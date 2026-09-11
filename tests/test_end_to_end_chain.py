"""Phase 4 DoD: the full chain facts -> classification -> obligations -> evidence
status -> gap list runs, wiring together classify_system, map_obligations,
assess_all_obligations, and compute_gaps exactly as a future orchestrator/reporting
layer (Phase 5) would.
"""

from datetime import date

from src.classification.classify import classify_system
from src.evidence.assess import assess_all_obligations
from src.gaps.compute import compute_gaps
from src.legal.ingest import ingest_seed
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.obligations.mapping import map_obligations
from schemas.enums import ClassificationCategory, ClassificationState, EvidenceStatus
from schemas.facts import ExtractedFacts

RECRUITMENT_FACTS = ExtractedFacts(
    system_description="An AI tool that screens and ranks job applicant resumes for an employer.",
    intended_purpose="Recruitment and candidate evaluation for employers.",
    actor_roles=["deployer"],
)

CLASSIFICATION_RESPONSES = [
    # prohibited_practices
    '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
    '"rationale": "No prohibited practice indicators.", "confidence": 0.85}',
    # high_risk
    '{"category": "high_risk", "state": "YES", '
    '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", "citation": "Annex III", '
    '"relevance": "recruitment"}], "rationale": "Matches Annex III point 4(a).", "confidence": 0.9}',
]

COMPLIANT_EVIDENCE_JSON_TEMPLATE = (
    '{{"requirement_key": "{key}", "status": "COMPLIANT", "dimensions": ['
    '{{"dimension": "relevance", "met": true, "note": "ok"}},'
    '{{"dimension": "completeness", "met": true, "note": "ok"}},'
    '{{"dimension": "specificity", "met": true, "note": "ok"}},'
    '{{"dimension": "currency", "met": true, "note": "ok"}},'
    '{{"dimension": "traceability", "met": true, "note": "ok"}},'
    '{{"dimension": "consistency", "met": true, "note": "ok"}},'
    '{{"dimension": "sufficiency", "met": true, "note": "ok"}}'
    '], "rationale": "Thorough evidence.", "contradictions": []}}'
)


def test_full_chain_facts_to_gaps_with_no_evidence_supplied(session):
    ingest_seed(session)
    classification_client = LLMClient(FakeCompletionProvider(CLASSIFICATION_RESPONSES), model="fake-model")

    classification = classify_system(classification_client, session, RECRUITMENT_FACTS, as_of=date(2026, 9, 9))
    assert classification.for_category(ClassificationCategory.HIGH_RISK).state == ClassificationState.YES

    obligations = map_obligations(session, classification)
    assert len(obligations) == 7  # all seven Article 9-15 obligations attach

    evidence_client = LLMClient(FakeCompletionProvider([]), model="fake-model")  # no evidence supplied at all
    evidence_assessments = assess_all_obligations(evidence_client, obligations, evidence_by_key={})
    assert all(a.status == EvidenceStatus.INSUFFICIENT_EVIDENCE for a in evidence_assessments)

    gaps = compute_gaps(obligations, evidence_assessments)
    assert len(gaps) == 7  # every obligation is a gap when no evidence exists
    assert {g.requirement_key for g in gaps} == {o.requirement_key for o in obligations}


def test_full_chain_facts_to_gaps_with_partial_evidence_narrows_gaps(session):
    ingest_seed(session)
    classification_client = LLMClient(FakeCompletionProvider(CLASSIFICATION_RESPONSES), model="fake-model")
    classification = classify_system(classification_client, session, RECRUITMENT_FACTS, as_of=date(2026, 9, 9))
    obligations = map_obligations(session, classification)

    # Evidence supplied (and compliant) for only one of the seven obligations.
    covered_key = "EU-AI-ACT-ART9"
    evidence_client = LLMClient(
        FakeCompletionProvider([COMPLIANT_EVIDENCE_JSON_TEMPLATE.format(key=covered_key)]), model="fake-model"
    )
    evidence_assessments = assess_all_obligations(
        evidence_client, obligations, evidence_by_key={covered_key: "Thorough risk management policy..."}
    )

    gaps = compute_gaps(obligations, evidence_assessments)

    assert len(gaps) == 6  # six of seven obligations remain gaps
    assert covered_key not in {g.requirement_key for g in gaps}


def test_full_chain_no_high_risk_no_prohibited_yields_no_obligations_or_gaps(session):
    ingest_seed(session)
    responses = [
        '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
        '"rationale": "No indicators.", "confidence": 0.9}',
        '{"category": "high_risk", "state": "NO", "cited_requirements": [], '
        '"rationale": "No Annex III match.", "confidence": 0.9}',
    ]
    client = LLMClient(FakeCompletionProvider(responses), model="fake-model")
    facts = ExtractedFacts(
        system_description="A customer service chatbot for order status inquiries.",
        intended_purpose="Automate routine customer support.",
    )

    classification = classify_system(client, session, facts, as_of=date(2026, 9, 9))
    obligations = map_obligations(session, classification)
    evidence_assessments = assess_all_obligations(
        LLMClient(FakeCompletionProvider([]), model="fake-model"), obligations, evidence_by_key={}
    )
    gaps = compute_gaps(obligations, evidence_assessments)

    assert obligations == []
    assert evidence_assessments == []
    assert gaps == []
