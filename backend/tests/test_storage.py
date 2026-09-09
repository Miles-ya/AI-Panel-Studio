from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_sqlite_engine, initialize_database
from app.models import Discussion, Insight, Participant, Utterance
from app.schemas import DiscussionStatus, ErrorResponse, ParticipantDto


@pytest.fixture()
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'storage.db'}"


def test_when_initialized_then_all_domain_tables_exist(database_url: str) -> None:
    engine = create_sqlite_engine(database_url)

    initialize_database(engine, seed=False)

    with engine.connect() as connection:
        tables = set(connection.dialect.get_table_names(connection))

    assert {"discussions", "participants", "utterances", "insights"} <= tables


def test_when_foreign_keys_are_enabled_then_invalid_participant_is_rejected(
    database_url: str,
) -> None:
    engine = create_sqlite_engine(database_url)
    initialize_database(engine, seed=False)

    with Session(engine) as session:
        session.add(
            Participant(
                id="participant-without-discussion",
                discussion_id="missing-discussion",
                role="expert",
                name="测试专家",
                profession="研究员",
                title="测试职位",
                stance="测试立场",
                color="#123456",
                runtime_status="idle",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_when_utterance_participant_belongs_to_another_discussion_then_insert_is_rejected(
    database_url: str,
) -> None:
    engine = create_sqlite_engine(database_url)
    initialize_database(engine, seed=False)
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add_all(
            [
                Discussion(
                    id="discussion-a",
                    topic="讨论 A",
                    expert_count=4,
                    max_public_utterances=15,
                    status="CAST_READY",
                    cast_confirmed=False,
                    summary_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                Discussion(
                    id="discussion-b",
                    topic="讨论 B",
                    expert_count=4,
                    max_public_utterances=15,
                    status="CAST_READY",
                    cast_confirmed=False,
                    summary_status="pending",
                    created_at=now,
                    updated_at=now,
                ),
                Participant(
                    id="participant-a",
                    discussion_id="discussion-a",
                    role="moderator",
                    name="主持人",
                    profession="记者",
                    title="主持人",
                    stance="澄清问题",
                    color="#2563EB",
                    runtime_status="idle",
                ),
            ]
        )
        session.commit()

        session.add(
            Utterance(
                id="cross-discussion-utterance",
                discussion_id="discussion-b",
                participant_id="participant-a",
                sequence=1,
                content="这条发言不应被保存。",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_when_initialized_twice_then_seed_is_not_duplicated_or_overwritten(
    database_url: str,
) -> None:
    engine = create_sqlite_engine(database_url)
    initialize_database(engine, seed=True)

    with Session(engine) as session:
        first_discussion = session.scalar(select(Discussion).order_by(Discussion.id))
        assert first_discussion is not None
        first_discussion_id = first_discussion.id
        first_discussion.topic = "用户自定义主题"
        session.commit()

    initialize_database(engine, seed=True)

    with Session(engine) as session:
        discussions = session.scalars(select(Discussion)).all()
        participant_count = session.scalar(select(func.count()).select_from(Participant))
        assert len(discussions) == 5
        assert participant_count == 25
        assert session.scalar(select(Discussion.topic).where(Discussion.id == first_discussion_id)) == "用户自定义主题"


def test_when_seeded_then_each_discussion_has_one_moderator_and_four_experts(
    database_url: str,
) -> None:
    engine = create_sqlite_engine(database_url)
    initialize_database(engine, seed=True)

    with Session(engine) as session:
        discussions = session.scalars(select(Discussion)).all()
        assert len(discussions) == 5
        for discussion in discussions:
            participants = session.scalars(
                select(Participant).where(Participant.discussion_id == discussion.id)
            ).all()
            assert discussion.status == "CAST_READY"
            assert discussion.cast_confirmed is False
            assert sum(person.role == "moderator" for person in participants) == 1
            assert sum(person.role == "expert" for person in participants) == 4
            assert len({person.color for person in participants}) == 5
            assert {person.stance for person in participants}


def test_when_serializing_contract_dtos_then_only_documented_public_fields_are_exposed() -> None:
    participant = ParticipantDto(
        id="participant-1",
        discussion_id="discussion-1",
        role="expert",
        name="测试专家",
        profession="研究员",
        title="测试职位",
        stance="测试立场",
        color="#123456",
        runtime_status="idle",
        public_focus=None,
    )
    error = ErrorResponse(error={"code": "INVALID_TOPIC", "message": "话题不能为空"})

    assert DiscussionStatus.CAST_READY == "CAST_READY"
    assert participant.model_dump()["runtime_status"] == "idle"
    assert error.model_dump() == {
        "error": {"code": "INVALID_TOPIC", "message": "话题不能为空", "details": {}}
    }
