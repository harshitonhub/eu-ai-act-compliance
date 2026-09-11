# Testing Rules

Testing layers:
- Unit tests for deterministic domain logic.
- Integration tests for retrieval, persistence, orchestration, and external boundaries.
- Contract tests for schemas and provider interfaces.
- Evaluation tests for LLM classification, grounding, evidence assessment, and reporting.
- Adversarial tests for prompt injection and malicious or misleading documents.
- Regression tests against a versioned golden dataset.

Any change to prompts, models, retrieval, legal knowledge, schemas, or classification logic should trigger the relevant evaluation suite.

Prefer tests that expose failure modes rather than tests that merely increase coverage numbers.
