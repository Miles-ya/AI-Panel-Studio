from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.llm import CastOutput
from app.models import Discussion, Participant


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

    def list(self) -> list[Discussion]:
        return list(self.session.scalars(select(Discussion).order_by(Discussion.updated_at.desc())))

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
