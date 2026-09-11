# EU AI Act Compliance — Claude Code Starter Pack

Files included:
- `INITIAL_CLAUDE_CODE_PROMPT.md` — the initial architecture/implementation mandate
- `CLAUDE.md` — persistent project instructions
- `.claude/rules/` — architecture, legal, security, testing, LLM, data, and code-quality rules
- `.claude/skills/` — reusable workflows for legal research, updates, classification, evidence, evaluation, adversarial testing, reporting, and production audits

Copy this directory into the root of your project, or copy the files into the corresponding locations in an existing repository.

## Running locally

```
uv sync --frozen --extra dev
uv run alembic upgrade head
APP_USERNAME=<user> APP_PASSWORD=<password> ANTHROPIC_API_KEY=<key> uv run uvicorn src.api.main:app --reload
```

`APP_USERNAME`/`APP_PASSWORD` gate every assessment route via HTTP Basic Auth (see
`docs/security-model.md`); the server refuses to serve without them. `ANTHROPIC_API_KEY`
is read by the `anthropic` SDK directly — omit it to fail fast at classification time
rather than starting with a broken LLM client.

Run `python scripts/purge_expired_assessments.py` periodically (e.g. via cron) to
enforce the assessment data retention window (default 90 days).
