from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class DiscussionDto(ContractModel):
    id: str
    topic: str
    expert_count: int
    max_public_utterances: int
    status: DiscussionStatus
    cast_confirmed: bool
