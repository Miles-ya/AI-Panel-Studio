from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LLMProviderError(Exception):
    """The configured model provider could not produce a response."""


class CastOutputValidationError(Exception):
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


class LLMProvider(Protocol):
    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput | list[dict[str, str]]:
        ...


class FakeLLMProvider:
    """Deterministic provider for tests and local demonstrations."""

    def __init__(self, responses: list[CastOutput | list[dict[str, str]] | Exception]) -> None:
        self._responses = iter(responses)

    def generate_cast(
        self, topic: str, expert_count: int, correction: str | None = None
    ) -> CastOutput | list[dict[str, str]]:
        del topic, expert_count, correction
        response = next(self._responses)
        if isinstance(response, Exception):
            raise response
        return response


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
                timeout=30.0,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return CastOutput.from_provider_response(json.loads(content))
        except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise LLMProviderError("DeepSeek cast generation failed.") from error
