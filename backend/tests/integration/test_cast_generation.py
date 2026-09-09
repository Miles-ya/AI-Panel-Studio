from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.database import create_sqlite_engine, initialize_database
from app.models import Discussion, Participant
from app.repositories import DiscussionRepository
from app.services import DiscussionService


class FakeLLMProviderError(Exception):
    pass


class ScriptedFakeLLMProvider:
    """A test-only, deterministic stand-in for the external LLM boundary."""

    def __init__(self, responses: list[list[dict[str, str]] | Exception]) -> None:
        self._responses = iter(responses)
        self.generate_cast_calls = 0

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> list[dict[str, str]]:
        del topic, expert_count, correction
        self.generate_cast_calls += 1
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def database_engine(tmp_path: Path) -> Engine:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'cast-generation.db'}")
    initialize_database(engine, seed=False)
    try:
        yield engine
    finally:
        engine.dispose()


def test_when_fake_llm_returns_a_valid_cast_then_it_persists_a_complete_ready_cast(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_draft_discussion(session, expert_count=3)
        fake_llm = ScriptedFakeLLMProvider([_valid_cast()])
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        generated = service.generate_cast(discussion.id)

        participants = _participants(session, discussion.id)
        assert generated.id == discussion.id
        assert generated.status == "CAST_READY"
        assert generated.cast_confirmed is False
        assert sum(person.role == "moderator" for person in participants) == 1
        assert sum(person.role == "expert" for person in participants) == discussion.expert_count
        _assert_complete_public_cast(participants)
    finally:
        session.close()


def test_when_regenerating_a_confirmed_cast_then_it_replaces_the_cast_and_clears_confirmation(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_confirmed_ready_discussion(session, expert_count=3)
        old_participant_ids = {person.id for person in _participants(session, discussion.id)}
        fake_llm = ScriptedFakeLLMProvider([_valid_cast(prefix="新")])
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        regenerated = service.generate_cast(discussion.id)

        participants = _participants(session, discussion.id)
        assert regenerated.status == "CAST_READY"
        assert regenerated.cast_confirmed is False
        assert regenerated.cast_confirmed_at is None
        assert {person.id for person in participants}.isdisjoint(old_participant_ids)
        assert len(participants) == 4
        _assert_complete_public_cast(participants)
    finally:
        session.close()


def test_when_first_cast_is_invalid_and_correction_is_valid_then_it_persists_the_corrected_cast(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_draft_discussion(session, expert_count=3)
        fake_llm = ScriptedFakeLLMProvider([_invalid_cast_with_duplicate_color(), _valid_cast()])
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        generated = service.generate_cast(discussion.id)

        participants = _participants(session, discussion.id)
        assert generated.status == "CAST_READY"
        assert fake_llm.generate_cast_calls == 2
        _assert_complete_public_cast(participants)
    finally:
        session.close()


def test_when_cast_and_its_single_correction_are_invalid_then_it_preserves_the_confirmed_cast(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_confirmed_ready_discussion(session, expert_count=3)
        before = _cast_snapshot(session, discussion.id)
        fake_llm = ScriptedFakeLLMProvider(
            [_invalid_cast_with_duplicate_color(), _invalid_cast_with_duplicate_color()]
        )
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        with pytest.raises(Exception):
            service.generate_cast(discussion.id)

        assert fake_llm.generate_cast_calls == 2
        assert _cast_snapshot(session, discussion.id) == before
    finally:
        session.close()


def test_when_the_provider_fails_before_generating_then_it_preserves_the_confirmed_cast(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_confirmed_ready_discussion(session, expert_count=3)
        before = _cast_snapshot(session, discussion.id)
        fake_llm = ScriptedFakeLLMProvider([FakeLLMProviderError("provider unavailable")])
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        with pytest.raises(Exception):
            service.generate_cast(discussion.id)

        assert fake_llm.generate_cast_calls == 1
        assert _cast_snapshot(session, discussion.id) == before
    finally:
        session.close()


def test_when_the_provider_fails_during_correction_then_it_preserves_the_confirmed_cast(
    database_engine: Engine,
) -> None:
    session = Session(database_engine)
    try:
        discussion = _create_confirmed_ready_discussion(session, expert_count=3)
        before = _cast_snapshot(session, discussion.id)
        fake_llm = ScriptedFakeLLMProvider(
            [_invalid_cast_with_duplicate_color(), FakeLLMProviderError("provider unavailable")]
        )
        service = DiscussionService(DiscussionRepository(session), llm_provider=fake_llm)

        with pytest.raises(Exception):
            service.generate_cast(discussion.id)

        assert fake_llm.generate_cast_calls == 2
        assert _cast_snapshot(session, discussion.id) == before
    finally:
        session.close()


def _create_draft_discussion(session: Session, *, expert_count: int) -> Discussion:
    return DiscussionService(DiscussionRepository(session)).create("AI 治理应如何落地？", expert_count)


def _create_confirmed_ready_discussion(session: Session, *, expert_count: int) -> Discussion:
    discussion = _create_draft_discussion(session, expert_count=expert_count)
    discussion.status = "CAST_READY"
    discussion.cast_confirmed = True
    discussion.cast_confirmed_at = datetime(2026, 9, 9, tzinfo=UTC)
    session.add_all(
        _participants_from_cast(discussion.id, _valid_cast(prefix="旧")))
    session.commit()
    session.refresh(discussion)
    return discussion


def _participants_from_cast(discussion_id: str, cast: list[dict[str, str]]) -> list[Participant]:
    now = datetime.now(UTC)
    return [
        Participant(
            id=f"{discussion_id}-{index}",
            discussion_id=discussion_id,
            runtime_status="idle",
            created_at=now,
            **candidate,
        )
        for index, candidate in enumerate(cast, start=1)
    ]


def _participants(session: Session, discussion_id: str) -> list[Participant]:
    return list(
        session.scalars(
            select(Participant)
            .where(Participant.discussion_id == discussion_id)
            .order_by(Participant.id)
        )
    )


def _cast_snapshot(session: Session, discussion_id: str) -> tuple[bool, datetime | None, list[tuple[Any, ...]]]:
    discussion = session.get(Discussion, discussion_id)
    assert discussion is not None
    participants = [
        (
            person.id,
            person.role,
            person.name,
            person.profession,
            person.title,
            person.stance,
            person.color,
        )
        for person in _participants(session, discussion_id)
    ]
    return discussion.cast_confirmed, discussion.cast_confirmed_at, participants


def _assert_complete_public_cast(participants: list[Participant]) -> None:
    assert participants
    assert all(
        field.strip()
        for person in participants
        for field in (person.name, person.profession, person.title, person.stance)
    )
    assert all(
        len(person.color) == 7
        and person.color.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in person.color[1:])
        for person in participants
    )
    assert len({person.color for person in participants}) == len(participants)
    expert_stances = {person.stance for person in participants if person.role == "expert"}
    assert len(expert_stances) >= 2


def _valid_cast(*, prefix: str = "") -> list[dict[str, str]]:
    return [
        {
            "role": "moderator",
            "name": f"{prefix}林澄",
            "profession": "科技记者",
            "title": "商业栏目主编",
            "stance": "优先厘清决策边界",
            "color": "#2563EB",
        },
        {
            "role": "expert",
            "name": f"{prefix}周启明",
            "profession": "组织发展顾问",
            "title": "人力战略负责人",
            "stance": "自动化应与员工转岗机制同步设计",
            "color": "#F59E0B",
        },
        {
            "role": "expert",
            "name": f"{prefix}沈言",
            "profession": "财务战略顾问",
            "title": "企业转型负责人",
            "stance": "应先验证可量化的投资回报",
            "color": "#10B981",
        },
        {
            "role": "expert",
            "name": f"{prefix}许宁",
            "profession": "技术治理研究员",
            "title": "AI 风险与合规顾问",
            "stance": "应优先界定可审计的风险边界",
            "color": "#EC4899",
        },
    ]


def _invalid_cast_with_duplicate_color() -> list[dict[str, str]]:
    cast = _valid_cast()
    cast[-1] = {**cast[-1], "color": cast[-2]["color"]}
    return cast
