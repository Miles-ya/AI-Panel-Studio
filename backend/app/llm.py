from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator


class LLMProviderError(Exception):
    """The configured model provider could not produce a response."""


class CastOutputValidationError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))

    @property
    def correction(self) -> str:
        return json.dumps({"validation_errors": self.reasons}, ensure_ascii=False)


class SpeakerSelectionOutputValidationError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))

    @property
    def correction(self) -> str:
        return json.dumps({"validation_errors": self.reasons}, ensure_ascii=False)


class TurnOutputValidationError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))

    @property
    def correction(self) -> str:
        return json.dumps({"validation_errors": self.reasons}, ensure_ascii=False)


class CastMemberOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["moderator", "expert"]
    name: str = Field(min_length=1, max_length=100)
    profession: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=150)
    stance: str = Field(min_length=1, max_length=300)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class CastOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participants: list[CastMemberOutput]

    @classmethod
    def from_provider_response(cls, response: object) -> CastOutput:
        try:
            if isinstance(response, cls):
                return response
            if isinstance(response, Mapping):
                return cls.model_validate(response)
            if isinstance(response, Sequence) and not isinstance(response, (str, bytes)):
                return cls.model_validate({"participants": response})
        except ValidationError as error:
            raise CastOutputValidationError(["invalid_schema"]) from error
        raise CastOutputValidationError(["invalid_schema"])

    def validate_for(self, expert_count: int) -> None:
        moderators = [person for person in self.participants if person.role == "moderator"]
        experts = [person for person in self.participants if person.role == "expert"]
        reasons: list[str] = []
        if len(moderators) != 1:
            reasons.append("expected_one_moderator")
        if len(experts) != expert_count:
            reasons.append("expected_expert_count")
        if len({person.color for person in self.participants}) != len(self.participants):
            reasons.append("duplicate_colors")
        if len({person.stance for person in experts}) < 2:
            reasons.append("insufficient_expert_stances")
        if reasons:
            raise CastOutputValidationError(reasons)


class PublicParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    discussion_id: UUID
    role: Literal["moderator", "expert"]
    name: str = Field(min_length=1, max_length=100)
    profession: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=150)
    stance: str = Field(min_length=1, max_length=300)


class PublicUtterance(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    participant_id: UUID
    content: str = Field(min_length=1, max_length=500)


class PublicInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    type: Literal["consensus", "disagreement"]
    content: str = Field(min_length=1, max_length=300)


class SpeakerSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discussion_id: UUID
    participants: list[PublicParticipant]
    transcript: list[PublicUtterance] = Field(default_factory=list)
    active_insights: list[PublicInsight] = Field(default_factory=list)
    public_utterance_count: int = Field(default=0, ge=0)
    previous_speaker_id: UUID | None = None
    stop_requested: bool = False


class TurnGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discussion_id: UUID
    participants: list[PublicParticipant]
    transcript: list[PublicUtterance] = Field(default_factory=list)
    active_insights: list[PublicInsight] = Field(default_factory=list)
    selected_participant: PublicParticipant
    closing: bool = False


class SpeakerSelectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: UUID
    public_focus: str = Field(min_length=1, max_length=50)

    @field_validator("public_focus", mode="before")
    @classmethod
    def _validate_public_focus(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if "\r" in value or "\n" in value:
            raise ValueError("public_focus_must_not_contain_line_breaks")
        return value.strip()

    @classmethod
    def from_provider_response(cls, response: object) -> SpeakerSelectionOutput:
        try:
            if isinstance(response, cls):
                return response
            if isinstance(response, Mapping):
                return cls.model_validate(response)
        except ValidationError as error:
            raise SpeakerSelectionOutputValidationError(["invalid_schema"]) from error
        raise SpeakerSelectionOutputValidationError(["invalid_schema"])

    def validate_for(
        self,
        discussion_id: str,
        participants: Sequence[Any],
        previous_speaker_id: str | None,
        public_utterance_count: int,
        stop_requested: bool,
    ) -> None:
        reasons: list[str] = []
        selected_id = str(self.participant_id)
        matching = [person for person in participants if str(person.id) == selected_id]
        same_discussion = [
            person for person in participants if str(person.discussion_id) == str(discussion_id)
        ]

        if stop_requested:
            reasons.append("discussion_stopped")
        if public_utterance_count >= 15:
            reasons.append("public_utterance_limit_reached")
        if not matching or not any(str(person.discussion_id) == str(discussion_id) for person in matching):
            reasons.append("participant_not_in_discussion")
        if public_utterance_count == 0 and matching and matching[0].role != "moderator":
            reasons.append("first_turn_must_select_moderator")
        if (
            previous_speaker_id is not None
            and selected_id == str(previous_speaker_id)
            and len([person for person in same_discussion if str(person.id) != str(previous_speaker_id)]) > 0
        ):
            reasons.append("consecutive_speaker")
        if reasons:
            raise SpeakerSelectionOutputValidationError(reasons)


class TurnOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=300)
    should_end: StrictBool

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if "\r" in value or "\n" in value:
            raise ValueError("content_must_not_contain_line_breaks")
        return value.strip()

    @classmethod
    def from_provider_response(cls, response: object) -> TurnOutput:
        try:
            if isinstance(response, cls):
                return response
            if isinstance(response, Mapping):
                return cls.model_validate(response)
        except ValidationError as error:
            raise TurnOutputValidationError(["invalid_schema"]) from error
        raise TurnOutputValidationError(["invalid_schema"])


class LLMProvider(Protocol):
    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput | list[dict[str, str]]:
        ...

    def select_next_speaker(
        self, input: SpeakerSelectionInput, correction: str | None = None
    ) -> SpeakerSelectionOutput | Mapping[str, object]:
        ...

    def generate_turn(
        self, input: TurnGenerationInput, correction: str | None = None
    ) -> TurnOutput | Mapping[str, object]:
        ...


class FakeLLMProvider:
    """Deterministic provider for tests and local demonstrations."""

    def __init__(
        self,
        responses: list[CastOutput | list[dict[str, str]] | Exception],
        *,
        selection_responses: list[SpeakerSelectionOutput | Mapping[str, object] | Exception] | None = None,
        turn_responses: list[TurnOutput | Mapping[str, object] | Exception] | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._selection_responses = iter(selection_responses or [])
        self._turn_responses = iter(turn_responses or [])

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput | list[dict[str, str]]:
        del topic, expert_count, correction
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response

    def select_next_speaker(
        self, input: SpeakerSelectionInput, correction: str | None = None
    ) -> SpeakerSelectionOutput | Mapping[str, object]:
        del input, correction
        response = next(self._selection_responses)
        if isinstance(response, Exception):
            raise response
        return response

    def generate_turn(
        self, input: TurnGenerationInput, correction: str | None = None
    ) -> TurnOutput | Mapping[str, object]:
        del input, correction
        response = next(self._turn_responses)
        if isinstance(response, Exception):
            raise response
        return response


class DemoLLMProvider:
    """A deterministic, discussion-isolated provider for local browser smoke tests."""

    def __init__(self, *, summary_mode: str = "success") -> None:
        self.summary_mode = summary_mode
        self._summary_attempts: dict[str, int] = {}

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput:
        del correction
        palette = ["#2563EB", "#F59E0B", "#10B981", "#EC4899", "#8B5CF6", "#0891B2", "#EA580C", "#4F46E5", "#65A30D"]
        participants = [
            CastMemberOutput(
                role="moderator",
                name="林澄",
                profession="科技记者",
                title="圆桌主持人",
                stance=f"围绕{topic}厘清可验证的行动。",
                color=palette[0],
            )
        ]
        stances = ["优先衡量业务价值", "先设定治理边界", "同步规划人才转岗", "从可逆流程试点", "关注长期公共影响", "建立可审计指标", "控制实施风险", "检验用户实际收益"]
        for index in range(expert_count):
            participants.append(
                CastMemberOutput(
                    role="expert",
                    name=f"专家{index + 1}",
                    profession="策略顾问",
                    title=f"议题研究员 {index + 1}",
                    stance=stances[index],
                    color=palette[index + 1],
                )
            )
        return CastOutput(participants=participants)

    def select_next_speaker(
        self, input: SpeakerSelectionInput, correction: str | None = None
    ) -> SpeakerSelectionOutput:
        del correction
        if input.public_utterance_count == 0:
            participant = next(item for item in input.participants if item.role == "moderator")
        else:
            candidates = [item for item in input.participants if str(item.id) != str(input.previous_speaker_id)]
            participant = candidates[input.public_utterance_count % len(candidates)]
        return SpeakerSelectionOutput(participant_id=participant.id, public_focus="正在提出可验证的下一步")

    def generate_turn(
        self, input: TurnGenerationInput, correction: str | None = None
    ) -> TurnOutput:
        del correction
        turn_number = len(input.transcript) + 1
        return TurnOutput(
            content=f"这是第 {turn_number} 条公开观点：应把分歧转化为可验证的行动。",
            should_end=turn_number >= 3,
        )

    def extract_insights(self, saved: Mapping[str, object], _: object) -> dict[str, list[str]]:
        sequence = int(saved["sequence"])
        return {
            "consensus": ["下一步应当可验证。"],
            "disagreement": ["投入节奏是否应当一次性确定？"] if sequence > 1 else [],
        }

    def summarize(self, transcript: Sequence[Any]) -> str | None:
        discussion_id = str(transcript[0].discussion_id) if transcript else "empty"
        attempts = self._summary_attempts.get(discussion_id, 0)
        self._summary_attempts[discussion_id] = attempts + 1
        if self.summary_mode == "fallback_once" and attempts == 0:
            return None
        return "讨论已收束：应以可验证的行动作为下一步。"


class DeepSeekLLMProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY")
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
        self.timeout_seconds = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput:
        if not self.api_key:
            raise LLMProviderError("DeepSeek API key is not configured.")
        prompt = {
            "topic": topic,
            "expert_count": expert_count,
            "required_schema": {
                "participants": [
                    {"role": "moderator|expert", "name": "string", "profession": "string", "title": "string", "stance": "string", "color": "#RRGGBB"}
                ]
            },
        }
        if correction is not None:
            prompt["correction"] = correction
        for attempt in range(2):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "Return only JSON matching the requested cast schema."},
                            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return CastOutput.from_provider_response(json.loads(content))
            except httpx.TransportError as error:
                if attempt == 0:
                    continue
                raise LLMProviderError("DeepSeek cast generation failed.") from error
            except httpx.HTTPStatusError as error:
                if attempt == 0 and error.response.status_code >= 500:
                    continue
                raise LLMProviderError("DeepSeek cast generation failed.") from error
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise LLMProviderError("DeepSeek cast generation failed.") from error

        raise AssertionError("The retry loop should either return or raise.")

    def select_next_speaker(
        self, input: SpeakerSelectionInput, correction: str | None = None
    ) -> Mapping[str, object]:
        prompt = {
            "discussion_id": str(input.discussion_id),
            "participants": [person.model_dump(mode="json") for person in input.participants],
            "transcript": [item.model_dump(mode="json") for item in input.transcript],
            "active_insights": [item.model_dump(mode="json") for item in input.active_insights],
            "public_utterance_count": input.public_utterance_count,
            "previous_speaker_id": str(input.previous_speaker_id) if input.previous_speaker_id else None,
            "selection_policy": "根据最新观点、分歧和待回应的问题自主选择最能推进讨论的嘉宾。不要按嘉宾列表、座位或轮流顺序选择发言人；优先回应、反驳、补充新证据、追问或收束。",
            "required_schema": {"participant_id": "UUID", "public_focus": "one short public focus, no line breaks, max 50 characters"},
        }
        if correction is not None:
            prompt["correction"] = correction
        return self._request_json(
            prompt,
            system_message="Return only JSON for the next public speaker and one short public focus. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek speaker selection failed.",
        )

    async def async_select_next_speaker(
        self, input: SpeakerSelectionInput, correction: str | None = None
    ) -> Mapping[str, object]:
        prompt = {
            "discussion_id": str(input.discussion_id),
            "participants": [person.model_dump(mode="json") for person in input.participants],
            "transcript": [item.model_dump(mode="json") for item in input.transcript],
            "active_insights": [item.model_dump(mode="json") for item in input.active_insights],
            "public_utterance_count": input.public_utterance_count,
            "previous_speaker_id": str(input.previous_speaker_id) if input.previous_speaker_id else None,
            "selection_policy": "根据最新观点、分歧和待回应的问题自主选择最能推进讨论的嘉宾。不要按嘉宾列表、座位或轮流顺序选择发言人；优先回应、反驳、补充新证据、追问或收束。",
            "required_schema": {"participant_id": "UUID", "public_focus": "one short public focus, no line breaks, max 50 characters"},
        }
        if correction is not None:
            prompt["correction"] = correction
        return await self._request_json_async(
            prompt,
            system_message="Return only JSON for the next public speaker and one short public focus. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek speaker selection failed.",
        )

    def generate_turn(
        self, input: TurnGenerationInput, correction: str | None = None
    ) -> Mapping[str, object]:
        closing_instruction = "Write a 180-280 Chinese-character moderator closing summary covering conclusions, remaining disagreements, and next steps." if input.closing else "Write 1-2 public sentences."
        prompt = {
            "discussion_id": str(input.discussion_id),
            "participants": [person.model_dump(mode="json") for person in input.participants],
            "transcript": [item.model_dump(mode="json") for item in input.transcript],
            "active_insights": [item.model_dump(mode="json") for item in input.active_insights],
            "selected_participant": input.selected_participant.model_dump(mode="json"),
            "closing": input.closing,
            "required_schema": {"content": "180-280 Chinese characters, no line breaks, max 300 characters" if input.closing else "1-2 public sentences, no line breaks, max 300 characters", "should_end": "boolean"},
        }
        if correction is not None:
            prompt["correction"] = correction
        return self._request_json(
            prompt,
            system_message=f"Return only JSON. {closing_instruction} Include whether the discussion should end. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek turn generation failed.",
        )

    async def async_generate_turn(
        self, input: TurnGenerationInput, correction: str | None = None
    ) -> Mapping[str, object]:
        closing_instruction = "Write a 180-280 Chinese-character moderator closing summary covering conclusions, remaining disagreements, and next steps." if input.closing else "Write 1-2 public sentences."
        prompt = {
            "discussion_id": str(input.discussion_id),
            "participants": [person.model_dump(mode="json") for person in input.participants],
            "transcript": [item.model_dump(mode="json") for item in input.transcript],
            "active_insights": [item.model_dump(mode="json") for item in input.active_insights],
            "selected_participant": input.selected_participant.model_dump(mode="json"),
            "closing": input.closing,
            "required_schema": {"content": "180-280 Chinese characters, no line breaks, max 300 characters" if input.closing else "1-2 public sentences, no line breaks, max 300 characters", "should_end": "boolean"},
        }
        if correction is not None:
            prompt["correction"] = correction
        return await self._request_json_async(
            prompt,
            system_message=f"Return only JSON. {closing_instruction} Include whether the discussion should end. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek turn generation failed.",
        )

    def summarize(self, transcript: Sequence[PublicUtterance]) -> str | None:
        if not transcript:
            return None
        response = self._request_json(
            {
                "transcript": [item.model_dump(mode="json") for item in transcript],
                "required_schema": {"summary": "a concise Chinese summary, max 500 characters"},
            },
            system_message="Return only JSON with a concise public discussion summary. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek summary generation failed.",
        )
        return self._summary_from_response(response)

    async def async_summarize(self, transcript: Sequence[PublicUtterance]) -> str | None:
        if not transcript:
            return None
        response = await self._request_json_async(
            {
                "transcript": [item.model_dump(mode="json") for item in transcript],
                "required_schema": {"summary": "a concise Chinese summary, max 500 characters"},
            },
            system_message="Return only JSON with a concise public discussion summary. Do not provide reasoning or hidden analysis.",
            error_message="DeepSeek summary generation failed.",
        )
        return self._summary_from_response(response)

    async def async_finalize_insights(
        self, transcript: Sequence[PublicUtterance]
    ) -> Mapping[str, object]:
        return await self._request_json_async(
            {
                "transcript": [item.model_dump(mode="json") for item in transcript],
                "required_schema": {
                    "consensus": "0-2 concise Chinese consensus statements, each max 120 characters",
                    "disagreement": "0-2 concise Chinese disagreement statements, each max 120 characters",
                },
            },
            system_message="Return only JSON with independently generated consensus and disagreement lists for this completed discussion. Do not include a summary, reasoning, or hidden analysis.",
            error_message="DeepSeek final insights generation failed.",
        )

    @staticmethod
    def _summary_from_response(response: Mapping[str, object]) -> str:
        summary = response.get("summary")
        if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 500:
            raise LLMProviderError("DeepSeek summary generation failed.")
        return summary.strip()

    def _request_json(
        self, prompt: dict[str, object], *, system_message: str, error_message: str
    ) -> Mapping[str, object]:
        if not self.api_key:
            raise LLMProviderError("DeepSeek API key is not configured.")
        for attempt in range(2):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                payload = json.loads(content)
                if not isinstance(payload, Mapping):
                    raise TypeError("model response must be an object")
                return payload
            except httpx.TransportError as error:
                if attempt == 0:
                    continue
                raise LLMProviderError(error_message) from error
            except httpx.HTTPStatusError as error:
                if attempt == 0 and error.response.status_code >= 500:
                    continue
                raise LLMProviderError(error_message) from error
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise LLMProviderError(error_message) from error
        raise AssertionError("unreachable")

    async def _request_json_async(
        self, prompt: dict[str, object], *, system_message: str, error_message: str
    ) -> Mapping[str, object]:
        if not self.api_key:
            raise LLMProviderError("DeepSeek API key is not configured.")
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                            ],
                            "response_format": {"type": "json_object"},
                        },
                    )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                payload = json.loads(content)
                if not isinstance(payload, Mapping):
                    raise TypeError("model response must be an object")
                return payload
            except httpx.TransportError as error:
                if attempt == 0:
                    continue
                raise LLMProviderError(error_message) from error
            except httpx.HTTPStatusError as error:
                if attempt == 0 and error.response.status_code >= 500:
                    continue
                raise LLMProviderError(error_message) from error
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise LLMProviderError(error_message) from error
        raise AssertionError("unreachable")
