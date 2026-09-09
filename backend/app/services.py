from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain import Discussion as DiscussionAggregate
from app.domain import DiscussionRuleViolation
from app.models import Discussion
from app.repositories import DiscussionRepository


class DiscussionNotFound(Exception):
    pass


class DiscussionService:
    def __init__(self, repository: DiscussionRepository) -> None:
        self.repository = repository

    def create(self, topic: str, expert_count: int | None) -> Discussion:
        aggregate = DiscussionAggregate.create(
            topic,
            expert_count=4 if expert_count is None else expert_count,
        )
        now = datetime.now(UTC)
        return self.repository.add(
            Discussion(
                id=str(uuid4()),
                topic=aggregate.topic,
                expert_count=aggregate.expert_count,
                max_public_utterances=aggregate.max_public_utterances,
                status=aggregate.status,
                cast_confirmed=aggregate.cast_confirmed,
                summary_status="pending",
                created_at=now,
                updated_at=now,
            )
        )

    def list(self) -> list[Discussion]:
        return self.repository.list()

    def get(self, discussion_id: str) -> Discussion:
        discussion = self.repository.get(discussion_id)
        if discussion is None:
            raise DiscussionNotFound
        return discussion

    def confirm(self, discussion_id: str) -> Discussion:
        discussion = self.get(discussion_id)
        aggregate = self._aggregate(discussion)
        aggregate.confirm_cast()
        self._require_complete_cast(discussion)
        discussion.cast_confirmed = aggregate.cast_confirmed
        discussion.cast_confirmed_at = datetime.now(UTC)
        discussion.updated_at = discussion.cast_confirmed_at
        return self.repository.save(discussion)

    def start(self, discussion_id: str) -> Discussion:
        discussion = self.get(discussion_id)
        aggregate = self._aggregate(discussion)
        aggregate.start()
        self._require_complete_cast(discussion)
        discussion.status = aggregate.status
        discussion.started_at = datetime.now(UTC)
        discussion.updated_at = discussion.started_at
        return self.repository.save(discussion)

    @staticmethod
    def _aggregate(discussion: Discussion) -> DiscussionAggregate:
        return DiscussionAggregate.rehydrate(
            topic=discussion.topic,
            expert_count=discussion.expert_count,
            max_public_utterances=discussion.max_public_utterances,
            status=discussion.status,
            cast_confirmed=discussion.cast_confirmed,
        )

    def _require_complete_cast(self, discussion: Discussion) -> None:
        if not self.repository.has_complete_cast(discussion):
            raise DiscussionRuleViolation(
                "DISCUSSION_STATE_CONFLICT", "当前讨论的阵容不完整，无法执行此操作。"
            )
