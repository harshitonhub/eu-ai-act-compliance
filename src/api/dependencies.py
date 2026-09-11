from __future__ import annotations

import os

from src.llm import LLMClient
from src.llm.anthropic_client import AnthropicCompletionProvider

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


def get_llm_client() -> LLMClient:
    return LLMClient(AnthropicCompletionProvider(), model=DEFAULT_MODEL)
