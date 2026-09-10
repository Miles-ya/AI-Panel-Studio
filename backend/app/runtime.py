from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
        discussion_repository: DiscussionRepository,
        participant_repository: ParticipantRepository,
        utterance_repository: UtteranceRepository,
        insight_repository: InsightRepository,
        llm_provider: Any,
        event_hub: EventHub,
        stop_event: asyncio.Event | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.discussion_id = discussion_id
        self.discussion_repository = discussion_repository
        self.participant_repository = participant_repository
        self.utterance_repository = utterance_repository
        self.insight_repository = insight_repository
        self.llm_provider = llm_provider
        self.event_hub = event_hub
        self.stop_event = stop_event or asyncio.Event()
        self.clock = clock or (lambda: datetime.now(UTC))
        self._previous_speaker_id: str | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def status(self) -> str:
        discussion = self.discussion_repository.get(self.discussion_id)
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
                count = self.utterance_repository.count(self.discussion_id)
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
        if self.stop_event.is_set() or self.utterance_repository.count(self.discussion_id) >= 15:
            await self._finish()
            return False

        participants = self.participant_repository.list_for_discussion(self.discussion_id)
        transcript = self.utterance_repository.list_for_discussion(self.discussion_id)
        active_insights = self.insight_repository.active_for_discussion(self.discussion_id)
        public_participants = [PublicParticipant.model_validate(item) for item in participants]
        public_transcript = [PublicUtterance.model_validate(item) for item in transcript]
        public_insights = [PublicInsight.model_validate(item) for item in active_insights]
        discussion = self.discussion_repository.get(self.discussion_id)
        if discussion is None:
            raise LookupError(self.discussion_id)

        selection_input = SpeakerSelectionInput(
            discussion_id=self.discussion_id,
            participants=public_participants,
            transcript=public_transcript,
            active_insights=public_insights,
            public_utterance_count=len(transcript),
            previous_speaker_id=self._previous_speaker_id,
            stop_requested=self.stop_event.is_set(),
        )
        selection = SpeakerSelector(self.llm_provider).select_next_speaker(selection_input)
        selected = next(
            participant for participant in participants if str(participant.id) == str(selection.participant_id)
        )

        await self._set_participant_status(selected, "preparing", selection.public_focus)
        await self._set_participant_status(selected, "speaking", selection.public_focus)

        turn_input = TurnGenerationInput(
            discussion_id=self.discussion_id,
            participants=public_participants,
            transcript=public_transcript,
            active_insights=public_insights,
            selected_participant=PublicParticipant.model_validate(selected),
        )
        turn = TurnGenerator(self.llm_provider).generate_turn(turn_input)
        saved = self.utterance_repository.add(
            Utterance(
                id=str(uuid4()),
                discussion_id=self.discussion_id,
                participant_id=selected.id,
                sequence=self.utterance_repository.count(self.discussion_id) + 1,
                content=turn.content,
                created_at=self.clock(),
            )
        )
        await self.event_hub.publish(
            {
                "type": "utterance.created",
                "discussion_id": self.discussion_id,
                "utterance": {
                    "id": saved.id,
                    "discussion_id": saved.discussion_id,
                    "participant_id": saved.participant_id,
                    "sequence": saved.sequence,
                    "content": saved.content,
                },
            }
        )

        extractor = getattr(self.llm_provider, "extract_insights", None)
        if extractor is not None:
            try:
                output = extractor(saved, active_insights)
                replacement = self._insight_pairs(output)
                replaced = self.insight_repository.replace_active(
                    self.discussion_id, replacement, now=self.clock()
                )
                await self.event_hub.publish(
                    {
                        "type": "insights.updated",
                        "discussion_id": self.discussion_id,
                        "insights": [
                            {
                                "id": item.id,
                                "discussion_id": item.discussion_id,
                                "type": item.type,
                                "content": item.content,
                                "active": item.active,
                            }
                            for item in replaced
                        ],
                    }
                )
            except Exception:
                pass

        await self._set_participant_status(selected, "idle", None)
        self._previous_speaker_id = str(selected.id)
        if turn.should_end or self.stop_event.is_set() or self.utterance_repository.count(self.discussion_id) >= 15:
            await self._finish()
        return True

    async def retry_summary(self) -> None:
        discussion = self.discussion_repository.get(self.discussion_id)
        if discussion is None or discussion.status != "FINISHED" or discussion.summary_status != "fallback":
            raise ValueError("summary retry is only available for finished fallback discussions")
        summary = await self._request_summary()
        if summary is None:
            return
        discussion.summary = summary
        discussion.summary_status = "succeeded"
        discussion.updated_at = self.clock()
        self.discussion_repository.save(discussion)

    async def _set_participant_status(
        self, participant: Participant, runtime_status: str, public_focus: str | None
    ) -> None:
        saved = self.participant_repository.set_runtime_status(
            participant.id,
            self.discussion_id,
            runtime_status,
            public_focus,
        )
        await self.event_hub.publish(
            {
                "type": "participant.status.changed",
                "discussion_id": self.discussion_id,
                "participant": {
                    "id": saved.id,
                    "runtime_status": saved.runtime_status,
                    "public_focus": saved.public_focus,
                },
            }
        )

    async def _finish(self) -> None:
        discussion = self.discussion_repository.get(self.discussion_id)
        if discussion is None or discussion.status != "RUNNING":
            return
        now = self.clock()
        discussion.status = "FINISHED"
        discussion.finished_at = now
        discussion.updated_at = now
        discussion.summary_status = "pending"
        self.discussion_repository.save(discussion)
        summary = await self._request_summary()
        discussion = self.discussion_repository.get(self.discussion_id)
        if discussion is None:
            return
        if summary is None:
            discussion.summary = "总结暂不可用"
            discussion.summary_status = "fallback"
        else:
            discussion.summary = summary
            discussion.summary_status = "succeeded"
        discussion.updated_at = self.clock()
        self.discussion_repository.save(discussion)
        await self.event_hub.publish(
            {
                "type": "discussion.finished",
                "discussion_id": self.discussion_id,
                "status": discussion.status,
                "summary": discussion.summary,
                "summary_status": discussion.summary_status,
                "finished_at": discussion.finished_at,
            }
        )

    async def _request_summary(self) -> str | None:
        summarizer = getattr(self.llm_provider, "summarize", None)
        if summarizer is None:
            return None
        transcript = self.utterance_repository.list_for_discussion(self.discussion_id)
        for _ in range(2):
            try:
                return summarizer(transcript)
            except Exception:
                continue
        return None

    async def _fail(self, error: Exception) -> None:
        discussion = self.discussion_repository.get(self.discussion_id)
        if discussion is None or discussion.status != "RUNNING":
            return
        discussion.status = "FAILED"
        discussion.error_code = "RUNNER_FAILED"
        discussion.updated_at = self.clock()
        self.discussion_repository.save(discussion)
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
            }
        )

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
