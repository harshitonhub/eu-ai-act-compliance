# Critic stage — deferred as an LLM role

The mandate lists `critic` as one of the role-specific reasoning stages (analyst,
classifier, evidence-assessor, critic, reporter) and notes these "may use the same
underlying model" but warns: "Do not create a multi-agent swarm unless evaluation
demonstrates that it improves outcomes."

For Phase 3, the critic's core job — catching a classifier that cites a requirement it
was never given — is implemented as a **deterministic check**, not a second LLM call:
`src/classification/classify.py:verify_citations` rejects any `cited_requirements` entry
whose `requirement_key` isn't in the retrieved candidate set for that call, and fails the
classification closed to `INSUFFICIENT_INFORMATION` if so. Per `.claude/rules/llm.md`
rule 1 ("Do not use an LLM where deterministic code is more reliable"), string-matching a
citation against a known candidate list is exactly such a case — 100% reliable, no
model variance, no extra latency/cost per classification.

An LLM critic pass would add value for judgment calls a string match can't catch — e.g.
"the classifier's rationale doesn't actually follow from the cited provision's text" or
"the classifier missed an applicable exception it was given." Add `prompts/critic/v1.py`
and wire a second `LLMClient.generate_structured` call into `classify_category` when the
golden/adversarial eval suite (`evals/golden/classification_v1/`) shows citation
verification alone isn't catching enough real failures to justify skipping it — not
before, per the mandate's swarm-avoidance rule.
