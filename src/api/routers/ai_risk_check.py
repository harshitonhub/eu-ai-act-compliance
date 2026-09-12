"""Standalone public entry point for a quick EU AI Act risk check. One text box, one
plain-English answer, reusing the full classification pipeline -- but scoped to a
single quick question, not the full compliance workflow.

Originally scoped to hiring/recruitment AI specifically as the starting niche (see
ROADMAP.md); broadened to any AI system once it was clear the underlying
classify_system pipeline already checks all 8 Annex III categories regardless -- the
narrowness was in this page's copy, not a technical limitation.

Deliberately separate from the authenticated assessment router: public, no login,
stricter rate limit, and no AssessmentRecord persisted (anonymous input shouldn't
silently land in someone's system-of-record).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from schemas.enums import ClassificationCategory
from schemas.facts import ExtractedFacts
from src.api.dependencies import get_llm_client
from src.api.rate_limit import public_rate_limit
from src.classification.classify import classify_system
from src.legal.queries import find_requirement_by_key
from src.llm import LLMClient
from src.persistence.db import get_session
from src.web.copy import STATE_EXPLANATIONS

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["STATE_EXPLANATIONS"] = STATE_EXPLANATIONS
templates.env.globals["public_page"] = True  # hides the auth-only /history nav link


@router.get("/ai-risk-check", response_class=HTMLResponse)
def show_ai_risk_check_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ai_risk_check.html", {})


@router.post("/ai-risk-check", response_class=HTMLResponse)
def run_ai_risk_check(
    request: Request,
    description: str = Form(...),
    session: Session = Depends(get_session),
    llm_client: LLMClient = Depends(get_llm_client),
    _rate_limit: None = Depends(public_rate_limit),
) -> HTMLResponse:
    facts = ExtractedFacts(system_description=description, intended_purpose=description)

    try:
        classification = classify_system(llm_client, session, facts, as_of=date.today())
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user, no record to persist
        return templates.TemplateResponse(
            request,
            "ai_risk_check.html",
            {"description": description, "error": f"Something went wrong. Technical detail: {exc}"},
        )

    prohibited = classification.for_category(ClassificationCategory.PROHIBITED_PRACTICES)
    high_risk = classification.for_category(ClassificationCategory.HIGH_RISK)

    citation_texts = {}
    for assessment in (prohibited, high_risk):
        for cited in assessment.cited_requirements:
            result = find_requirement_by_key(session, cited.requirement_key)
            if result is not None:
                citation_texts[cited.requirement_key] = result.provision_text

    return templates.TemplateResponse(
        request,
        "ai_risk_check.html",
        {
            "description": description,
            "prohibited": prohibited,
            "high_risk": high_risk,
            "citation_texts": citation_texts,
        },
    )
