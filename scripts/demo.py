"""Run the whole platform locally with no API key and no setup.

    python scripts/demo.py        # then open http://127.0.0.1:8000

Everything runs against an in-memory database that is rebuilt on each start, seeded with
the legal corpus, two tenants, and three users. The LLM is a canned fake, so the
classification and evidence stages complete without an Anthropic key and without
spending anything -- responses are clearly marked [DEMO] wherever they appear in the UI.

This exists because a reviewer should be able to see the system work before deciding
whether to read any of it. It is not a deployment path: `--reload`-style dev serving,
in-memory storage, a fake model, and printed passwords are all fine for a throwaway demo
and none of them are fine in production. See README.md's "Running locally" for the real
thing.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os

os.environ.setdefault("SESSION_SECRET", "demo-only-not-a-real-secret")

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from schemas.enums import IncidentSeverity, UserRole
from src.api.dependencies import get_llm_client
from src.api.main import app
from src.auth.users import create_tenant, create_user
from src.incidents.registry import create_incident
from src.legal.ingest import ingest_seed
from src.llm.interface import LLMClient, RawCompletionProvider, TokenUsage
from src.persistence.db import get_session
from src.persistence.models import Base
from src.persistence.tenancy import tenant_context
from src.systems.registry import get_or_create_ai_system

HOST, PORT = "127.0.0.1", 8000

ACCOUNTS = [
    ("Acme Ltd", "admin@acme.test", "demo-password-1", UserRole.ADMIN),
    ("Acme Ltd", "viewer@acme.test", "demo-password-2", UserRole.VIEWER),
    ("Globex Ltd", "admin@globex.test", "demo-password-3", UserRole.ADMIN),
]

_EVIDENCE_DIMENSIONS = [
    {"dimension": d, "met": True, "note": "[DEMO] assumed met."}
    for d in ("relevance", "completeness", "specificity", "currency",
              "traceability", "consistency", "sufficiency")
]


class DemoProvider(RawCompletionProvider):
    """Canned responses keyed off which schema the caller asked for.

    Deliberately dumb: it recognises a recruitment system and otherwise answers NO. It is
    a stand-in so the UI is explorable, not a model -- every rationale it emits is
    prefixed [DEMO] so nothing it says can be mistaken for a real classification.
    """

    provider_name = "demo-fake"

    def complete(self, *, system_prompt: str, user_prompt: str, model: str):
        if '"CategoryClassification"' in system_prompt:
            return self._classify(user_prompt), TokenUsage(input_tokens=10, output_tokens=10)
        return self._assess_evidence(user_prompt), TokenUsage(input_tokens=10, output_tokens=10)

    @staticmethod
    def _classify(user_prompt: str) -> str:
        category = "scope"
        for line in user_prompt.splitlines():
            if line.startswith("CATEGORY TO ASSESS:"):
                category = line.split(":", 1)[1].strip()
                break
        if category == "high_risk" and "EU-AI-ACT-ANNEXIII-4" in user_prompt:
            return json.dumps({
                "category": "high_risk",
                "state": "YES",
                "cited_requirements": [{
                    "requirement_key": "EU-AI-ACT-ANNEXIII-4",
                    "citation": "Annex III",
                    "relevance": "[DEMO] Recruitment matches Annex III point 4(a).",
                }],
                "rationale": "[DEMO] Recruitment/selection use case matches Annex III point 4(a).",
                "confidence": 0.9,
            })
        return json.dumps({
            "category": category,
            "state": "NO",
            "cited_requirements": [],
            "rationale": f"[DEMO] No indicators found for {category}.",
            "confidence": 0.8,
        })

    @staticmethod
    def _assess_evidence(user_prompt: str) -> str:
        requirement_key = "UNKNOWN"
        for line in user_prompt.splitlines():
            if line.strip().startswith("requirement_key:"):
                requirement_key = line.split(":", 1)[1].strip()
                break
        return json.dumps({
            "requirement_key": requirement_key,
            "status": "PARTIALLY_COMPLIANT",
            "dimensions": _EVIDENCE_DIMENSIONS,
            "rationale": "[DEMO] Placeholder assessment from the fake provider.",
            "contradictions": [],
        })


def _seed(engine) -> None:
    with Session(engine) as session:
        ingest_seed(session)  # legal corpus: shared, not tenant-owned

        tenants: dict[str, str] = {}
        for tenant_name, email, password, role in ACCOUNTS:
            if tenant_name not in tenants:
                tenants[tenant_name] = create_tenant(session, tenant_name).id
            create_user(
                session, tenant_id=tenants[tenant_name], email=email, password=password, role=role
            )

        # One system + one open incident per tenant, so tenant isolation is visible on
        # first load rather than needing to be set up by hand.
        for tenant_name, tenant_id in tenants.items():
            label = tenant_name.split()[0]
            with tenant_context(session, tenant_id):
                system = get_or_create_ai_system(session, f"{label} Resume Screener")
                create_incident(
                    session,
                    ai_system_id=system.id,
                    severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
                    description=f"[DEMO] {label}-only incident. Should never be visible to the other tenant.",
                    detected_at=date.today(),
                )


def main() -> None:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    _seed(engine)

    def override_get_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(
        DemoProvider(), model="demo-fake-model"
    )

    print(f"""
  EU AI Act Compliance Platform -- DEMO MODE
  ------------------------------------------------------------------
  In-memory database, fake LLM. No API key needed, nothing persisted.

  http://{HOST}:{PORT}/               sign in
  http://{HOST}:{PORT}/ai-risk-check  public, no login required

  Sign in as:""")
    for tenant_name, email, password, role in ACCOUNTS:
        print(f"    {email:<22} {password:<18} {role.value:<7} ({tenant_name})")
    print("""
  Worth trying:
    - Sign in as admin@acme.test, note the AI system id in the URL,
      then sign in as admin@globex.test and paste that URL -> 404.
    - Sign in as viewer@acme.test and try to run an assessment -> 403.
  ------------------------------------------------------------------
""", flush=True)  # flush: the banner must appear before uvicorn takes the terminal
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
