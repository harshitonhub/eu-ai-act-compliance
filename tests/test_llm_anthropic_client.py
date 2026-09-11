"""Verifies AnthropicCompletionProvider's request/response translation without any
network call, so CI never needs a live API key (per Phase 2 DoD).
"""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from src.llm.anthropic_client import AnthropicCompletionProvider


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]
    usage: _FakeUsage = field(default_factory=lambda: _FakeUsage(10, 5))


def test_complete_extracts_text_and_usage_from_response():
    provider = AnthropicCompletionProvider(api_key="test-key")
    fake_response = _FakeMessage(content=[_FakeTextBlock(text='{"message": "hi"}')])
    provider._client.messages.create = MagicMock(return_value=fake_response)

    text, usage = provider.complete(system_prompt="sys", user_prompt="user", model="claude-x")

    assert text == '{"message": "hi"}'
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5
    provider._client.messages.create.assert_called_once_with(
        model="claude-x",
        max_tokens=4096,
        system="sys",
        messages=[{"role": "user", "content": "user"}],
    )


def test_complete_joins_multiple_text_blocks():
    provider = AnthropicCompletionProvider(api_key="test-key")
    fake_response = _FakeMessage(content=[_FakeTextBlock(text="part1"), _FakeTextBlock(text="part2")])
    provider._client.messages.create = MagicMock(return_value=fake_response)

    text, _ = provider.complete(system_prompt="sys", user_prompt="user", model="claude-x")

    assert text == "part1part2"
