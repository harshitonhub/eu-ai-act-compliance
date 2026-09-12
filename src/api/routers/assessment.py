from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from schemas.classification import ClassificationResult
from schemas.enums import ActorRole
from schemas.facts import ExtractedFacts
from src.api.dependencies import get_llm_client
from src.api.rate_limit import rate_limit
from src.classification.classify import classify_system
from src.evidence.assess import assess_all_obligations
from src.evidence.file_ingestion import FileValidationError, extract_evidence_text
from src.gaps.compute import compute_gaps
from src.legal.queries import find_requirement_by_key
from src.llm import LLMClient
from src.obligations.mapping import Obligation, map_obligations
from src.observability.assessment_log import list_recent_assessments, record_assessment, reconstruct_assessment
from src.observability.instrumented_client import InstrumentedLLMClient
from src.observability.serialization import llm_call_record_from_dict, llm_call_record_to_dict
from src.persistence.db import get_session
from src.reporting.report import build_report
from src.review.triggers import determine_review_flags
from src.web.copy import STATE_EXPLANATIONS

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["STATE_EXPLANATIONS"] = STATE_EXPLANATIONS

EVIDENCE_FIELD_PREFIX = "evidence__"
EVIDENCE_FILE_FIELD_PREFIX = "evidence_file__"
LEGAL_KNOWLEDGE_SOURCE_KEY = "eu_ai_act_2024_1689"  # the only source ingested so far -- see docs/legal-methodology.md


def _citation_texts_for(session: Session, classification: ClassificationResult) -> dict[str, str]:
    """requirement_key -> verbatim provision text, for every citation in a result.
    Lets the UI show the actual quoted law next to a citation instead of a bare code.
    """
    keys = {c.requirement_key for a in classification.assessments for c in a.cited_requirements}
    texts = {}
    for key in keys:
        result = find_requirement_by_key(session, key)
        if result is not None:
            texts[key] = result.provision_text
    return texts


@router.get("/", response_class=HTMLResponse)
def show_assessment_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "assessment_form.html",
        {"actor_roles": [r.value for r in ActorRole], "as_of": date.today().isoformat()},
    )


@router.post("/assess", response_class=HTMLResponse)
def submit_assessment(
    request: Request,
    system_description: str = Form(...),
    intended_purpose: str = Form(...),
    actor_role: str = Form(""),
    sector: str = Form(""),
    as_of: str = Form(...),
    session: Session = Depends(get_session),
    llm_client: LLMClient = Depends(get_llm_client),
    _rate_limit: None = Depends(rate_limit),
) -> HTMLResponse:
    facts = ExtractedFacts(
        system_description=system_description,
        intended_purpose=intended_purpose,
        actor_roles=[ActorRole(actor_role)] if actor_role else [],
        sector=sector or None,
    )
    as_of_date = date.fromisoformat(as_of)
    instrumented_client = InstrumentedLLMClient(llm_client)

    try:
        classification = classify_system(instrumented_client, session, facts, as_of=as_of_date)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not a bare pass
        # No classification exists yet, so there is nothing meaningful to persist as an
        # AssessmentRecord -- see src/observability/assessment_log.py's module docstring.
        return templates.TemplateResponse(
            request,
            "assessment_form.html",
            {
                "actor_roles": [r.value for r in ActorRole],
                "as_of": as_of,
                "system_description": system_description,
                "intended_purpose": intended_purpose,
                "actor_role": actor_role,
                "sector": sector,
                "error": (
                    "Something went wrong while classifying this system. "
                    f"Technical detail: {exc}"
                ),
            },
        )

    obligations = map_obligations(session, classification)

    return templates.TemplateResponse(
        request,
        "obligations_form.html",
        {
            "classification": classification,
            "obligations": obligations,
            "citation_texts": _citation_texts_for(session, classification),
            "facts_json": facts.model_dump_json(),
            "classification_json": classification.model_dump_json(),
            "classification_llm_calls_json": json.dumps(
                [llm_call_record_to_dict(c) for c in instrumented_client.call_records]
            ),
            "as_of": as_of,
        },
    )


@router.post("/report", response_class=HTMLResponse)
async def generate_report(
    request: Request,
    session: Session = Depends(get_session),
    llm_client: LLMClient = Depends(get_llm_client),
    _rate_limit: None = Depends(rate_limit),
) -> HTMLResponse:
    form = await request.form()

    facts = ExtractedFacts.model_validate_json(form["facts_json"])
    classification = ClassificationResult.model_validate_json(form["classification_json"])
    as_of_date = date.fromisoformat(form["as_of"])
    classification_llm_calls = [
        llm_call_record_from_dict(d) for d in json.loads(form["classification_llm_calls_json"])
    ]

    obligations: list[Obligation] = map_obligations(session, classification)

    evidence_by_key: dict[str, str] = {
        key.removeprefix(EVIDENCE_FIELD_PREFIX): value
        for key, value in form.multi_items()
        if key.startswith(EVIDENCE_FIELD_PREFIX) and isinstance(value, str) and value
    }

    # An uploaded file takes precedence over pasted text for the same obligation --
    # processed after the text pass above so it overwrites, not merges.
    file_errors: list[str] = []
    for key, value in form.multi_items():
        if not (key.startswith(EVIDENCE_FILE_FIELD_PREFIX) and isinstance(value, UploadFile) and value.filename):
            continue
        requirement_key = key.removeprefix(EVIDENCE_FILE_FIELD_PREFIX)
        content = await value.read()
        try:
            evidence_by_key[requirement_key] = extract_evidence_text(filename=value.filename, content=content)
        except FileValidationError as exc:
            file_errors.append(f"{requirement_key} ({value.filename}): {exc}")

    instrumented_client = InstrumentedLLMClient(llm_client)
    error: str | None = None
    try:
        evidence_assessments = assess_all_obligations(instrumented_client, obligations, evidence_by_key)
        gaps = compute_gaps(obligations, evidence_assessments)
        review_flags = determine_review_flags(classification, evidence_assessments)
    except Exception as exc:  # noqa: BLE001 -- recorded, then re-raised as a 500
        error = f"Something went wrong while assessing evidence. Technical detail: {exc}"
        evidence_assessments, gaps, review_flags = [], [], []
        record_assessment(
            session,
            as_of=as_of_date,
            legal_knowledge_source_key=LEGAL_KNOWLEDGE_SOURCE_KEY,
            facts=facts,
            classification=classification,
            obligations=obligations,
            evidence_assessments=evidence_assessments,
            gaps=gaps,
            review_flags=review_flags,
            llm_calls=classification_llm_calls + instrumented_client.call_records,
            error=error,
        )
        raise

    assessment_id = record_assessment(
        session,
        as_of=as_of_date,
        legal_knowledge_source_key=LEGAL_KNOWLEDGE_SOURCE_KEY,
        facts=facts,
        classification=classification,
        obligations=obligations,
        evidence_assessments=evidence_assessments,
        gaps=gaps,
        review_flags=review_flags,
        llm_calls=classification_llm_calls + instrumented_client.call_records,
    )

    report = build_report(facts, as_of_date, classification, obligations, evidence_assessments, gaps, review_flags)

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "report": report,
            "assessment_id": assessment_id,
            "file_errors": file_errors,
            "citation_texts": _citation_texts_for(session, classification),
        },
    )


@router.get("/history", response_class=HTMLResponse)
def show_history(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    assessments = list_recent_assessments(session)
    return templates.TemplateResponse(request, "history.html", {"assessments": assessments})


@router.get("/assessments/{assessment_id}", response_class=HTMLResponse)
def show_past_assessment(
    assessment_id: str, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    reconstructed = reconstruct_assessment(session, assessment_id)
    if reconstructed is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")

    report = build_report(
        reconstructed.facts,
        reconstructed.as_of,
        reconstructed.classification,
        reconstructed.obligations,
        reconstructed.evidence_assessments,
        reconstructed.gaps,
        reconstructed.review_flags,
    )

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "report": report,
            "assessment_id": reconstructed.assessment_id,
            "file_errors": [],
            "citation_texts": _citation_texts_for(session, reconstructed.classification),
        },
    )
