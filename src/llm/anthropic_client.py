"""Anthropic-backed RawCompletionProvider. The only module that imports the `anthropic`
SDK, so a provider swap or SDK-version bump never touches LLMClient or callers.
"""

from __future__ import annotations

from anthropic import Anthropic

from src.llm.interface import RawCompletionProvider, TokenUsage

DEFAULT_MAX_TOKENS = 4096


class AnthropicCompletionProvider(RawCompletionProvider):
    provider_name = "anthropic"

    def __init__(self, api_key: str | None = None, *, max_tokens: int = DEFAULT_MAX_TOKENS):
        self._client = Anthropic(api_key=api_key)
        self._max_tokens = max_tokens

    def complete(self, *, system_prompt: str, user_prompt: str, model: str) -> tuple[str, TokenUsage]:
        response = self._client.messages.create(
            model=model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return text, usage
