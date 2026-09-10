from types import SimpleNamespace


def test_demo_provider_keeps_summary_fallback_attempts_isolated_per_discussion() -> None:
    """A summary retry in one demo discussion must not consume another's scenario."""
    from app.llm import DemoLLMProvider

    provider = DemoLLMProvider(summary_mode="fallback_once")
    discussion_a = [SimpleNamespace(discussion_id="discussion-a")]
    discussion_b = [SimpleNamespace(discussion_id="discussion-b")]

    assert provider.summarize(discussion_a) is None
    assert provider.summarize(discussion_b) is None
    assert provider.summarize(discussion_a) == "讨论已收束：应以可验证的行动作为下一步。"
    assert provider.summarize(discussion_b) == "讨论已收束：应以可验证的行动作为下一步。"
