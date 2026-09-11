from src.evidence.assess import assess_all_obligations, assess_evidence
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.obligations.mapping import Obligation
from schemas.enums import ClassificationCategory, EvidenceStatus

OBLIGATION = Obligation(
    requirement_key="EU-AI-ACT-ART9",
    citation="Article 9",
    summary="Providers must establish, implement, document, and maintain a risk management system.",
    triggered_by=ClassificationCategory.HIGH_RISK,
)

ALL_DIMENSIONS_MET_JSON = (
    '{"requirement_key": "EU-AI-ACT-ART9", "status": "COMPLIANT", "dimensions": ['
    '{"dimension": "relevance", "met": true, "note": "Directly addresses risk management."},'
    '{"dimension": "completeness", "met": true, "note": "Covers full lifecycle."},'
    '{"dimension": "specificity", "met": true, "note": "Names concrete risk categories."},'
    '{"dimension": "currency", "met": true, "note": "Updated this year."},'
    '{"dimension": "traceability", "met": true, "note": "Linked to responsible owner."},'
    '{"dimension": "consistency", "met": true, "note": "Matches other docs."},'
    '{"dimension": "sufficiency", "met": true, "note": "Fully covers the obligation."}'
    '], "rationale": "Thorough, current risk management policy.", "contradictions": []}'
)


def _client(responses: list[str]) -> tuple[LLMClient, FakeCompletionProvider]:
    provider = FakeCompletionProvider(responses)
    return LLMClient(provider, model="fake-model"), provider


def test_empty_evidence_skips_llm_call_and_returns_insufficient_evidence():
    client, provider = _client([])

    result = assess_evidence(client, OBLIGATION, "")

    assert result.status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert len(provider.calls) == 0
    assert len(result.dimensions) == 7


def test_valid_response_passes_through():
    client, provider = _client([ALL_DIMENSIONS_MET_JSON])

    result = assess_evidence(client, OBLIGATION, "Our risk management policy covers the full AI system lifecycle...")

    assert result.status == EvidenceStatus.COMPLIANT
    assert len(provider.calls) == 1


def test_mismatched_requirement_key_fails_closed():
    wrong_key_response = ALL_DIMENSIONS_MET_JSON.replace("EU-AI-ACT-ART9", "EU-AI-ACT-ART10")
    client, _ = _client([wrong_key_response])

    result = assess_evidence(client, OBLIGATION, "Some evidence text.")

    assert result.status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert "expected" in result.rationale


def test_assess_all_obligations_matches_evidence_by_key():
    other_obligation = Obligation(
        requirement_key="EU-AI-ACT-ART10",
        citation="Article 10",
        summary="Data governance obligation.",
        triggered_by=ClassificationCategory.HIGH_RISK,
    )
    client, provider = _client([ALL_DIMENSIONS_MET_JSON])

    results = assess_all_obligations(
        client,
        [OBLIGATION, other_obligation],
        evidence_by_key={"EU-AI-ACT-ART9": "Our risk management policy..."},
    )

    assert results[0].status == EvidenceStatus.COMPLIANT
    assert results[1].status == EvidenceStatus.INSUFFICIENT_EVIDENCE  # no evidence supplied for ART10
    assert len(provider.calls) == 1  # only the obligation with evidence calls the LLM
