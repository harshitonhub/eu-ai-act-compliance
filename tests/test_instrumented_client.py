import pytest
from pydantic import BaseModel

from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient, StructuredOutputError
from src.observability.instrumented_client import InstrumentedLLMClient


class Greeting(BaseModel):
    message: str


def test_successful_call_is_recorded():
    inner = LLMClient(FakeCompletionProvider(['{"message": "hi"}']), model="fake-model")
    instrumented = InstrumentedLLMClient(inner)

    result, _metadata = instrumented.generate_structured(
        system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
    )

    assert result.message == "hi"
    assert len(instrumented.call_records) == 1
    record = instrumented.call_records[0]
    assert record.succeeded is True
    assert record.provider == "fake"
    assert record.prompt_version == "v1"
    assert record.response_model_name == "Greeting"
    assert record.latency_ms >= 0


def test_failed_call_is_recorded_and_still_raises():
    inner = LLMClient(FakeCompletionProvider(["not json", "still not json"]), model="fake-model")
    instrumented = InstrumentedLLMClient(inner)

    with pytest.raises(StructuredOutputError):
        instrumented.generate_structured(
            system_prompt="sys", user_prompt="user", response_model=Greeting, prompt_version="v1"
        )

    assert len(instrumented.call_records) == 1
    record = instrumented.call_records[0]
    assert record.succeeded is False
    assert record.error is not None


def test_multiple_calls_accumulate_records():
    inner = LLMClient(FakeCompletionProvider(['{"message": "a"}', '{"message": "b"}']), model="fake-model")
    instrumented = InstrumentedLLMClient(inner)

    instrumented.generate_structured(system_prompt="s", user_prompt="u1", response_model=Greeting, prompt_version="v1")
    instrumented.generate_structured(system_prompt="s", user_prompt="u2", response_model=Greeting, prompt_version="v1")

    assert len(instrumented.call_records) == 2
