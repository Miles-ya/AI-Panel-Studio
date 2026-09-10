from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain import Discussion as DiscussionAggregate
from app.domain import DiscussionRuleViolation
from app.llm import (
    CastOutput,
    CastOutputValidationError,
    DeepSeekLLMProvider,
    LLMProvider,
    LLMProviderError,
    SpeakerSelectionInput,
    SpeakerSelectionOutput,
    SpeakerSelectionOutputValidationError,
    TurnGenerationInput,
    TurnOutput,
    TurnOutputValidationError,
)
from app.models import Discussion
from app.repositories import DiscussionRepository


class DiscussionNotFound(Exception):
    pass


class SpeakerSelector:
    """Coordinates provider output parsing, domain validation, and one correction retry."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    def select_next_speaker(self, input: SpeakerSelectionInput) -> SpeakerSelectionOutput:
        correction: str | None = None
        for attempt in range(2):
            try:
                candidate = SpeakerSelectionOutput.from_provider_response(
                    self.llm_provider.select_next_speaker(input, correction=correction)
                )
                candidate.validate_for(
                    str(input.discussion_id),
                    input.participants,
                    str(input.previous_speaker_id) if input.previous_speaker_id else None,
                    input.public_utterance_count,
                    input.stop_requested,
                )
                return candidate
            except SpeakerSelectionOutputValidationError as error:
                if attempt == 1:
                    raise
                correction = error.correction
        raise AssertionError("unreachable")


class TurnGenerator:
    """Coordinates TurnOutput parsing and one correction retry."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider

    def generate_turn(self, input: TurnGenerationInput) -> TurnOutput:
        correction: str | None = None
        for attempt in range(2):
            try:
                return TurnOutput.from_provider_response(
                    self.llm_provider.generate_turn(input, correction=correction)
                )
            except TurnOutputValidationError as error:
                if attempt == 1:
                    raise
                correction = error.correction
        raise AssertionError("unreachable")


class DiscussionService:
    def __init__(self, repository: DiscussionRepository, llm_provider: LLMProvider | None = None) -> None:
        self.repository = repository
        self.llm_provider = llm_provider or DeepSeekLLMProvider()

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

    def generate_cast(self, discussion_id: str) -> Discussion:
        discussion = self.get(discussion_id)
        if discussion.status not in {"DRAFT", "CAST_READY"}:
            raise DiscussionRuleViolation(
                "DISCUSSION_STATE_CONFLICT",
                "当前讨论状态不允许生成阵容。",
                details={"current_status": discussion.status, "required_statuses": ["DRAFT", "CAST_READY"]},
            )
        topic, expert_count = discussion.topic, discussion.expert_count
        self.repository.session.rollback()
        cast = self._generate_valid_cast(topic, expert_count)
        return self.repository.replace_cast(discussion_id, cast)

    def _generate_valid_cast(self, topic: str, expert_count: int) -> CastOutput:
        try:
            candidate = CastOutput.from_provider_response(
                self._request_cast(topic, expert_count)
            )
            candidate.validate_for(expert_count)
            return candidate
        except CastOutputValidationError as first_error:
            corrected = CastOutput.from_provider_response(
                self._request_cast(topic, expert_count, correction=first_error.correction)
            )
            corrected.validate_for(expert_count)
            return corrected

    def _request_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput | list[dict[str, str]]:
        try:
            return self.llm_provider.generate_cast(topic, expert_count, correction=correction)
        except LLMProviderError:
            raise
        except Exception as error:
            raise LLMProviderError("Cast provider failed.") from error

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
