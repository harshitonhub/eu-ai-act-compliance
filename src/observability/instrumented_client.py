"""Wraps an LLMClient to record an LLMCallRecord for every generate_structured call,
success or failure, without touching classify.py/assess.py at all.

Deliberately a decorator over the client, not a change to classify_category/
assess_evidence's signatures: those are already tested (Phases 3-4) and don't need to
know instrumentation exists. Duck-typed against LLMClient's public interface
(generate_structured/provider_name/model), not a subclass, so it composes with any
future client implementation without inheritance coupling.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import TypeVar

from pydantic import BaseModel

from src.llm import LLMCallMetadata, LLMClient, StructuredOutputError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMCallRecord:
    timestamp: datetime
    provider: str
    model: str
    prompt_version: str
    response_model_name: str
    succeeded: bool
    input_tokens: int
    output_tokens: int
    retried: bool
    latency_ms: float
    error: str | None = None


class InstrumentedLLMClient:
    def __init__(self, inner: LLMClient):
        self._inner = inner
        self.call_records: list[LLMCallRecord] = []

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        prompt_version: str,
    ) -> tuple[T, LLMCallMetadata]:
        timestamp = datetime.now(UTC)
        start = time.monotonic()
        try:
            result, metadata = self._inner.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                prompt_version=prompt_version,
            )
        except StructuredOutputError as exc:
            self.call_records.append(
                LLMCallRecord(
                    timestamp=timestamp,
                    provider=self._inner.provider_name,
                    model=self._inner.model,
                    prompt_version=prompt_version,
                    response_model_name=response_model.__name__,
                    succeeded=False,
                    input_tokens=0,
                    output_tokens=0,
                    retried=True,
                    latency_ms=(time.monotonic() - start) * 1000,
                    error=str(exc),
                )
            )
            raise

        self.call_records.append(
            LLMCallRecord(
                timestamp=timestamp,
                provider=metadata.provider,
                model=metadata.model,
                prompt_version=metadata.prompt_version,
                response_model_name=response_model.__name__,
                succeeded=True,
                input_tokens=metadata.input_tokens,
                output_tokens=metadata.output_tokens,
                retried=metadata.retried,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        )
        return result, metadata
