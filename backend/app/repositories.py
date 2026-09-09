from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
