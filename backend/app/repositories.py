from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.llm import CastOutput
from app.models import Discussion, Insight, Participant, Utterance


class DiscussionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, discussion: Discussion) -> Discussion:
        self.session.add(discussion)
        self.session.commit()
        self.session.refresh(discussion)
        return discussion

    def get(self, discussion_id: str) -> Discussion | None:
        return self.session.get(Discussion, discussion_id)

    def get_aggregate(
        self, discussion_id: str
    ) -> tuple[Discussion, list[Participant], list[Utterance], list[Insight]] | None:
        discussion = self.get(discussion_id)
        if discussion is None:
            return None
        participants = list(
            self.session.scalars(
                select(Participant)
                .where(Participant.discussion_id == discussion_id)
                .order_by(Participant.created_at, Participant.id)
            )
        )
        utterances = list(
            self.session.scalars(
                select(Utterance)
                .where(Utterance.discussion_id == discussion_id)
                .order_by(Utterance.sequence)
            )
        )
        insights = list(
            self.session.scalars(
                select(Insight)
                .where(Insight.discussion_id == discussion_id, Insight.active.is_(True))
                .order_by(Insight.created_at, Insight.id)
            )
        )
        return discussion, participants, utterances, insights

    def list(self) -> list[Discussion]:
        return list(self.session.scalars(select(Discussion).order_by(Discussion.updated_at.desc())))

    def list_finished_with_pending_summary(self) -> list[Discussion]:
        return list(
            self.session.scalars(
                select(Discussion).where(
                    Discussion.status == "FINISHED",
                    Discussion.summary_status == "pending",
                )
            )
        )

    def participant_count(self, discussion_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Participant).where(
                    Participant.discussion_id == discussion_id
                )
            )
            or 0
        )

    def has_complete_cast(self, discussion: Discussion) -> bool:
        roles = dict(
            self.session.execute(
                select(Participant.role, func.count())
                .where(Participant.discussion_id == discussion.id)
                .group_by(Participant.role)
            ).all()
        )
        return roles == {"moderator": 1, "expert": discussion.expert_count}

    def save(self, discussion: Discussion) -> Discussion:
        self.session.commit()
        self.session.refresh(discussion)
        return discussion

    def replace_cast(self, discussion_id: str, cast: CastOutput) -> Discussion:
        with self.session.begin():
            discussion = self.session.get(Discussion, discussion_id)
            if discussion is None:
                raise LookupError(discussion_id)
            now = datetime.now(UTC)
            self.session.execute(delete(Participant).where(Participant.discussion_id == discussion_id))
            self.session.add_all(
                Participant(
                    id=str(uuid4()),
                    discussion_id=discussion_id,
                    role=candidate.role,
                    name=candidate.name,
                    profession=candidate.profession,
                    title=candidate.title,
                    stance=candidate.stance,
                    color=candidate.color,
                    runtime_status="idle",
                    created_at=now,
                )
                for candidate in cast.participants
            )
            discussion.status = "CAST_READY"
            discussion.cast_confirmed = False
            discussion.cast_confirmed_at = None
            discussion.updated_at = now
        self.session.refresh(discussion)
        return discussion


class ParticipantRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_discussion(self, discussion_id: str) -> list[Participant]:
        return list(
            self.session.scalars(
                select(Participant)
                .where(Participant.discussion_id == discussion_id)
                .order_by(Participant.created_at, Participant.id)
            )
        )

    def get(self, participant_id: str, discussion_id: str) -> Participant | None:
        return self.session.scalar(
            select(Participant).where(
                Participant.id == participant_id,
                Participant.discussion_id == discussion_id,
            )
        )

    def set_runtime_status(
        self,
        participant_id: str,
        discussion_id: str,
        runtime_status: str,
        public_focus: str | None,
    ) -> Participant:
        participant = self.get(participant_id, discussion_id)
        if participant is None:
            raise LookupError(participant_id)
        participant.runtime_status = runtime_status
        participant.public_focus = public_focus
        self.session.commit()
        self.session.refresh(participant)
        return participant


class UtteranceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_discussion(self, discussion_id: str) -> list[Utterance]:
        return list(
            self.session.scalars(
                select(Utterance)
                .where(Utterance.discussion_id == discussion_id)
                .order_by(Utterance.sequence)
            )
        )

    def count(self, discussion_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(Utterance).where(
                    Utterance.discussion_id == discussion_id
                )
            )
            or 0
        )

    def add(self, utterance: Utterance) -> Utterance:
        self.session.add(utterance)
        self.session.commit()
        self.session.refresh(utterance)
        return utterance


class InsightRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_for_discussion(self, discussion_id: str) -> list[Insight]:
        return list(
            self.session.scalars(
                select(Insight)
                .where(Insight.discussion_id == discussion_id, Insight.active.is_(True))
                .order_by(Insight.created_at, Insight.id)
            )
        )

    def replace_active(
        self,
        discussion_id: str,
        insights: list[tuple[str, str]],
        *,
        now: datetime,
    ) -> list[Insight]:
        current = list(
            self.session.scalars(
                select(Insight).where(
                    Insight.discussion_id == discussion_id,
                    Insight.active.is_(True),
                )
            )
        )
        for insight in current:
            insight.active = False
            insight.updated_at = now
        created = [
            Insight(
                id=str(uuid4()),
                discussion_id=discussion_id,
                type=insight_type,
                content=content,
                active=True,
                created_at=now,
                updated_at=now,
            )
            for insight_type, content in insights
        ]
        self.session.add_all(created)
        self.session.commit()
        return created
