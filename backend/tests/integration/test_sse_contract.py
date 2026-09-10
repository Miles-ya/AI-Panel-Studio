from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.main import app
from app.models import Discussion, Insight, Participant, Utterance
from app.repositories import DiscussionRepository, InsightRepository, ParticipantRepository, UtteranceRepository
from app.runtime import EventHub, RunnerRegistry


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'sse-contract.db'}")
    initialize_database(engine, seed=False)
    app.state.session_factory = sessionmaker(bind=engine)
    try:
        yield engine
    finally:
        del app.state.session_factory
        engine.dispose()


def _seed_discussion(engine: Engine, *, discussion_id: str, label: str, status: str = "RUNNING") -> None:
    now = datetime.now(UTC)
    moderator_id = f"{discussion_id}-moderator"
    with Session(engine) as session:
        session.add(
            Discussion(
                id=discussion_id,
                topic=f"{label} topic",
                expert_count=2,
                max_public_utterances=15,
                status=status,
                cast_confirmed=True,
                cast_confirmed_at=now,
                summary=f"{label} summary" if status == "FINISHED" else None,
                summary_status="succeeded" if status == "FINISHED" else "pending",
                created_at=now,
                updated_at=now,
                started_at=now,
                finished_at=now if status == "FINISHED" else None,
            )
        )
        session.add_all(
            [
                Participant(
                    id=moderator_id,
                    discussion_id=discussion_id,
                    role="moderator",
                    name=f"{label} moderator",
                    profession="记者",
                    title="主持人",
                    stance=f"{label} stance",
                    color="#2563EB",
                    runtime_status="idle",
                    public_focus=None,
                    created_at=now,
                ),
                Participant(
                    id=f"{discussion_id}-expert",
                    discussion_id=discussion_id,
                    role="expert",
                    name=f"{label} expert",
                    profession="研究员",
                    title="专家",
                    stance=f"{label} expert stance",
                    color="#F59E0B",
                    runtime_status="idle",
                    public_focus=None,
                    created_at=now,
                ),
            ]
        )
        session.add(
            Utterance(
                id=f"{discussion_id}-utterance",
                discussion_id=discussion_id,
                participant_id=moderator_id,
                sequence=1,
                content=f"{label} utterance",
                created_at=now,
            )
        )
        session.add(
            Insight(
                id=f"{discussion_id}-insight",
                discussion_id=discussion_id,
                type="consensus",
                content=f"{label} insight",
                active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def _parse_sse_frame(frame: bytes | str) -> tuple[str, dict[str, Any]]:
    text = frame.decode() if isinstance(frame, bytes) else frame
    lines = [line for line in text.splitlines() if line]
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    return lines[0][len("event: "):], json.loads(lines[1][len("data: "):])


@pytest.mark.anyio
async def test_events_unknown_discussion_returns_404(database_engine: Engine) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/discussions/{uuid4()}/events")

    assert response.status_code == 404


@pytest.mark.anyio
async def test_snapshot_event_is_complete_aggregate_identical_to_rest_snapshot(
    database_engine: Engine,
) -> None:
    discussion_id = "sse-snapshot-discussion"
    _seed_discussion(database_engine, discussion_id=discussion_id, label="snapshot")
    transport = ASGITransport(app=app, raise_app_exceptions=True)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        rest_snapshot = (await client.get(f"/api/discussions/{discussion_id}")).json()
        response = await client.get(f"/api/discussions/{discussion_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    event_name, data = _parse_sse_frame(response.content)
    assert event_name == "discussion.snapshot"
    assert data["discussion_id"] == discussion_id
    assert data["discussion"] == rest_snapshot
    assert set(data["discussion"]) == {
        "id", "topic", "expert_count", "max_public_utterances", "status",
        "cast_confirmed", "cast_confirmed_at", "summary", "summary_status",
        "error_code", "created_at", "updated_at", "started_at", "finished_at",
        "participants", "utterances", "insights",
    }


@pytest.mark.anyio
async def test_stream_body_iterator_emits_public_event_frames_without_closing_connection(
    database_engine: Engine,
) -> None:
    discussion_id = "sse-stream-discussion"
    _seed_discussion(database_engine, discussion_id=discussion_id, label="stream")
    route = next(route for route in app.routes if getattr(route, "path", "") == "/api/discussions/{discussion_id}/events")
    app.state.event_hub = EventHub()
    response = await route.endpoint(discussion_id)
    assert response.media_type == "text/event-stream"
    iterator = response.body_iterator
    assert hasattr(iterator, "__anext__")

    publish_task = asyncio.create_task(
        app.state.event_hub.publish(
            {
                "type": "participant.status.changed",
                "discussion_id": discussion_id,
                "participant": {"id": f"{discussion_id}-expert", "runtime_status": "speaking", "public_focus": "公开关注点"},
            }
        )
    )
    frame = await asyncio.wait_for(iterator.__anext__(), timeout=0.5)
    await publish_task
    event_name, data = _parse_sse_frame(frame)
    assert event_name == "participant.status.changed"
    assert data["discussion_id"] == discussion_id


@pytest.mark.anyio
async def test_event_hub_keeps_all_public_event_types_isolated_by_discussion_id() -> None:
    hub = EventHub()
    subscription_a = await hub.subscribe("discussion-a")
    subscription_b = await hub.subscribe("discussion-b")
    events = [
        ("participant.status.changed", {"participant": {"runtime_status": "speaking"}}),
        ("utterance.created", {"utterance": {"content": "A utterance"}}),
        ("insights.updated", {"insights": [{"content": "A insight"}]}),
        ("discussion.finished", {"status": "FINISHED", "summary": "A summary"}),
        ("discussion.error", {"final_status": "FAILED", "error": {"code": "A_FAILURE"}}),
    ]
    for event_type, payload in events:
        await hub.publish({"type": event_type, "discussion_id": "discussion-a", **payload})

    received_a = [await asyncio.wait_for(subscription_a.__anext__(), timeout=0.5) for _ in events]
    assert [event["type"] for event in received_a] == [event_type for event_type, _ in events]
    assert all(event["discussion_id"] == "discussion-a" for event in received_a)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(subscription_b.__anext__(), timeout=0.05)


def test_repositories_never_return_records_from_another_discussion(database_engine: Engine) -> None:
    _seed_discussion(database_engine, discussion_id="repository-a", label="A")
    _seed_discussion(database_engine, discussion_id="repository-b", label="B")
    with Session(database_engine) as session:
        repository = DiscussionRepository(session)
        participant_repository = ParticipantRepository(session)
        utterance_repository = UtteranceRepository(session)
        insight_repository = InsightRepository(session)
        assert repository.participant_count("repository-a") == 2
        assert repository.participant_count("repository-b") == 2
        assert {item.discussion_id for item in participant_repository.list_for_discussion("repository-a")} == {"repository-a"}
        assert {item.discussion_id for item in utterance_repository.list_for_discussion("repository-a")} == {"repository-a"}
        assert {item.discussion_id for item in insight_repository.active_for_discussion("repository-a")} == {"repository-a"}
        assert all(item.discussion_id != "repository-a" for item in participant_repository.list_for_discussion("repository-b"))
        assert all(item.discussion_id != "repository-a" for item in utterance_repository.list_for_discussion("repository-b"))
        assert all(item.discussion_id != "repository-a" for item in insight_repository.active_for_discussion("repository-b"))


@pytest.mark.anyio
async def test_runner_registry_keeps_a_and_b_runners_distinct() -> None:
    class StubRunner:
        def __init__(self, discussion_id: str) -> None:
            self.discussion_id = discussion_id
            self._task = None

        async def run(self) -> None:
            return None

        def attach_task(self, task: asyncio.Task[None]) -> None:
            self._task = task

    registry = RunnerRegistry()
    runner_a = StubRunner("discussion-a")
    runner_b = StubRunner("discussion-b")
    await registry.start(runner_a)
    await registry.start(runner_b)
    await asyncio.gather(runner_a._task, runner_b._task)
    assert registry.get("discussion-a") is runner_a
    assert registry.get("discussion-b") is runner_b
