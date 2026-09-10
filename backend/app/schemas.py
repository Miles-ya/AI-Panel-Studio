from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DiscussionStatus(str, Enum):
    DRAFT = "DRAFT"
    CAST_READY = "CAST_READY"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class ParticipantRole(str, Enum):
    MODERATOR = "moderator"
    EXPERT = "expert"


class RuntimeStatus(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    SPEAKING = "speaking"


class InsightType(str, Enum):
    CONSENSUS = "consensus"
    DISAGREEMENT = "disagreement"


class ErrorBody(ContractModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    error: ErrorBody


class ParticipantDto(ContractModel):
    id: str
    discussion_id: str
    role: ParticipantRole
    name: str
    profession: str
    title: str
    stance: str
    color: str
    runtime_status: RuntimeStatus
    public_focus: str | None


class UtteranceDto(ContractModel):
    id: str
    discussion_id: str
    participant_id: str
    sequence: int
    content: str
    created_at: datetime


class InsightDto(ContractModel):
    id: str
    discussion_id: str
    type: InsightType
    content: str
    active: bool
    created_at: datetime
    updated_at: datetime


class DiscussionDto(ContractModel):
    id: str
    topic: str
    expert_count: int
    max_public_utterances: int
    status: DiscussionStatus
    cast_confirmed: bool
    cast_confirmed_at: datetime | None
    summary: str | None
    summary_status: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    participants: list[ParticipantDto] = Field(default_factory=list)
    utterances: list[UtteranceDto] = Field(default_factory=list)
    insights: list[InsightDto] = Field(default_factory=list)


class CreateDiscussionRequest(ContractModel):
    topic: str
    expert_count: int | None = None


class DiscussionListItemDto(ContractModel):
    id: str
    topic: str
    expert_count: int
    status: DiscussionStatus
    participant_count: int
    updated_at: datetime


class DiscussionListResponse(ContractModel):
    items: list[DiscussionListItemDto]


class ConfirmationDto(ContractModel):
    id: str
    status: DiscussionStatus
    cast_confirmed: bool
    cast_confirmed_at: datetime | None
    studio_path: str


class StartDiscussionDto(ContractModel):
    id: str
    status: DiscussionStatus
    started_at: datetime | None


class StopDiscussionDto(ContractModel):
    id: str
    status: DiscussionStatus
    stop_requested: bool


class RetrySummaryDto(ContractModel):
    id: str
    status: DiscussionStatus
    summary_status: str
    retry_requested: bool
