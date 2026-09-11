# LLM Rules

- Do not use an LLM where deterministic code is more reliable.
- Use targeted context rather than dumping the legal corpus into prompts.
- Retrieve authoritative sources with metadata and provenance.
- Prefer hybrid retrieval: semantic retrieval plus exact article/annex/identifier lookup where useful.
- Use structured outputs with explicit schemas.
- Validate and reject malformed outputs.
- Keep prompts modular and high-signal.
- Use role-specific stages such as analyst, classifier, evidence assessor, critic, and reporter when separation improves reliability.
- These roles may use the same underlying model.
- Never treat model confidence as legal certainty.
- Record model, prompt, retrieval, and knowledge versions for reproducibility.
- Evaluate before changing prompts or models in production.
