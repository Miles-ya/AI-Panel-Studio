from __future__ import annotations

import os
import json
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from app.database import create_sqlite_engine, initialize_database
from app.domain import DiscussionRuleViolation
from app.environment import load_local_environment
from app.llm import CastOutputValidationError, DeepSeekLLMProvider, DemoLLMProvider, LLMProviderError
from app.repositories import DiscussionRepository
from app.runtime import DiscussionRunner, EventHub, RunnerRegistry, SummaryGenerationService, SummaryTaskRegistry
from app.schemas import (
    ConfirmationDto,
    CreateDiscussionRequest,
    DiscussionDto,
    DiscussionListItemDto,
    DiscussionListResponse,
    ErrorBody,
    ErrorResponse,
    RetrySummaryDto,
    StartDiscussionDto,
    StopDiscussionDto,
)
from app.services import DiscussionNotFound, DiscussionService


load_local_environment()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    recovered = _summary_service().recover_interrupted()
    if recovered:
        logger.warning("summary_tasks_recovered count=%s", recovered)
    yield


app = FastAPI(title="AI Panel Studio", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(?:127\.0\.0\.1|localhost):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _event_hub() -> EventHub:
    hub = getattr(app.state, "event_hub", None)
    if hub is None:
        hub = EventHub()
        app.state.event_hub = hub
    return hub


def _runner_registry() -> RunnerRegistry:
    registry = getattr(app.state, "runner_registry", None)
    if registry is None:
        registry = RunnerRegistry()
        app.state.runner_registry = registry
    return registry


def _summary_service() -> SummaryGenerationService:
    service = getattr(app.state, "summary_service", None)
    if service is None:
        service = SummaryGenerationService(
            session_factory=_session_factory(),
            llm_provider=_llm_provider(),
            event_hub=_event_hub(),
        )
        app.state.summary_service = service
    return service


def _summary_task_registry() -> SummaryTaskRegistry:
    registry = getattr(app.state, "summary_task_registry", None)
    if registry is None:
        registry = SummaryTaskRegistry()
        app.state.summary_task_registry = registry
    return registry


async def _schedule_summary(discussion_id: str) -> None:
    service = _summary_service()
    try:
        await _summary_task_registry().start(discussion_id, service.generate)
    except Exception as error:
        logger.warning(
            "summary_task_start_failed discussion_id=%s error_type=%s",
            discussion_id,
            type(error).__name__,
        )
        await service.mark_fallback(discussion_id)


def _llm_provider() -> DeepSeekLLMProvider | DemoLLMProvider:
    provider = getattr(app.state, "llm_provider", None)
    if provider is None:
        if os.getenv("LLM_PROVIDER", "deepseek").lower() == "fake":
            provider = DemoLLMProvider(summary_mode=os.getenv("FAKE_LLM_SUMMARY_MODE", "success"))
        else:
            provider = DeepSeekLLMProvider()
        app.state.llm_provider = provider
    return provider


def _new_runner(discussion_id: str) -> DiscussionRunner:
    return DiscussionRunner(
        discussion_id=discussion_id,
        session_factory=_session_factory(),
        llm_provider=_llm_provider(),
        event_hub=_event_hub(),
        summary_service=_summary_service(),
        schedule_summary=_schedule_summary,
    )


def _snapshot(discussion_id: str) -> DiscussionDto:
    session = _session_factory()()
    try:
        return DiscussionService(DiscussionRepository(session)).snapshot(discussion_id)
    finally:
        session.close()


def _sse_frame(event_name: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(jsonable_encoder(payload), ensure_ascii=False)}\n\n"
    ).encode()


async def get_session() -> AsyncGenerator[Session, None]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


async def get_discussion_service(session: Session = Depends(get_session)) -> DiscussionService:
    return DiscussionService(DiscussionRepository(session), llm_provider=_llm_provider())


@app.post("/api/discussions", response_model=DiscussionDto, status_code=201)
async def create_discussion(
    request: CreateDiscussionRequest,
    service: DiscussionService = Depends(get_discussion_service),
) -> DiscussionDto:
    discussion = service.create(request.topic, request.expert_count)
    return service.snapshot(discussion.id)


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
) -> DiscussionDto:
    return service.snapshot(discussion_id)


@app.post("/api/discussions/{discussion_id}/generate-cast", response_model=DiscussionDto)
async def generate_cast(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> DiscussionDto:
    discussion = service.generate_cast(discussion_id)
    return service.snapshot(discussion.id)


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
    try:
        await _runner_registry().start(_new_runner(discussion_id))
    except Exception as error:
        discussion.status = "FAILED"
        discussion.error_code = "RUNNER_START_FAILED"
        service.repository.save(discussion)
        raise LLMProviderError("讨论运行器启动失败。") from error
    return StartDiscussionDto(
        id=discussion.id,
        status=discussion.status,
        started_at=discussion.started_at,
    )


@app.post("/api/discussions/{discussion_id}/stop", response_model=StopDiscussionDto, status_code=202)
async def stop_discussion(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> StopDiscussionDto:
    discussion = service.get(discussion_id)
    if discussion.status != "RUNNING":
        raise DiscussionRuleViolation("DISCUSSION_STATE_CONFLICT", "当前讨论未在运行。")
    runner = _runner_registry().get(discussion_id)
    if runner is None:
        raise LLMProviderError("讨论运行器不可用。")
    runner.request_stop()
    return StopDiscussionDto(id=discussion.id, status=discussion.status, stop_requested=True)


@app.post("/api/discussions/{discussion_id}/retry-summary", response_model=RetrySummaryDto, status_code=202)
async def retry_summary(
    discussion_id: str,
    service: DiscussionService = Depends(get_discussion_service),
) -> RetrySummaryDto:
    discussion = service.get(discussion_id)
    if discussion.status != "FINISHED" or discussion.summary_status != "fallback":
        raise DiscussionRuleViolation("DISCUSSION_STATE_CONFLICT", "当前讨论无法重试总结。")
    await _summary_service().begin_retry(discussion_id)
    await _schedule_summary(discussion_id)
    return RetrySummaryDto(id=discussion.id, status=discussion.status, summary_status="pending", retry_requested=True)


@app.get("/api/discussions/{discussion_id}/events")
async def discussion_events(discussion_id: str) -> StreamingResponse:
    snapshot = _snapshot(discussion_id)
    hub = _event_hub()

    async def stream() -> AsyncIterator[bytes]:
        subscription = await hub.subscribe(discussion_id)
        try:
            yield _sse_frame(
                "discussion.snapshot",
                {"discussion_id": discussion_id, "discussion": snapshot.model_dump(mode="json")},
            )
            async for event in subscription:
                yield _sse_frame(str(event["type"]), event)
        finally:
            hub.unsubscribe(discussion_id, subscription)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
