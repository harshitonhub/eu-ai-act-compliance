"""Provider-agnostic structured-output LLM client.

Per .claude/rules/llm.md: "Use structured outputs with explicit schemas. Validate and
reject malformed outputs." That validate/retry logic lives here, once, so every backend
(Anthropic, fake-for-tests, a future second provider) gets identical behavior instead of
each reimplementing it.

A RawCompletionProvider only has to turn prompts into raw text; LLMClient handles
JSON-schema validation and a single retry with the validation error fed back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class LLMCallMetadata:
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    retried: bool


class StructuredOutputError(Exception):
    """Raised when model output fails schema validation even after one retry.

    Callers (classification/evidence stages) should treat this as grounds for an
    INSUFFICIENT_INFORMATION result, not as a system failure -- never treat model
    confidence as legal certainty (llm.md).
    """

    def __init__(self, response_model: type[BaseModel], raw_output: str, validation_error: ValidationError):
        self.response_model = response_model
        self.raw_output = raw_output
        self.validation_error = validation_error
        super().__init__(
            f"Model output failed to validate against {response_model.__name__}: {validation_error}"
        )


class RawCompletionProvider(ABC):
    """Minimal seam a concrete backend implements: prompts in, raw text + usage out."""

    provider_name: str

    @abstractmethod
    def complete(self, *, system_prompt: str, user_prompt: str, model: str) -> tuple[str, TokenUsage]: ...


_RETRY_INSTRUCTION = (
    "\n\nYour previous response failed schema validation with this error:\n{error}\n"
    "Return ONLY valid JSON matching the requested schema, with no surrounding prose."
)


class LLMClient:
    """Structured-output client wrapping any RawCompletionProvider."""

    def __init__(self, provider: RawCompletionProvider, *, model: str):
        self._provider = provider
        self._model = model

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model(self) -> str:
        return self._model

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        prompt_version: str,
    ) -> tuple[T, LLMCallMetadata]:
        raw_text, usage = self._provider.complete(
            system_prompt=system_prompt, user_prompt=user_prompt, model=self._model
        )
        retried = False
        try:
            validated = response_model.model_validate_json(raw_text)
        except ValidationError as first_error:
            retried = True
            retry_prompt = user_prompt + _RETRY_INSTRUCTION.format(error=first_error)
            raw_text, retry_usage = self._provider.complete(
                system_prompt=system_prompt, user_prompt=retry_prompt, model=self._model
            )
            usage = TokenUsage(
                input_tokens=usage.input_tokens + retry_usage.input_tokens,
                output_tokens=usage.output_tokens + retry_usage.output_tokens,
            )
            try:
                validated = response_model.model_validate_json(raw_text)
            except ValidationError as second_error:
                raise StructuredOutputError(response_model, raw_text, second_error) from second_error

        metadata = LLMCallMetadata(
            provider=self._provider.provider_name,
            model=self._model,
            prompt_version=prompt_version,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            retried=retried,
        )
        return validated, metadata
