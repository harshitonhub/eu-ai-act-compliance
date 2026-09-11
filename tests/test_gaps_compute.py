from src.gaps.compute import compute_gaps
from src.obligations.mapping import Obligation
from schemas.enums import ClassificationCategory, EvidenceDimension, EvidenceStatus
from schemas.evidence import DimensionAssessment, EvidenceAssessment

ART9 = Obligation(
    requirement_key="EU-AI-ACT-ART9", citation="Article 9", summary="Risk management system.",
    triggered_by=ClassificationCategory.HIGH_RISK,
)
ART10 = Obligation(
    requirement_key="EU-AI-ACT-ART10", citation="Article 10", summary="Data governance.",
    triggered_by=ClassificationCategory.HIGH_RISK,
)


def _assessment(requirement_key: str, status: EvidenceStatus, met: bool = True) -> EvidenceAssessment:
    return EvidenceAssessment(
        requirement_key=requirement_key,
        status=status,
        dimensions=[DimensionAssessment(dimension=d, met=met, note="n/a") for d in EvidenceDimension],
        rationale="test fixture",
    )


def test_compliant_obligation_is_not_a_gap():
    gaps = compute_gaps([ART9], [_assessment("EU-AI-ACT-ART9", EvidenceStatus.COMPLIANT)])

    assert gaps == []


def test_non_compliant_obligation_is_a_gap():
    gaps = compute_gaps([ART9], [_assessment("EU-AI-ACT-ART9", EvidenceStatus.NON_COMPLIANT, met=False)])

    assert len(gaps) == 1
    assert gaps[0].requirement_key == "EU-AI-ACT-ART9"
    assert gaps[0].evidence_status == EvidenceStatus.NON_COMPLIANT


def test_partially_compliant_obligation_is_a_gap():
    gaps = compute_gaps([ART9], [_assessment("EU-AI-ACT-ART9", EvidenceStatus.PARTIALLY_COMPLIANT, met=False)])

    assert len(gaps) == 1


def test_missing_evidence_assessment_is_a_gap_with_insufficient_evidence():
    gaps = compute_gaps([ART9], [])

    assert len(gaps) == 1
    assert gaps[0].evidence_status == EvidenceStatus.INSUFFICIENT_EVIDENCE
    assert "No evidence assessment available" in gaps[0].rationale


def test_mixed_obligations_only_non_compliant_ones_are_gaps():
    gaps = compute_gaps(
        [ART9, ART10],
        [
            _assessment("EU-AI-ACT-ART9", EvidenceStatus.COMPLIANT),
            _assessment("EU-AI-ACT-ART10", EvidenceStatus.NON_COMPLIANT, met=False),
        ],
    )

    assert len(gaps) == 1
    assert gaps[0].requirement_key == "EU-AI-ACT-ART10"


def test_no_obligations_means_no_gaps():
    assert compute_gaps([], []) == []
