from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.main import app, get_discussion_service
from app.models import Discussion, Participant
from app.repositories import DiscussionRepository
from app.services import DiscussionService


class FakeLLMProvider:
    def __init__(self, responses: list[list[dict[str, str]] | Exception]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, int, str | None]] = []

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> list[dict[str, str]]:
        self.calls.append((topic, expert_count, correction))
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'cast-generation-api.db'}")
    initialize_database(engine, seed=False)
    app.state.session_factory = sessionmaker(bind=engine)
    try:
        yield engine
    finally:
        del app.state.session_factory
        engine.dispose()


@pytest.fixture()
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider([_valid_cast(), _invalid_cast(), _invalid_cast()])


@pytest.fixture(autouse=True)
def override_service(fake_llm: FakeLLMProvider) -> Iterator[None]:
    async def get_fake_service() -> AsyncIterator[DiscussionService]:
        session = getattr(app.state, "session_factory")()
        try:
            yield DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)
        finally:
            session.close()

    app.dependency_overrides[get_discussion_service] = get_fake_service
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.anyio
async def test_when_generating_a_draft_cast_then_it_can_be_confirmed(
    client: AsyncClient, database_engine: Engine
) -> None:
    discussion_id = _persist_discussion(database_engine, status="DRAFT")

    generated = await client.post(f"/api/discussions/{discussion_id}/generate-cast")

    assert generated.status_code == 200
    assert generated.json()["status"] == "CAST_READY"
    assert generated.json()["cast_confirmed"] is False
    with Session(database_engine) as session:
        participants = list(
            session.scalars(select(Participant).where(Participant.discussion_id == discussion_id))
        )
        assert sum(person.role == "moderator" for person in participants) == 1
        assert sum(person.role == "expert" for person in participants) == 3

    confirmed = await client.post(f"/api/discussions/{discussion_id}/confirm", json={})

    assert confirmed.status_code == 200
    assert confirmed.json()["cast_confirmed"] is True


@pytest.mark.parametrize("status", ["RUNNING", "FINISHED", "FAILED"])
@pytest.mark.anyio
async def test_when_generating_cast_from_an_illegal_state_then_it_does_not_call_the_provider_or_change_data(
    client: AsyncClient, database_engine: Engine, fake_llm: FakeLLMProvider, status: str
) -> None:
    discussion_id = _persist_discussion(database_engine, status=status)
    before = _snapshot(database_engine, discussion_id)

    response = await client.post(f"/api/discussions/{discussion_id}/generate-cast")

    assert response.status_code == 409
    assert fake_llm.calls == []
    assert _snapshot(database_engine, discussion_id) == before


@pytest.mark.anyio
async def test_when_regeneration_and_its_correction_are_invalid_then_it_preserves_the_confirmed_cast(
    client: AsyncClient, database_engine: Engine, fake_llm: FakeLLMProvider
) -> None:
    discussion_id = _persist_discussion(database_engine, status="CAST_READY", confirmed=True)
    _persist_cast(database_engine, discussion_id, _valid_cast(prefix="旧"))
    before = _snapshot(database_engine, discussion_id)
    fake_llm._responses = iter([_invalid_cast(), _invalid_cast()])

    response = await client.post(f"/api/discussions/{discussion_id}/generate-cast")

    assert response.status_code == 502
    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[1][2]
    assert _snapshot(database_engine, discussion_id) == before


def _persist_discussion(engine: Engine, *, status: str, confirmed: bool = False) -> str:
    discussion_id = str(uuid4())
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            Discussion(
                id=discussion_id,
                topic="讨论 AI 治理的边界",
                expert_count=3,
                max_public_utterances=15,
                status=status,
                cast_confirmed=confirmed,
                cast_confirmed_at=now if confirmed else None,
                summary_status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    return discussion_id


def _persist_cast(engine: Engine, discussion_id: str, cast: list[dict[str, str]]) -> None:
    with Session(engine) as session:
        session.add_all(
            Participant(
                id=str(uuid4()),
                discussion_id=discussion_id,
                runtime_status="idle",
                created_at=datetime.now(UTC),
                **candidate,
            )
            for candidate in cast
        )
        session.commit()


def _snapshot(engine: Engine, discussion_id: str) -> tuple[bool, datetime | None, list[tuple[Any, ...]]]:
    with Session(engine) as session:
        discussion = session.get(Discussion, discussion_id)
        assert discussion is not None
        participants = list(
            session.scalars(
                select(Participant).where(Participant.discussion_id == discussion_id).order_by(Participant.id)
            )
        )
        return (
            discussion.cast_confirmed,
            discussion.cast_confirmed_at,
            [(p.id, p.role, p.name, p.color) for p in participants],
        )


def _valid_cast(*, prefix: str = "") -> list[dict[str, str]]:
    return [
        {"role": "moderator", "name": f"{prefix}林澄", "profession": "科技记者", "title": "商业栏目主编", "stance": "先界定决策边界", "color": "#2563EB"},
        {"role": "expert", "name": f"{prefix}周启明", "profession": "组织顾问", "title": "人力负责人", "stance": "转岗机制必须同步设计", "color": "#F59E0B"},
        {"role": "expert", "name": f"{prefix}沈言", "profession": "财务顾问", "title": "转型负责人", "stance": "先验证投资回报", "color": "#10B981"},
        {"role": "expert", "name": f"{prefix}许宁", "profession": "技术研究员", "title": "合规顾问", "stance": "优先保证风险可审计", "color": "#EC4899"},
    ]


def _invalid_cast() -> list[dict[str, str]]:
    cast = _valid_cast()
    cast[-1] = {**cast[-1], "color": cast[-2]["color"]}
    return cast
