from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pytest


@dataclass
class ScriptedProvider:
    """A deterministic provider contract for the live-runner tests."""

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


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _runtime_contract() -> tuple[type[Any], type[Any], type[Any]]:
    """Fail in Red when the live-runner public boundary does not exist yet."""
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


async def _next_event(subscription: Any) -> dict[str, Any]:
    return await asyncio.wait_for(subscription.__anext__(), timeout=0.2)


@pytest.mark.anyio
async def test_utterance_created_is_published_only_after_database_commit() -> None:
    runner_type, event_hub_type, _ = _runtime_contract()
    harness = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[{"participant_id": "moderator", "public_focus": "界定问题"}],
            turns=[{"content": "第一条公开发言", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["讨论已完成"],
        ),
    )
    subscription = await event_hub_type.subscribe(harness.discussion_id)

    await harness.run_one_turn()
    event = await _next_event(subscription)

    assert event["type"] == "utterance.created"
    assert harness.repository.contains_utterance(event["utterance"]["id"])
    assert harness.repository.commit_count_at_publish(event["utterance"]["id"]) > 0


@pytest.mark.anyio
async def test_each_round_replaces_the_complete_active_insight_set() -> None:
    runner_type, _, _ = _runtime_contract()
    harness = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[
                {"participant_id": "moderator", "public_focus": "先定义目标"},
                {"participant_id": "expert-1", "public_focus": "补充证据"},
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
        active_insights=[{"type": "consensus", "content": "初始观点"}],
    )

    await harness.run_until_finished()

    assert harness.active_insights() == [{"type": "consensus", "content": "新共识"}]
    assert harness.inactive_insight_count() > 0


@pytest.mark.anyio
async def test_insight_failure_keeps_saved_utterance_and_previous_insights() -> None:
    runner_type, _, _ = _runtime_contract()
    harness = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[
                {"participant_id": "moderator", "public_focus": "先发言"},
                {"participant_id": "expert-1", "public_focus": "继续补充"},
            ],
            turns=[
                {"content": "保留下来的发言", "should_end": False},
                {"content": "下一轮发言", "should_end": True},
            ],
            insights=[RuntimeError("insight provider failed"), {"consensus": [], "disagreement": []}],
            summaries=["完成"],
        ),
        active_insights=[{"type": "consensus", "content": "上一轮共识"}],
    )

    await harness.run_until_finished()

    assert harness.contents() == ["保留下来的发言", "下一轮发言"]
    assert harness.active_insights() == [{"type": "consensus", "content": "上一轮共识"}]
    assert harness.status == "FINISHED"


@pytest.mark.anyio
async def test_user_stop_prevents_the_next_round_and_finishes_cleanly() -> None:
    runner_type, _, _ = _runtime_contract()
    provider = ScriptedProvider(
        selections=[{"participant_id": "moderator", "public_focus": "开始"}],
        turns=[{"content": "停止前的发言", "should_end": False}],
        insights=[{"consensus": [], "disagreement": []}],
        summaries=["用户主动结束"],
    )
    harness = await runner_type.test_harness(provider=provider)

    task = asyncio.create_task(harness.run())
    await harness.wait_until_event("utterance.created")
    await harness.stop()
    await task

    assert harness.status == "FINISHED"
    assert provider.selection_calls == 1
    assert provider.turn_calls == 1
    assert harness.finished_event()["summary_status"] == "succeeded"


@pytest.mark.anyio
async def test_fifteenth_saved_utterance_is_the_last_and_triggers_completion() -> None:
    runner_type, _, _ = _runtime_contract()
    harness = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[{"participant_id": "expert-1", "public_focus": "继续"}] * 15,
            turns=[{"content": f"第 {index} 条", "should_end": False} for index in range(1, 16)],
            insights=[{"consensus": [], "disagreement": []}] * 15,
            summaries=["达到公开发言上限"],
            initial_utterance_count=14,
        ),
    )

    await harness.run_until_finished()

    assert len(harness.contents()) == 15
    assert harness.contents()[-1] == "第 1 条"
    assert harness.provider.selection_calls == 1
    assert harness.provider.turn_calls == 1
    assert harness.status == "FINISHED"


@pytest.mark.anyio
async def test_summary_retries_once_then_falls_back_and_manual_retry_recovers_without_new_turn() -> None:
    runner_type, _, _ = _runtime_contract()
    provider = ScriptedProvider(
        selections=[{"participant_id": "moderator", "public_focus": "收束"}],
        turns=[{"content": "最后一条", "should_end": True}],
        insights=[{"consensus": [], "disagreement": []}],
        summaries=[RuntimeError("summary failed"), RuntimeError("summary failed again"), "重试成功"],
    )
    harness = await runner_type.test_harness(provider=provider)

    await harness.run_until_finished()

    assert harness.status == "FINISHED"
    assert harness.summary_status == "fallback"
    assert provider.summary_calls == 2
    utterance_count = len(harness.contents())

    await harness.retry_summary()

    assert harness.summary == "重试成功"
    assert harness.summary_status == "succeeded"
    assert provider.summary_calls == 3
    assert len(harness.contents()) == utterance_count
    assert provider.selection_calls == 1


@pytest.mark.anyio
async def test_failure_in_one_discussion_does_not_stop_another_discussion() -> None:
    runner_type, _, registry_type = _runtime_contract()
    failed = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[{"participant_id": "expert-outsider", "public_focus": "越界"}],
            turns=[],
            insights=[],
            summaries=[],
        ),
        discussion_id="discussion-a",
    )
    healthy = await runner_type.test_harness(
        provider=ScriptedProvider(
            selections=[{"participant_id": "moderator", "public_focus": "正常开始"}],
            turns=[{"content": "B 场发言", "should_end": True}],
            insights=[{"consensus": [], "disagreement": []}],
            summaries=["B 场完成"],
        ),
        discussion_id="discussion-b",
    )
    registry = registry_type()

    await asyncio.gather(registry.start(failed), registry.start(healthy))
    await asyncio.gather(failed.wait_until_done(), healthy.wait_until_done())

    assert failed.status == "FAILED"
    assert healthy.status == "FINISHED"
    assert healthy.contents() == ["B 场发言"]
    assert all(event["discussion_id"] == "discussion-b" for event in healthy.events())
