from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DiscussionRuleViolation(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class Discussion:
    topic: str
    expert_count: int
    max_public_utterances: int
    status: str
    cast_confirmed: bool

    @classmethod
    def create(cls, topic: str, *, expert_count: int = 4) -> Discussion:
        normalized_topic = topic.strip()
        if not 1 <= len(normalized_topic) <= 300:
            raise DiscussionRuleViolation("INVALID_TOPIC", "讨论话题必须为 1 到 300 个字符。")
        if not 2 <= expert_count <= 8:
            raise DiscussionRuleViolation("INVALID_EXPERT_COUNT", "专家人数必须在 2 到 8 人之间。")
        return cls(
            topic=normalized_topic,
            expert_count=expert_count,
            max_public_utterances=15,
            status="DRAFT",
            cast_confirmed=False,
        )

    @classmethod
    def rehydrate(
        cls,
        *,
        topic: str,
        expert_count: int,
        max_public_utterances: int,
        status: str,
        cast_confirmed: bool,
    ) -> Discussion:
        return cls(topic, expert_count, max_public_utterances, status, cast_confirmed)

    def confirm_cast(self) -> None:
        self._require_status("CAST_READY")
        if self.cast_confirmed:
            raise DiscussionRuleViolation(
                "DISCUSSION_STATE_CONFLICT", "当前讨论的阵容已经确认。"
            )
        self.cast_confirmed = True

    def start(self) -> None:
        self._require_status("CAST_READY")
        if not self.cast_confirmed:
            raise DiscussionRuleViolation(
                "DISCUSSION_STATE_CONFLICT", "必须先确认阵容才能开始讨论。"
            )
        self.status = "RUNNING"

    def finish(self) -> None:
        self._require_status("RUNNING")
        self.status = "FINISHED"

    def fail(self) -> None:
        self._require_status("RUNNING")
        self.status = "FAILED"

    def _require_status(self, required_status: str) -> None:
        if self.status != required_status:
            raise DiscussionRuleViolation(
                "DISCUSSION_STATE_CONFLICT",
                "当前讨论状态不允许此操作。",
                details={
                    "current_status": self.status,
                    "required_status": required_status,
                },
            )
