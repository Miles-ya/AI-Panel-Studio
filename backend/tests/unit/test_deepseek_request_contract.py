from uuid import UUID

import httpx

from app.llm import (
    DeepSeekLLMProvider,
    PublicParticipant,
    PublicUtterance,
    SpeakerSelectionInput,
    TurnGenerationInput,
)


def test_turn_request_mentions_json_when_requesting_json_object(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"content":"公开观点。","should_end":false}'}}]}

    def post(*_, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.llm.httpx.post", post)
    participant = PublicParticipant(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        discussion_id=UUID("22222222-2222-2222-2222-222222222222"),
        role="moderator",
        name="公开主持人",
        profession="记者",
        title="主持人",
        stance="公开立场",
    )

    DeepSeekLLMProvider(api_key="test-key").generate_turn(
        TurnGenerationInput(
            discussion_id=participant.discussion_id,
            participants=[participant],
            selected_participant=participant,
        )
    )

    system_message = captured["json"]["messages"][0]["content"]
    assert "json" in system_message.lower()


def test_turn_request_retries_one_transient_transport_failure(monkeypatch) -> None:
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"content":"公开观点。","should_end":false}'}}]}

    def post(*_, **__):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("provider timed out")
        return Response()

    monkeypatch.setattr("app.llm.httpx.post", post)
    participant = PublicParticipant(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        discussion_id=UUID("22222222-2222-2222-2222-222222222222"),
        role="moderator",
        name="公开主持人",
        profession="记者",
        title="主持人",
        stance="公开立场",
    )

    result = DeepSeekLLMProvider(api_key="test-key").generate_turn(
        TurnGenerationInput(
            discussion_id=participant.discussion_id,
            participants=[participant],
            selected_participant=participant,
        )
    )

    assert result["content"] == "公开观点。"
    assert calls == 2


def test_cast_request_retries_one_transient_transport_failure(monkeypatch) -> None:
    calls = 0

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"participants":[{"role":"moderator","name":"主持人","profession":"记者","title":"主持人","stance":"澄清问题","color":"#2563EB"},{"role":"expert","name":"专家一","profession":"研究员","title":"专家","stance":"支持方案","color":"#F59E0B"},{"role":"expert","name":"专家二","profession":"研究员","title":"专家","stance":"审视风险","color":"#10B981"}]}'
                        }
                    }
                ]
            }

    def post(*_, **__):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("provider timed out")
        return Response()

    monkeypatch.setattr("app.llm.httpx.post", post)

    result = DeepSeekLLMProvider(api_key="test-key").generate_cast("测试话题", 2)

    assert len(result.participants) == 3
    assert calls == 2


def test_summary_request_returns_the_model_summary(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"summary":"讨论结论。"}'}}]}

    monkeypatch.setattr("app.llm.httpx.post", lambda *_, **__: Response())

    summary = DeepSeekLLMProvider(api_key="test-key").summarize(
        [
            PublicUtterance(
                participant_id=UUID("11111111-1111-1111-1111-111111111111"),
                content="公开观点。",
            )
        ]
    )

    assert summary == "讨论结论。"


def test_speaker_selection_instructs_the_model_not_to_follow_seat_order(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"participant_id":"33333333-3333-4333-8333-333333333333","public_focus":"回应隐私风险"}'
                        }
                    }
                ]
            }

    def post(*_, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.llm.httpx.post", post)
    discussion_id = UUID("22222222-2222-2222-2222-222222222222")
    moderator = PublicParticipant(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        discussion_id=discussion_id,
        role="moderator",
        name="主持人",
        profession="记者",
        title="主持人",
        stance="推进讨论",
    )
    expert = PublicParticipant(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        discussion_id=discussion_id,
        role="expert",
        name="专家",
        profession="研究员",
        title="专家",
        stance="审视风险",
    )

    DeepSeekLLMProvider(api_key="test-key").select_next_speaker(
        SpeakerSelectionInput(discussion_id=discussion_id, participants=[moderator, expert])
    )

    request_prompt = captured["json"]["messages"][1]["content"]
    assert "不要按嘉宾列表、座位或轮流顺序选择发言人" in request_prompt


def test_closing_turn_requests_a_detailed_moderator_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None: return None
        def json(self) -> dict[str, object]: return {"choices": [{"message": {"content": '{"content":"收束。","should_end":true}'}}]}

    def post(*_, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.llm.httpx.post", post)
    participant = PublicParticipant(id=UUID("11111111-1111-1111-1111-111111111111"), discussion_id=UUID("22222222-2222-2222-2222-222222222222"), role="moderator", name="主持人", profession="记者", title="主持人", stance="收束")
    DeepSeekLLMProvider(api_key="test-key").generate_turn(TurnGenerationInput(discussion_id=participant.discussion_id, participants=[participant], selected_participant=participant, closing=True))

    assert "300-500" in captured["json"]["messages"][0]["content"]
