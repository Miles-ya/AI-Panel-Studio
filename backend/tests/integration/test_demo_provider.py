from uuid import UUID

from app.llm import DemoLLMProvider, PublicUtterance


def test_demo_provider_keeps_summary_fallback_attempts_isolated_per_discussion() -> None:
    """A summary retry in one demo discussion must not consume another's scenario."""
    provider = DemoLLMProvider(summary_mode="fallback_once")
    discussion_a = [
        PublicUtterance(
            participant_id=UUID("00000000-0000-0000-0000-000000000001"),
            content="讨论 A 的公开发言。",
        )
    ]
    discussion_b = [
        PublicUtterance(
            participant_id=UUID("00000000-0000-0000-0000-000000000002"),
            content="讨论 B 的公开发言。",
        )
    ]

    assert provider.summarize(discussion_a) is None
    assert provider.summarize(discussion_b) is None
    assert provider.summarize(discussion_a) == "讨论已收束：应以可验证的行动作为下一步。"
    assert provider.summarize(discussion_b) == "讨论已收束：应以可验证的行动作为下一步。"


def test_demo_provider_summarizes_the_public_utterances_passed_by_the_runtime() -> None:
    """The fake E2E provider must not require fields omitted from public summary inputs."""
    provider = DemoLLMProvider()
    transcript = [
        PublicUtterance(
            participant_id=UUID("00000000-0000-0000-0000-000000000001"),
            content="一条公开发言。",
        )
    ]

    assert provider.summarize(transcript) == "讨论已收束：应以可验证的行动作为下一步。"
