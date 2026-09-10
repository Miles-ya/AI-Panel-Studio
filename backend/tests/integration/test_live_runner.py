from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.models import Discussion, Insight, Participant, Utterance
from app.repositories import DiscussionRepository


DISCUSSION_A = "11111111-1111-4111-8111-111111111111"
DISCUSSION_B = "22222222-2222-4222-8222-222222222222"
MODERATOR_ID = "33333333-3333-4333-8333-333333333333"
EXPERT_ONE_ID = "44444444-4444-4444-8444-444444444444"
EXPERT_TWO_ID = "55555555-5555-4555-8555-555555555555"
OTHER_MODERATOR_ID = "66666666-6666-4666-8666-666666666666"
OTHER_EXPERT_ID = "77777777-7777-4777-8777-777777777777"
OTHER_EXPERT_TWO_ID = "88888888-8888-4888-8888-888888888888"


@dataclass
class ScriptedProvider:
    """Deterministic provider injected into the real SQLite-backed Runner."""

    selections: list[dict[str, Any]]
    turns: list[dict[str, Any]]
    insights: list[dict[str, Any] | Exception]
    summaries: list[str | Exception]
    selection_calls: int = 0
    turn_calls: int = 0
    insight_calls: int = 0
    summary_calls: int = 0

    def select_next_speaker(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.selection_calls += 1
        return self.selections.pop(0)

    def generate_turn(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.turn_calls += 1
        return self.turns.pop(0)

    def extract_insights(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.insight_calls += 1
        result = self.insights.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def summarize(self, *_: Any, **__: Any) -> str:
        self.summary_calls += 1
        result = self.summaries.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class SqliteRunnerFixture:
    engine: Engine
    session_factory: sessionmaker[Session]
    discussion_id: str
    runner: Any
    event_hub: Any
    provider: ScriptedProvider
    stop_event: asyncio.Event

    def session(self) -> Session:
        return self.session_factory()

    def contents(self) -> list[str]:
        with self.session() as session:
            return list(
                session.scalars(
                    select(Utterance.content)
                    .where(Utterance.discussion_id == self.discussion_id)
                    .order_by(Utterance.sequence)
                )
            )

    def active_insights(self) -> list[dict[str, str]]:
        with self.session() as session:
            return [
                {"type": insight.type, "content": insight.content}
                for insight in session.scalars(
                    select(Insight)
                    .where(Insight.discussion_id == self.discussion_id, Insight.active.is_(True))
                    .order_by(Insight.created_at, Insight.id)
                )
            ]

    def inactive_insight_count(self) -> int:
        with self.session() as session:
            return int(
                session.scalar(
                    select(Insight.id)
                    .where(Insight.discussion_id == self.discussion_id, Insight.active.is_(False))
                    .limit(1)
                )
                is not None
            )

    def status(self) -> str:
        with self.session() as session:
            discussion = session.get(Discussion, self.discussion_id)
            assert discussion is not None
            return discussion.status


class PersistenceCheckingEventHub:
    def __init__(self, inner: Any, session_factory: sessionmaker[Session]) -> None:
        self.inner = inner
        self.session_factory = session_factory
        self.before_publish: list[tuple[str, bool, bool]] = []

    async def publish(self, *args: Any, **kwargs: Any) -> Any:
        event = kwargs.get("event") or next(
            (value for value in reversed(args) if isinstance(value, dict)), None
        )
        if event is not None and (
            event.get("type") == "utterance.created"
            or (
                event.get("type") == "participant.status.changed"
                and event.get("participant", {}).get("runtime_status") in {"preparing", "speaking"}
            )
        ):
            discussion_id = event["discussion_id"]
            participant_id = event.get("participant", {}).get("id")
            utterance_id = event.get("utterance", {}).get("id")
            with self.session_factory() as session:
                participant = session.get(Participant, participant_id) if participant_id else None
                utterance = session.get(Utterance, utterance_id) if utterance_id else None
                self.before_publish.append(
                    (
                        event["type"],
                        participant is not None and participant.discussion_id == discussion_id,
                        utterance is not None and utterance.discussion_id == discussion_id,
                    )
                )
        return await self.inner.publish(*args, **kwargs)

    async def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return await self.inner.subscribe(*args, **kwargs)


class SafePointEventHub:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.utterance_published = asyncio.Event()
        self.release_after_utterance = asyncio.Event()

    async def publish(self, *args: Any, **kwargs: Any) -> Any:
        event = kwargs.get("event") or next(
            (value for value in reversed(args) if isinstance(value, dict)), None
        )
        result = await self.inner.publish(*args, **kwargs)
        if event is not None and event.get("type") == "utterance.created":
            self.utterance_published.set()
            await self.release_after_utterance.wait()
        return result

    async def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return await self.inner.subscribe(*args, **kwargs)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _runtime_contract() -> tuple[type[Any], type[Any], type[Any]]:
    """Fail in Red only because the real runtime boundary is not implemented yet."""
    try:
        runtime = import_module("app.runtime")
    except ModuleNotFoundError as error:
        pytest.fail("DiscussionRunner/EventHub/RunnerRegistry are not implemented")
        raise AssertionError from error

    runner = getattr(runtime, "DiscussionRunner", None)
    event_hub = getattr(runtime, "EventHub", None)
    registry = getattr(runtime, "RunnerRegistry", None)
    assert runner is not None, "DiscussionRunner is not implemented"
    assert event_hub is not None, "EventHub is not implemented"
    assert registry is not None, "RunnerRegistry is not implemented"
    return runner, event_hub, registry


def _repository_types() -> tuple[type[Any], type[Any], type[Any]]:
    repositories = import_module("app.repositories")
    participant = getattr(repositories, "ParticipantRepository", None)
    utterance = getattr(repositories, "UtteranceRepository", None)
    insight = getattr(repositories, "InsightRepository", None)
    assert participant is not None, "ParticipantRepository is not implemented"
    assert utterance is not None, "UtteranceRepository is not implemented"
    assert insight is not None, "InsightRepository is not implemented"
    return participant, utterance, insight


def _participant(*, participant_id: str, discussion_id: str, role: str, name: str) -> Participant:
    colors = {
        "主持人": "#2563EB",
        "专家一": "#F59E0B",
        "专家二": "#10B981",
    }
    return Participant(
        id=participant_id,
        discussion_id=discussion_id,
        role=role,
        name=name,
        profession="测试职业",
        title="测试职务",
        stance=f"{name} 的公开立场",
        color=colors[name],
        runtime_status="idle",
        created_at=datetime.now(UTC),
    )


def _seed_discussion(
    engine: Engine,
    *,
    discussion_id: str,
    participant_ids: tuple[str, str, str],
    initial_utterance_count: int = 0,
    active_insights: list[tuple[str, str]] | None = None,
) -> None:
    now = datetime.now(UTC)
    moderator_id, expert_one_id, expert_two_id = participant_ids
    with Session(engine) as session:
        session.add(
            Discussion(
                id=discussion_id,
                topic=f"测试讨论 {discussion_id}",
                expert_count=2,
                max_public_utterances=15,
                status="RUNNING",
                cast_confirmed=True,
                summary_status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                _participant(
                    participant_id=moderator_id,
                    discussion_id=discussion_id,
                    role="moderator",
                    name="主持人",
                ),
                _participant(
                    participant_id=expert_one_id,
                    discussion_id=discussion_id,
                    role="expert",
                    name="专家一",
                ),
                _participant(
                    participant_id=expert_two_id,
                    discussion_id=discussion_id,
                    role="expert",
                    name="专家二",
                ),
            ]
        )
        for sequence in range(1, initial_utterance_count + 1):
            participant_id = (moderator_id, expert_one_id, expert_two_id)[(sequence - 1) % 3]
            session.add(
                Utterance(
                    id=f"{discussion_id[:8]}-{sequence:028d}",
                    discussion_id=discussion_id,
                    participant_id=participant_id,
                    sequence=sequence,
                    content=f"既有发言 {sequence}",
                    created_at=now + timedelta(microseconds=sequence),
                )
            )
        for index, (insight_type, content) in enumerate(active_insights or [], start=1):
            session.add(
                Insight(
                    id=f"{discussion_id[:8]}-{index:028d}",
                    discussion_id=discussion_id,
                    type=insight_type,
                    content=content,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()


@pytest.fixture()
def sqlite_runner(tmp_path: Path) -> Path:
    return tmp_path / "runner.db"


def _make_fixture(
    database: Path | Engine,
    *,
    runtime_contract: tuple[type[Any], type[Any], type[Any]],
    provider: ScriptedProvider,
    discussion_id: str = DISCUSSION_A,
    participant_ids: tuple[str, str, str] = (MODERATOR_ID, EXPERT_ONE_ID, EXPERT_TWO_ID),
    initial_utterance_count: int = 0,
    active_insights: list[tuple[str, str]] | None = None,
    event_hub_wrapper: Callable[[Any, sessionmaker[Session]], Any] | None = None,
    seed: bool = True,
) -> SqliteRunnerFixture:
    runner_type, event_hub_type, _ = runtime_contract
    engine = database if isinstance(database, Engine) else create_sqlite_engine(f"sqlite:///{database}")
    if isinstance(database, Path):
        initialize_database(engine, seed=False)
    if seed:
        _seed_discussion(
            engine,
            discussion_id=discussion_id,
            participant_ids=participant_ids,
            initial_utterance_count=initial_utterance_count,
            active_insights=active_insights,
        )
    factory = sessionmaker(bind=engine)
    event_hub = event_hub_type()
    if event_hub_wrapper is not None:
        event_hub = event_hub_wrapper(event_hub, factory)
    stop_event = asyncio.Event()
    runner = runner_type(
        discussion_id=discussion_id,
        session_factory=factory,
        llm_provider=provider,
        event_hub=event_hub,
        stop_event=stop_event,
    )
    return SqliteRunnerFixture(
        engine, factory, discussion_id, runner, event_hub, provider, stop_event
    )


async def _events_until(subscription: Any, event_type: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        event = await asyncio.wait_for(subscription.__anext__(), timeout=0.5)
        events.append(event)
        if event["type"] == event_type:
            return events


@pytest.mark.anyio
async def test_utterance_created_is_published_after_persisted_status_and_utterance(
    sqlite_runner: Path,
) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": MODERATOR_ID, "public_focus": "界定问题"}],
            turns=[{"content": "第一条公开发言", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["讨论已完成"],
        ),
        event_hub_wrapper=PersistenceCheckingEventHub,
    )
    subscription = await fixture.event_hub.subscribe(fixture.discussion_id)

    await fixture.runner.run_one_turn()
    events = await _events_until(subscription, "utterance.created")

    assert [event["type"] for event in events[:3]] == [
        "participant.status.changed",
        "participant.status.changed",
        "utterance.created",
    ]
    assert events[0]["participant"]["runtime_status"] == "preparing"
    assert events[1]["participant"]["runtime_status"] == "speaking"
    assert getattr(fixture.event_hub, "before_publish") == [
        ("participant.status.changed", True, False),
        ("participant.status.changed", True, False),
        ("utterance.created", False, True),
    ]


@pytest.mark.anyio
async def test_each_round_replaces_the_complete_active_insight_set(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[
                {"participant_id": MODERATOR_ID, "public_focus": "先定义目标"},
                {"participant_id": EXPERT_ONE_ID, "public_focus": "补充证据"},
            ],
            turns=[
                {"content": "第一轮", "should_end": False},
                {"content": "第二轮", "should_end": True},
            ],
            insights=[
                {"consensus": ["旧共识"], "disagreement": ["旧分歧"]},
                {"consensus": ["新共识"], "disagreement": []},
            ],
            summaries=["完成"],
        ),
        active_insights=[("consensus", "初始观点")],
    )

    await fixture.runner.run()

    assert fixture.active_insights() == [{"type": "consensus", "content": "新共识"}]
    assert fixture.inactive_insight_count() > 0


@pytest.mark.anyio
async def test_insight_failure_keeps_saved_utterance_and_previous_insights(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": MODERATOR_ID, "public_focus": "先发言"}],
            turns=[{"content": "保留下来的发言", "should_end": True}],
            insights=[RuntimeError("insight provider failed")],
            summaries=["完成"],
        ),
        active_insights=[("consensus", "上一轮共识")],
    )
    subscription = await fixture.event_hub.subscribe(fixture.discussion_id)

    await fixture.runner.run()
    events = await _events_until(subscription, "discussion.finished")

    assert fixture.contents() == ["保留下来的发言"]
    assert fixture.active_insights() == [{"type": "consensus", "content": "上一轮共识"}]
    assert all(event["type"] != "insights.updated" for event in events)
    assert fixture.status() == "FINISHED"


@pytest.mark.anyio
async def test_user_stop_prevents_the_next_round_at_a_safe_point(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": MODERATOR_ID, "public_focus": "开始"}],
            turns=[{"content": "停止前的发言", "should_end": False}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["用户主动结束"],
        ),
        event_hub_wrapper=lambda event_hub, _: SafePointEventHub(event_hub),
    )
    subscription = await fixture.event_hub.subscribe(fixture.discussion_id)

    task = asyncio.create_task(fixture.runner.run())
    await fixture.event_hub.utterance_published.wait()
    fixture.stop_event.set()
    fixture.event_hub.release_after_utterance.set()
    await task

    assert fixture.status() == "FINISHED"
    assert fixture.provider.selection_calls == 1
    assert fixture.provider.turn_calls == 1


@pytest.mark.anyio
async def test_slow_synchronous_provider_call_does_not_block_the_event_loop(
    sqlite_runner: Path,
) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": MODERATOR_ID, "public_focus": "开始"}],
            turns=[{"content": "首条发言", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["完成"],
        ),
    )
    async def async_select_next_speaker(*args: Any, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return fixture.provider.select_next_speaker(*args, **kwargs)

    fixture.provider.async_select_next_speaker = async_select_next_speaker  # type: ignore[attr-defined]
    task = asyncio.create_task(fixture.runner.run_one_turn())

    await asyncio.sleep(0.01)

    assert not task.done()
    await task


@pytest.mark.anyio
async def test_fifteenth_slot_is_reserved_for_the_moderator_closing_statement(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[],
            turns=[{"content": "主持人第 15 条收束", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["达到公开发言上限"],
        ),
        initial_utterance_count=14,
    )

    await fixture.runner.run()

    assert len(fixture.contents()) == 15
    assert fixture.contents()[-1] == "主持人第 15 条收束"
    assert fixture.provider.selection_calls == 0
    assert fixture.provider.turn_calls == 1
    assert fixture.status() == "FINISHED"


@pytest.mark.anyio
async def test_manual_summary_retry_recovers_a_legacy_fallback_discussion(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": MODERATOR_ID, "public_focus": "收束"}],
            turns=[{"content": "最后一条", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["调解总结", "重试成功"],
        ),
    )

    await fixture.runner.run()

    with fixture.session() as session:
        discussion = session.get(Discussion, fixture.discussion_id)
        assert discussion is not None
        assert discussion.status == "FINISHED"
        assert discussion.finished_at is not None
        assert discussion.summary == "调解总结"
        assert discussion.summary_status == "succeeded"
        discussion.summary = "总结暂不可用"
        discussion.summary_status = "fallback"
        session.commit()
    utterance_count = len(fixture.contents())

    await fixture.runner.retry_summary()

    with fixture.session() as session:
        discussion = session.get(Discussion, fixture.discussion_id)
        assert discussion is not None
        assert discussion.summary == "重试成功"
        assert discussion.summary_status == "succeeded"
    assert len(fixture.contents()) == utterance_count
    assert fixture.provider.selection_calls == 1


@pytest.mark.anyio
async def test_expert_end_request_adds_a_moderator_closing_statement_as_the_summary(
    sqlite_runner: Path,
) -> None:
    runtime_contract = _runtime_contract()
    fixture = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[
                {"participant_id": EXPERT_ONE_ID, "public_focus": "提出最后观点"},
            ],
            turns=[
                {"content": "专家请求结束。", "should_end": True},
                {"content": "主持人收束：保留分歧并明确下一步。", "should_end": True},
            ],
            insights=[
                {"consensus": [], "disagreement": []},
                {"consensus": [], "disagreement": []},
            ],
            summaries=["AI 调解总结"],
        ),
        initial_utterance_count=1,
    )

    await fixture.runner.run()

    assert fixture.status() == "FINISHED"
    assert fixture.provider.turn_calls == 2
    assert fixture.contents() == [
        "既有发言 1",
        "专家请求结束。",
        "主持人收束：保留分歧并明确下一步。",
    ]
    with fixture.session() as session:
        discussion = session.get(Discussion, fixture.discussion_id)
        assert discussion is not None
        assert discussion.status == "FINISHED"
        assert discussion.summary == "AI 调解总结"


@pytest.mark.anyio
async def test_failure_in_one_discussion_does_not_stop_another_discussion(sqlite_runner: Path) -> None:
    runtime_contract = _runtime_contract()
    failed = _make_fixture(
        sqlite_runner,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": OTHER_EXPERT_ID, "public_focus": "越界"}],
            turns=[],
            insights=[],
            summaries=[],
        ),
        discussion_id=DISCUSSION_A,
    )
    _seed_discussion(
        failed.engine,
        discussion_id=DISCUSSION_B,
        participant_ids=(OTHER_MODERATOR_ID, OTHER_EXPERT_ID, OTHER_EXPERT_TWO_ID),
    )
    healthy = _make_fixture(
        failed.engine,
        runtime_contract=runtime_contract,
        provider=ScriptedProvider(
            selections=[{"participant_id": OTHER_MODERATOR_ID, "public_focus": "正常开始"}],
            turns=[{"content": "B 场发言", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["B 场完成"],
        ),
        discussion_id=DISCUSSION_B,
        participant_ids=(OTHER_MODERATOR_ID, OTHER_EXPERT_ID, OTHER_EXPERT_TWO_ID),
        seed=False,
    )
    _, _, registry_type = runtime_contract
    registry = registry_type()

    await asyncio.gather(registry.start(failed.runner), registry.start(healthy.runner))
    await asyncio.gather(failed.runner.wait_until_done(), healthy.runner.wait_until_done())

    assert failed.status() == "FAILED"
    assert healthy.status() == "FINISHED"
    assert healthy.contents() == ["B 场发言"]
