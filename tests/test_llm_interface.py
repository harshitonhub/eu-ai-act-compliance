import pytest
from pydantic import BaseModel

from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient, StructuredOutputError


class Greeting(BaseModel):
    message: str


VALID_JSON = '{"message": "hello"}'
INVALID_JSON = '{"message": 123}'  # wrong type, fails schema validation
GARBAGE = "not json at all"


def _client(responses: list[str]) -> tuple[LLMClient, FakeCompletionProvider]:
    provider = FakeCompletionProvider(responses)
    return LLMClient(provider, model="fake-model-v1"), provider


def test_valid_first_response_returns_without_retry():
    client, provider = _client([VALID_JSON])

    result, metadata = client.generate_structured(
        system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
    )

    assert result.message == "hello"
    assert metadata.retried is False
    assert metadata.provider == "fake"
    assert metadata.prompt_version == "v1"
    assert len(provider.calls) == 1


def test_invalid_then_valid_retries_once_and_succeeds():
    client, provider = _client([INVALID_JSON, VALID_JSON])

    result, metadata = client.generate_structured(
        system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
    )

    assert result.message == "hello"
    assert metadata.retried is True
    assert len(provider.calls) == 2
    assert "failed schema validation" in provider.calls[1]["user_prompt"]


def test_invalid_twice_raises_structured_output_error():
    client, _ = _client([GARBAGE, INVALID_JSON])

    with pytest.raises(StructuredOutputError) as exc_info:
        client.generate_structured(
            system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
        )

    assert exc_info.value.response_model is Greeting


def test_token_usage_accumulates_across_retry():
    client, _ = _client([INVALID_JSON, VALID_JSON])

    _, metadata = client.generate_structured(
        system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
    )

    assert metadata.input_tokens > 0
    assert metadata.output_tokens > 0
