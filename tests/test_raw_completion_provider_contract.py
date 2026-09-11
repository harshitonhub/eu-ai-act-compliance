"""One contract, run against every RawCompletionProvider implementation, per Phase 2 DoD:
both the fake and Anthropic-backed providers must satisfy the same interface shape.
"""

from unittest.mock import MagicMock

import pytest

from src.llm.anthropic_client import AnthropicCompletionProvider
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import RawCompletionProvider, TokenUsage


def _fake_provider() -> FakeCompletionProvider:
    return FakeCompletionProvider(responses=["some raw output"])


def _anthropic_provider() -> AnthropicCompletionProvider:
    provider = AnthropicCompletionProvider(api_key="test-key")
    fake_response = MagicMock()
    fake_response.content = [MagicMock(type="text", text="some raw output")]
    fake_response.usage = MagicMock(input_tokens=7, output_tokens=3)
    provider._client.messages.create = MagicMock(return_value=fake_response)
    return provider


@pytest.mark.parametrize("make_provider", [_fake_provider, _anthropic_provider])
def test_provider_satisfies_raw_completion_contract(make_provider):
    provider = make_provider()

    assert isinstance(provider, RawCompletionProvider)
    assert isinstance(provider.provider_name, str) and provider.provider_name

    text, usage = provider.complete(system_prompt="sys", user_prompt="user", model="some-model")

    assert text == "some raw output"
    assert isinstance(usage, TokenUsage)
    assert usage.input_tokens >= 0
    assert usage.output_tokens >= 0
