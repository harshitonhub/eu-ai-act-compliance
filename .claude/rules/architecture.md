# Architecture Rules

- Prefer a modular monolith with explicit domain boundaries.
- Separate legal knowledge, retrieval, classification, evidence, reporting, evaluation, and infrastructure.
- Keep domain logic independent from framework and provider-specific code.
- Use explicit interfaces for LLM providers, retrieval, storage, and external services.
- Do not introduce microservices, queues, vector databases, agent swarms, or other infrastructure unless a demonstrated requirement justifies them.
- Keep orchestration visible and testable.
- Deterministic business rules must not be delegated to an LLM.
- Record important architectural decisions in documentation.
- Design for tenant isolation and future horizontal scaling without premature distribution.
