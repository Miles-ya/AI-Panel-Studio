from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.llm import (
    PublicInsight,
    PublicParticipant,
    PublicUtterance,
    SpeakerSelectionInput,
    TurnGenerationInput,
)
from app.models import Discussion, Participant, Utterance
from app.repositories import (
    DiscussionRepository,
    InsightRepository,
    ParticipantRepository,
    UtteranceRepository,
)
from app.services import SpeakerSelector, TurnGenerator


class _EventSubscription(AsyncIterator[dict[str, Any]]):
    def __init__(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queue = queue

    def __aiter__(self) -> _EventSubscription:
        return self

    async def __anext__(self) -> dict[str, Any]:
        return await self._queue.get()


class EventHub:
    """In-process, per-Discussion event fan-out for the current application process."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def subscribe(self, discussion_id: str) -> _EventSubscription:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(discussion_id, set()).add(queue)
        return _EventSubscription(queue)

    async def publish(self, event: Mapping[str, Any]) -> None:
        discussion_id = str(event["discussion_id"])
        for queue in tuple(self._subscribers.get(discussion_id, ())):
            await queue.put(dict(event))

    def unsubscribe(self, discussion_id: str, subscription: _EventSubscription) -> None:
        queues = self._subscribers.get(discussion_id)
        if queues is None:
            return
        queues.discard(subscription._queue)
        if not queues:
            self._subscribers.pop(discussion_id, None)


class DiscussionRunner:
    def __init__(
        self,
        *,
        discussion_id: str,
        session_factory: sessionmaker[Session],
        llm_provider: Any,
        event_hub: EventHub,
        stop_event: asyncio.Event | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.discussion_id = discussion_id
        self.session_factory = session_factory
        self.llm_provider = llm_provider
        self.event_hub = event_hub
        self.stop_event = stop_event or asyncio.Event()
        self.clock = clock or (lambda: datetime.now(UTC))
        self._previous_speaker_id: str | None = None
        self._closing_requested = False
        self._task: asyncio.Task[None] | None = None

    @property
    def status(self) -> str:
        with self.session_factory() as session:
            discussion = DiscussionRepository(session).get(self.discussion_id)
            return discussion.status if discussion is not None else "UNKNOWN"

    def attach_task(self, task: asyncio.Task[None]) -> None:
        self._task = task

    async def wait_until_done(self) -> None:
        if self._task is not None:
            await self._task

    def request_stop(self) -> None:
        self.stop_event.set()

    async def stop(self) -> None:
        self.request_stop()

    async def run(self) -> None:
        try:
            while self.status == "RUNNING":
                count = self._utterance_count()
                if self.stop_event.is_set() or count >= 15:
                    await self._finish()
                    return
                await self.run_one_turn()
        except Exception as error:
            if self.status == "RUNNING":
                await self._fail(error)

    async def run_one_turn(self) -> bool:
        if self.status != "RUNNING":
            return False
        if self.stop_event.is_set() or self._utterance_count() >= 15:
            await self._finish()
            return False

        with self.session_factory() as session:
            discussion_repository = DiscussionRepository(session)
            participant_repository = ParticipantRepository(session)
            utterance_repository = UtteranceRepository(session)
            insight_repository = InsightRepository(session)
            discussion = discussion_repository.get(self.discussion_id)
            if discussion is None:
                raise LookupError(self.discussion_id)
            participants = participant_repository.list_for_discussion(self.discussion_id)
            transcript = utterance_repository.list_for_discussion(self.discussion_id)
            active_insights = insight_repository.active_for_discussion(self.discussion_id)
            public_participants = [PublicParticipant.model_validate(item) for item in participants]
            public_transcript = [PublicUtterance.model_validate(item) for item in transcript]
            public_insights = [PublicInsight.model_validate(item) for item in active_insights]

        closing = self._closing_requested or len(transcript) >= discussion.max_public_utterances - 1
        if closing:
            selected = next(person for person in public_participants if person.role == "moderator")
            public_focus = "主持收束：总结讨论并保留关键分歧"
        else:
            selection_input = SpeakerSelectionInput(
                discussion_id=self.discussion_id,
                participants=public_participants,
                transcript=public_transcript,
                active_insights=public_insights,
                public_utterance_count=len(transcript),
                previous_speaker_id=self._previous_speaker_id,
                stop_requested=self.stop_event.is_set(),
            )
            selector = SpeakerSelector(self.llm_provider)
            if callable(getattr(self.llm_provider, "async_select_next_speaker", None)):
                selection = await selector.select_next_speaker_async(selection_input)
            else:
                selection = selector.select_next_speaker(selection_input)
            selected = next(person for person in public_participants if str(person.id) == str(selection.participant_id))
            public_focus = selection.public_focus

        await self._set_participant_status(str(selected.id), "preparing", public_focus)
        await self._set_participant_status(str(selected.id), "speaking", public_focus)

        turn_input = TurnGenerationInput(
            discussion_id=self.discussion_id,
            participants=public_participants,
            transcript=public_transcript,
            active_insights=public_insights,
            selected_participant=selected,
            closing=closing,
        )
        generator = TurnGenerator(self.llm_provider)
        if callable(getattr(self.llm_provider, "async_generate_turn", None)):
            turn = await generator.generate_turn_async(turn_input)
        else:
            turn = generator.generate_turn(turn_input)
        saved = self._save_utterance(str(selected.id), turn.content)
        await self.event_hub.publish(
            {
                "type": "utterance.created",
                "discussion_id": self.discussion_id,
                "utterance": {
                    "id": saved["id"],
                    "discussion_id": saved["discussion_id"],
                    "participant_id": saved["participant_id"],
                    "sequence": saved["sequence"],
                    "content": saved["content"],
                    "created_at": saved["created_at"],
                },
            }
        )

        extractor = getattr(self.llm_provider, "extract_insights", None)
        if extractor is not None:
            try:
                output = extractor(saved, active_insights)
                replacement = self._insight_pairs(output)
                replaced = self._replace_insights(replacement)
                await self.event_hub.publish(
                    {
                        "type": "insights.updated",
                        "discussion_id": self.discussion_id,
                        "insights": [
                            {
                                "id": item["id"],
                                "discussion_id": item["discussion_id"],
                                "type": item["type"],
                                "content": item["content"],
                                "active": item["active"],
                                "created_at": item["created_at"],
                                "updated_at": item["updated_at"],
                            }
                            for item in replaced
                        ],
                        "occurred_at": self.clock(),
                    }
                )
            except Exception:
                pass

        await self._set_participant_status(str(selected.id), "idle", None)
        self._previous_speaker_id = str(selected.id)
        if closing or (turn.should_end and selected.role == "moderator"):
            await self._finish(summary=turn.content)
        elif turn.should_end:
            self._closing_requested = True
        elif self.stop_event.is_set() or self._utterance_count() >= 15:
            await self._finish()
        return True

    async def retry_summary(self) -> None:
        with self.session_factory() as session:
            discussion = DiscussionRepository(session).get(self.discussion_id)
            if discussion is None or discussion.status != "FINISHED" or discussion.summary_status != "fallback":
                raise ValueError("summary retry is only available for finished fallback discussions")
        summary = await self._request_summary()
        with self.session_factory() as session:
            discussion = DiscussionRepository(session).get(self.discussion_id)
            if discussion is None:
                return
            if summary is not None:
                discussion.summary = summary
                discussion.summary_status = "succeeded"
                discussion.updated_at = self.clock()
                DiscussionRepository(session).save(discussion)
            event = {
                "type": "discussion.finished",
                "discussion_id": self.discussion_id,
                "status": discussion.status,
                "summary": discussion.summary,
                "summary_status": discussion.summary_status,
                "finished_at": discussion.finished_at,
            }
        await self.event_hub.publish(event)

    async def _set_participant_status(
        self, participant_id: str, runtime_status: str, public_focus: str | None
    ) -> None:
        with self.session_factory() as session:
            saved = ParticipantRepository(session).set_runtime_status(
                participant_id, self.discussion_id, runtime_status, public_focus
            )
            payload = {"id": saved.id, "runtime_status": saved.runtime_status, "public_focus": saved.public_focus}
        await self.event_hub.publish(
            {
                "type": "participant.status.changed",
                "discussion_id": self.discussion_id,
                "participant": payload,
                "occurred_at": self.clock(),
            }
        )

    async def _finish(self, summary: str | None = None) -> None:
        with self.session_factory() as session:
            repository = DiscussionRepository(session)
            discussion = repository.get(self.discussion_id)
            if discussion is None or discussion.status != "RUNNING":
                return
            now = self.clock()
            discussion.status = "FINISHED"
            discussion.finished_at = now
            discussion.updated_at = now
            discussion.summary_status = "pending"
            repository.save(discussion)
        fallback_summary = summary
        summary = await self._request_summary()
        if summary is None:
            summary = fallback_summary
        with self.session_factory() as session:
            repository = DiscussionRepository(session)
            discussion = repository.get(self.discussion_id)
            if discussion is None:
                return
            if summary is None:
                discussion.summary = "总结暂不可用"
                discussion.summary_status = "fallback"
            else:
                discussion.summary = summary
                discussion.summary_status = "succeeded"
            discussion.updated_at = self.clock()
            repository.save(discussion)
            payload = {"status": discussion.status, "summary": discussion.summary, "summary_status": discussion.summary_status, "finished_at": discussion.finished_at}
        await self.event_hub.publish(
            {
                "type": "discussion.finished",
                "discussion_id": self.discussion_id,
                **payload,
            }
        )

    async def _request_summary(self) -> str | None:
        async_summarizer = getattr(self.llm_provider, "async_summarize", None)
        summarizer = getattr(self.llm_provider, "summarize", None)
        if not callable(async_summarizer) and not callable(summarizer):
            return None
        with self.session_factory() as session:
            transcript = UtteranceRepository(session).list_for_discussion(self.discussion_id)
        for _ in range(2):
            try:
                if callable(async_summarizer):
                    return await async_summarizer(transcript)
                return summarizer(transcript)
            except Exception:
                continue
        return None

    async def _fail(self, error: Exception) -> None:
        with self.session_factory() as session:
            repository = DiscussionRepository(session)
            discussion = repository.get(self.discussion_id)
            if discussion is None or discussion.status != "RUNNING":
                return
            discussion.status = "FAILED"
            discussion.error_code = "RUNNER_FAILED"
            discussion.updated_at = self.clock()
            repository.save(discussion)
        await self.event_hub.publish(
            {
                "type": "discussion.error",
                "discussion_id": self.discussion_id,
                "final_status": "FAILED",
                "error": {
                    "code": "RUNNER_FAILED",
                    "message": "本轮讨论生成失败，系统已停止该讨论。",
                    "details": {},
                },
                "occurred_at": self.clock(),
            }
        )

    def _utterance_count(self) -> int:
        with self.session_factory() as session:
            return UtteranceRepository(session).count(self.discussion_id)

    def _save_utterance(self, participant_id: str, content: str) -> dict[str, Any]:
        with self.session_factory() as session:
            repository = UtteranceRepository(session)
            saved = repository.add(Utterance(id=str(uuid4()), discussion_id=self.discussion_id, participant_id=participant_id, sequence=repository.count(self.discussion_id) + 1, content=content, created_at=self.clock()))
            return {"id": saved.id, "discussion_id": saved.discussion_id, "participant_id": saved.participant_id, "sequence": saved.sequence, "content": saved.content, "created_at": saved.created_at}

    def _replace_insights(self, replacement: list[tuple[str, str]]) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            items = InsightRepository(session).replace_active(self.discussion_id, replacement, now=self.clock())
            return [{"id": item.id, "discussion_id": item.discussion_id, "type": item.type, "content": item.content, "active": item.active, "created_at": item.created_at, "updated_at": item.updated_at} for item in items]

    @staticmethod
    def _insight_pairs(output: object) -> list[tuple[str, str]]:
        if not isinstance(output, Mapping):
            raise ValueError("invalid insight output")
        pairs: list[tuple[str, str]] = []
        for insight_type in ("consensus", "disagreement"):
            values = output.get(insight_type, [])
            if not isinstance(values, list) or len(values) > 2:
                raise ValueError("invalid insight collection")
            pairs.extend((insight_type, value) for value in values if isinstance(value, str) and value.strip())
        return pairs


class RunnerRegistry:
    def __init__(self) -> None:
        self._runners: dict[str, DiscussionRunner] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self, runner: DiscussionRunner) -> None:
        lock = self._locks.setdefault(runner.discussion_id, asyncio.Lock())
        async with lock:
            current = self._runners.get(runner.discussion_id)
            if current is not None and current._task is not None and not current._task.done():
                raise RuntimeError("runner already started")
            task = asyncio.create_task(runner.run())
            runner.attach_task(task)
            self._runners[runner.discussion_id] = runner

    def get(self, discussion_id: str) -> DiscussionRunner | None:
        return self._runners.get(discussion_id)
