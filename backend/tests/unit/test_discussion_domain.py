from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _domain_types() -> tuple[type[Any], type[Exception]]:
    """Load the future pure aggregate without turning its absence into collection failure."""
    try:
        domain = import_module("app.domain")
    except ModuleNotFoundError:
        pytest.fail("Discussion aggregate is not implemented")

    discussion = getattr(domain, "Discussion", None)
    violation = getattr(domain, "DiscussionRuleViolation", None)
    assert discussion is not None, "Discussion aggregate is not implemented"
    assert violation is not None, "Discussion aggregate is not implemented"
    assert callable(getattr(discussion, "create", None)), "Discussion aggregate is not implemented"
    assert callable(getattr(discussion, "rehydrate", None)), "Discussion aggregate is not implemented"
    return discussion, violation


def _rehydrate(status: str, *, cast_confirmed: bool = False) -> Any:
    discussion, _ = _domain_types()
    return discussion.rehydrate(
        topic="讨论 AI 治理的边界",
        expert_count=4,
        max_public_utterances=15,
        status=status,
        cast_confirmed=cast_confirmed,
    )


def test_when_creating_discussion_then_topic_is_trimmed_and_mvp_defaults_are_applied() -> None:
    discussion, _ = _domain_types()

    created = discussion.create("  AI 应如何参与公共决策？  ")

    assert created.topic == "AI 应如何参与公共决策？"
    assert created.expert_count == 4
    assert created.max_public_utterances == 15
    assert created.status == "DRAFT"
    assert created.cast_confirmed is False


@pytest.mark.parametrize("topic", ["   ", "x" * 301])
def test_when_creating_discussion_with_invalid_topic_then_domain_rule_is_rejected(topic: str) -> None:
    discussion, violation = _domain_types()

    with pytest.raises(violation) as captured:
        discussion.create(topic)

    assert captured.value.code == "INVALID_TOPIC"


@pytest.mark.parametrize("expert_count", [1, 9])
def test_when_creating_discussion_outside_expert_range_then_domain_rule_is_rejected(
    expert_count: int,
) -> None:
    discussion, violation = _domain_types()

    with pytest.raises(violation) as captured:
        discussion.create("讨论 AI 治理", expert_count=expert_count)

    assert captured.value.code == "INVALID_EXPERT_COUNT"


def test_when_discussion_is_draft_then_confirm_and_start_are_rejected() -> None:
    draft = _rehydrate("DRAFT")
    _, violation = _domain_types()

    with pytest.raises(violation) as confirm_error:
        draft.confirm_cast()
    with pytest.raises(violation) as start_error:
        draft.start()

    assert confirm_error.value.code == "DISCUSSION_STATE_CONFLICT"
    assert start_error.value.code == "DISCUSSION_STATE_CONFLICT"


def test_when_cast_is_ready_but_unconfirmed_then_start_is_rejected() -> None:
    ready = _rehydrate("CAST_READY")
    _, violation = _domain_types()

    with pytest.raises(violation) as captured:
        ready.start()

    assert captured.value.code == "DISCUSSION_STATE_CONFLICT"


def test_when_ready_cast_is_confirmed_then_discussion_can_start() -> None:
    ready = _rehydrate("CAST_READY")

    ready.confirm_cast()
    ready.start()

    assert ready.cast_confirmed is True
    assert ready.status == "RUNNING"


@pytest.mark.parametrize("status", ["DRAFT", "CAST_READY"])
@pytest.mark.parametrize("action", ["finish", "fail"])
def test_when_discussion_is_not_running_then_finish_and_fail_are_rejected(
    status: str,
    action: str,
) -> None:
    discussion = _rehydrate(status)
    _, violation = _domain_types()

    with pytest.raises(violation) as captured:
        getattr(discussion, action)()

    assert captured.value.code == "DISCUSSION_STATE_CONFLICT"


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [("finish", "FINISHED"), ("fail", "FAILED")],
)
def test_when_discussion_is_running_then_it_can_reach_a_terminal_state(
    action: str,
    expected_status: str,
) -> None:
    running = _rehydrate("RUNNING", cast_confirmed=True)

    getattr(running, action)()

    assert running.status == expected_status


@pytest.mark.parametrize("status", ["FINISHED", "FAILED"])
def test_when_discussion_is_terminal_then_it_cannot_start_again(status: str) -> None:
    terminal = _rehydrate(status, cast_confirmed=True)
    _, violation = _domain_types()

    with pytest.raises(violation) as captured:
        terminal.start()

    assert captured.value.code == "DISCUSSION_STATE_CONFLICT"
