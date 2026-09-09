from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _assert_error_shape(response_body: dict[str, Any], *, code: str) -> dict[str, Any]:
    assert set(response_body) == {"error"}
    error = response_body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    assert error["message"]
    assert isinstance(error["details"], dict)
    return error


@pytest.mark.anyio
async def test_when_creating_discussion_then_api_returns_normalized_draft_defaults(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/discussions",
        json={"topic": "  AI 应如何参与公共决策？  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "AI 应如何参与公共决策？"
    assert body["expert_count"] == 4
    assert body["max_public_utterances"] == 15
    assert body["status"] == "DRAFT"


@pytest.mark.parametrize("topic", ["   ", "x" * 301])
@pytest.mark.anyio
async def test_when_creating_discussion_with_invalid_topic_then_api_returns_error_dto(
    client: AsyncClient,
    topic: str,
) -> None:
    response = await client.post("/api/discussions", json={"topic": topic})

    assert response.status_code == 422
    _assert_error_shape(response.json(), code="INVALID_TOPIC")


@pytest.mark.parametrize("expert_count", [1, 9])
@pytest.mark.anyio
async def test_when_creating_discussion_outside_expert_range_then_api_returns_error_dto(
    client: AsyncClient,
    expert_count: int,
) -> None:
    response = await client.post(
        "/api/discussions",
        json={"topic": "讨论 AI 治理", "expert_count": expert_count},
    )

    assert response.status_code == 422
    _assert_error_shape(response.json(), code="INVALID_EXPERT_COUNT")


@pytest.mark.anyio
async def test_when_confirming_draft_then_api_returns_state_conflict_error_dto(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/discussions/discussion-in-draft/confirm", json={})

    assert response.status_code == 409
    _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")


@pytest.mark.anyio
async def test_when_starting_draft_then_api_returns_documented_state_conflict_details(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/discussions/discussion-in-draft/start", json={})

    assert response.status_code == 409
    error = _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")
    assert error["details"] == {
        "current_status": "DRAFT",
        "required_status": "CAST_READY",
    }
