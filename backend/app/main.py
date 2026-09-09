from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.domain import DiscussionRuleViolation
from app.llm import CastOutputValidationError, LLMProviderError
from app.repositories import DiscussionRepository
from app.schemas import (
    ConfirmationDto,
    CreateDiscussionRequest,
    DiscussionDto,
    DiscussionListItemDto,
    DiscussionListResponse,
    ErrorBody,
    ErrorResponse,
    StartDiscussionDto,
)
from app.services import DiscussionNotFound, DiscussionService


app = FastAPI(title="AI Panel Studio", version="0.1.0")


def _error_response(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    payload = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "INVALID_REQUEST",
        "请求参数不合法。",
        {"validation_errors": error.errors()},
    )


@app.exception_handler(DiscussionRuleViolation)
async def discussion_rule_violation_handler(_: Request, error: DiscussionRuleViolation) -> JSONResponse:
    status_code = 422 if error.code in {"INVALID_TOPIC", "INVALID_EXPERT_COUNT"} else 409
    return _error_response(status_code, error.code, error.message, error.details)


@app.exception_handler(DiscussionNotFound)
async def discussion_not_found_handler(_: Request, __: DiscussionNotFound) -> JSONResponse:
    return _error_response(404, "DISCUSSION_NOT_FOUND", "未找到指定的讨论。")


@app.exception_handler(CastOutputValidationError)
async def cast_output_validation_handler(_: Request, __: CastOutputValidationError) -> JSONResponse:
    return _error_response(502, "LLM_RESPONSE_VALIDATION_FAILED", "阵容生成结果不合法。")


@app.exception_handler(LLMProviderError)
async def llm_provider_error_handler(_: Request, __: LLMProviderError) -> JSONResponse:
    return _error_response(503, "LLM_PROVIDER_UNAVAILABLE", "阵容生成服务暂不可用。")


def _session_factory() -> sessionmaker[Session]:
    factory = getattr(app.state, "session_factory", None)
    if factory is None:
        engine = create_sqlite_engine(
            os.getenv("DATABASE_URL", "sqlite:///./data/ai_panel_studio.db")
        )
        initialize_database(engine, seed=False)
        factory = sessionmaker(bind=engine)
        app.state.session_factory = factory
    return factory


async def get_session() -> AsyncGenerator[Session, None]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


async def get_discussion_service(session: Session = Depends(get_session)) -> DiscussionService:
    return DiscussionService(DiscussionRepository(session))


@app.post("/api/discussions", response_model=DiscussionDto, status_code=201)
async def create_discussion(
    request: CreateDiscussionRequest,
    service: DiscussionService = Depends(get_discussion_service),
) -> Discussion:
    return service.create(request.topic, request.expert_count)


@app.get("/api/discussions", response_model=DiscussionListResponse)
async def list_discussions(
    service: DiscussionService = Depends(get_discussion_service),
) -> DiscussionListResponse:
    return DiscussionListResponse(
        items=[
            DiscussionListItemDto(
                id=discussion.id,
                topic=discussion.topic,
                expert_count=discussion.expert_count,
                status=discussion.status,
                participant_count=service.repository.participant_count(discussion.id),
                updated_at=discussion.updated_at,
            )
            for discussion in service.list()
        ]
    )


@app.get("/api/discussions/{discussion_id}", response_model=DiscussionDto)
async def get_discussion(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> Discussion:
    return service.get(discussion_id)


@app.post("/api/discussions/{discussion_id}/generate-cast", response_model=DiscussionDto)
async def generate_cast(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> Discussion:
    return service.generate_cast(discussion_id)


@app.post("/api/discussions/{discussion_id}/confirm", response_model=ConfirmationDto)
async def confirm_discussion(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> ConfirmationDto:
    discussion = service.confirm(discussion_id)
    return ConfirmationDto(
        id=discussion.id,
        status=discussion.status,
        cast_confirmed=discussion.cast_confirmed,
        cast_confirmed_at=discussion.cast_confirmed_at,
        studio_path=f"/discussions/{discussion.id}",
    )


@app.post("/api/discussions/{discussion_id}/start", response_model=StartDiscussionDto, status_code=202)
async def start_discussion(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> StartDiscussionDto:
    discussion = service.start(discussion_id)
    return StartDiscussionDto(
        id=discussion.id,
        status=discussion.status,
        started_at=discussion.started_at,
    )
