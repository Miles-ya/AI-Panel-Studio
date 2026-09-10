from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.main import app
from app.models import Discussion, Participant


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'api-contract.db'}")
    initialize_database(engine, seed=False)
    app.state.session_factory = sessionmaker(bind=engine)
    try:
        yield engine
    finally:
        del app.state.session_factory
        engine.dispose()


@pytest.fixture()
def draft_discussion_id(database_engine: Engine) -> str:
    return _persist_discussion(database_engine, status="DRAFT")


@pytest.fixture()
def cast_ready_discussion_id(database_engine: Engine) -> str:
    return _persist_discussion(database_engine, status="CAST_READY")


@pytest.fixture()
def complete_cast_discussion_id(database_engine: Engine) -> str:
    return _persist_complete_cast(database_engine, cast_confirmed=False)


@pytest.fixture()
def confirmed_complete_cast_discussion_id(database_engine: Engine) -> str:
    return _persist_complete_cast(database_engine, cast_confirmed=True)


def _persist_complete_cast(engine: Engine, *, cast_confirmed: bool) -> str:
    discussion_id = _persist_discussion(
        engine,
        status="CAST_READY",
        cast_confirmed=cast_confirmed,
    )
    now = datetime.now(UTC)

    with Session(engine) as session:
        for role, name, color in (
            ("moderator", "主持人", "#2563EB"),
            ("expert", "专家一", "#F59E0B"),
            ("expert", "专家二", "#10B981"),
            ("expert", "专家三", "#EC4899"),
            ("expert", "专家四", "#8B5CF6"),
        ):
            session.add(
                Participant(
                    id=str(uuid4()),
                    discussion_id=discussion_id,
                    role=role,
                    name=name,
                    profession="研究员",
                    title="测试职位",
                    stance="测试立场",
                    color=color,
                    runtime_status="idle",
                    created_at=now,
                )
            )
        session.commit()

    return discussion_id


def _persist_discussion(
    engine: Engine,
    *,
    status: str,
    cast_confirmed: bool = False,
) -> str:
    discussion_id = str(uuid4())
    now = datetime.now(UTC)

    with Session(engine) as session:
        session.add(
            Discussion(
                id=discussion_id,
                topic="讨论 AI 治理的边界",
                expert_count=4,
                max_public_utterances=15,
                status=status,
                cast_confirmed=cast_confirmed,
                summary_status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    return discussion_id


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


@pytest.mark.anyio
async def test_when_frontend_uses_an_alternate_vite_port_then_api_allows_the_browser_request(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/discussions",
        headers={"Origin": "http://127.0.0.1:5174"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"


@pytest.mark.anyio
async def test_when_request_origin_is_not_localhost_then_api_does_not_grant_cors_access(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/discussions",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("topic", ["   ", "x" * 301])
@pytest.mark.anyio
async def test_when_creating_discussion_with_invalid_topic_then_api_returns_error_dto(
    client: AsyncClient,
    topic: str,
) -> None:
    response = await client.post("/api/discussions", json={"topic": topic})

    assert response.status_code == 422
    _assert_error_shape(response.json(), code="INVALID_TOPIC")


@pytest.mark.anyio
async def test_when_creating_discussion_without_topic_then_api_returns_request_error_dto(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/discussions", json={"expert_count": 4})

    assert response.status_code == 422
    _assert_error_shape(response.json(), code="INVALID_REQUEST")


@pytest.mark.parametrize("expert_count", [0, 1, 9])
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
    draft_discussion_id: str,
) -> None:
    response = await client.post(f"/api/discussions/{draft_discussion_id}/confirm", json={})

    assert response.status_code == 409
    _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")


@pytest.mark.anyio
async def test_when_starting_draft_then_api_returns_documented_state_conflict_details(
    client: AsyncClient,
    draft_discussion_id: str,
) -> None:
    response = await client.post(f"/api/discussions/{draft_discussion_id}/start", json={})

    assert response.status_code == 409
    error = _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")
    assert error["details"] == {
        "current_status": "DRAFT",
        "required_status": "CAST_READY",
    }


@pytest.mark.anyio
async def test_when_confirming_unknown_discussion_then_api_returns_not_found_error_dto(
    client: AsyncClient,
) -> None:
    response = await client.post(f"/api/discussions/{uuid4()}/confirm", json={})

    assert response.status_code == 404
    _assert_error_shape(response.json(), code="DISCUSSION_NOT_FOUND")


@pytest.mark.anyio
async def test_when_starting_unknown_discussion_then_api_returns_not_found_error_dto(
    client: AsyncClient,
) -> None:
    response = await client.post(f"/api/discussions/{uuid4()}/start", json={})

    assert response.status_code == 404
    _assert_error_shape(response.json(), code="DISCUSSION_NOT_FOUND")


@pytest.mark.anyio
async def test_when_confirming_incomplete_cast_then_api_returns_state_conflict_error_dto(
    client: AsyncClient,
    cast_ready_discussion_id: str,
) -> None:
    response = await client.post(f"/api/discussions/{cast_ready_discussion_id}/confirm", json={})

    assert response.status_code == 409
    _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")


@pytest.mark.anyio
async def test_when_confirming_complete_cast_then_api_marks_discussion_confirmed(
    client: AsyncClient,
    complete_cast_discussion_id: str,
) -> None:
    response = await client.post(
        f"/api/discussions/{complete_cast_discussion_id}/confirm",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["cast_confirmed"] is True


@pytest.mark.anyio
async def test_when_starting_confirmed_complete_cast_then_api_marks_discussion_running(
    client: AsyncClient,
    confirmed_complete_cast_discussion_id: str,
) -> None:
    response = await client.post(
        f"/api/discussions/{confirmed_complete_cast_discussion_id}/start",
        json={},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "RUNNING"


@pytest.mark.anyio
async def test_when_starting_confirmed_incomplete_cast_then_api_returns_state_conflict_error_dto(
    client: AsyncClient,
    cast_ready_discussion_id: str,
) -> None:
    with getattr(app.state, "session_factory")() as session:
        discussion = session.get(Discussion, cast_ready_discussion_id)
        assert discussion is not None
        discussion.cast_confirmed = True
        session.commit()

    response = await client.post(f"/api/discussions/{cast_ready_discussion_id}/start", json={})

    assert response.status_code == 409
    _assert_error_shape(response.json(), code="DISCUSSION_STATE_CONFLICT")
