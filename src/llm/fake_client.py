"""Deterministic fake provider for tests. No network calls.

Downstream tests (classification, evidence, evaluation harness) should depend on this,
not on AnthropicCompletionProvider, so CI never requires a live API key.
"""

from __future__ import annotations

from collections import deque

from src.llm.interface import RawCompletionProvider, TokenUsage


class FakeCompletionProvider(RawCompletionProvider):
    provider_name = "fake"

    def __init__(self, responses: list[str]):
        """`responses` are returned in order, one per `complete()` call."""
        self._responses = deque(responses)
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system_prompt: str, user_prompt: str, model: str) -> tuple[str, TokenUsage]:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "model": model})
        if not self._responses:
            raise AssertionError("FakeCompletionProvider ran out of programmed responses")
        raw_text = self._responses.popleft()
        return raw_text, TokenUsage(input_tokens=len(user_prompt) // 4, output_tokens=len(raw_text) // 4)
