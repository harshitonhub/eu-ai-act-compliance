from src.review.triggers import ReviewTrigger, determine_review_flags
from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState, EvidenceDimension, EvidenceStatus
from schemas.evidence import DimensionAssessment, EvidenceAssessment


def _classification(**overrides) -> ClassificationResult:
    defaults = {cat: (ClassificationState.NO, 0.9, []) for cat in ClassificationCategory}
    defaults.update(overrides)
    assessments = [
        CategoryClassification(category=cat, state=state, cited_requirements=cited, rationale="fixture", confidence=confidence)
        for cat, (state, confidence, cited) in defaults.items()
    ]
    return ClassificationResult(assessments=assessments)


def _evidence(requirement_key, status, contradictions=None) -> EvidenceAssessment:
    return EvidenceAssessment(
        requirement_key=requirement_key,
        status=status,
        dimensions=[DimensionAssessment(dimension=d, met=True, note="n/a") for d in EvidenceDimension],
        rationale="fixture",
        contradictions=contradictions or [],
    )


def _triggers(flags) -> set[ReviewTrigger]:
    return {f.trigger for f in flags}


def test_no_flags_for_clean_negative_result():
    flags = determine_review_flags(_classification(), [])
    assert flags == []


def test_insufficient_information_triggers_flag():
    classification = _classification(
        **{ClassificationCategory.SCOPE: (ClassificationState.INSUFFICIENT_INFORMATION, 0.0, [])}
    )
    flags = determine_review_flags(classification, [])
    assert ReviewTrigger.INSUFFICIENT_INFORMATION in _triggers(flags)


def test_low_confidence_triggers_flag_only_for_resolved_states():
    classification = _classification(
        **{ClassificationCategory.TRANSPARENCY: (ClassificationState.NO, 0.3, [])}
    )
    flags = determine_review_flags(classification, [])
    assert ReviewTrigger.LOW_CONFIDENCE in _triggers(flags)


def test_low_confidence_not_triggered_for_not_applicable():
    classification = _classification(
        **{ClassificationCategory.HIGH_RISK: (ClassificationState.NOT_APPLICABLE, 0.0, [])}
    )
    flags = determine_review_flags(classification, [])
    assert ReviewTrigger.LOW_CONFIDENCE not in _triggers(flags)
    # NOT_APPLICABLE also shouldn't be double-counted as insufficient_information
    assert ReviewTrigger.INSUFFICIENT_INFORMATION not in _triggers(flags)


def test_high_impact_prohibited_practice_yes_triggers_flag():
    cited = [CitedRequirement(requirement_key="EU-AI-ACT-ART5-1-A", citation="Article 5", relevance="x")]
    classification = _classification(
        **{ClassificationCategory.PROHIBITED_PRACTICES: (ClassificationState.YES, 0.9, cited)}
    )
    flags = determine_review_flags(classification, [])
    assert ReviewTrigger.HIGH_IMPACT_PROHIBITED_PRACTICE in _triggers(flags)


def test_high_impact_high_risk_possibly_triggers_flag():
    cited = [CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="x")]
    classification = _classification(
        **{ClassificationCategory.HIGH_RISK: (ClassificationState.POSSIBLY, 0.7, cited)}
    )
    flags = determine_review_flags(classification, [])
    assert ReviewTrigger.HIGH_IMPACT_HIGH_RISK in _triggers(flags)


def test_evidence_gap_triggers_for_insufficient_non_compliant_and_partially_compliant():
    evidence = [
        _evidence("EU-AI-ACT-ART9", EvidenceStatus.INSUFFICIENT_EVIDENCE),
        _evidence("EU-AI-ACT-ART10", EvidenceStatus.NON_COMPLIANT),
        _evidence("EU-AI-ACT-ART11", EvidenceStatus.PARTIALLY_COMPLIANT),
        _evidence("EU-AI-ACT-ART12", EvidenceStatus.COMPLIANT),
    ]
    flags = determine_review_flags(_classification(), evidence)
    gap_flags = [f for f in flags if f.trigger == ReviewTrigger.EVIDENCE_GAP]
    assert len(gap_flags) == 3  # everything except COMPLIANT


def test_contradiction_detected_triggers_flag():
    evidence = [_evidence("EU-AI-ACT-ART14", EvidenceStatus.NON_COMPLIANT, contradictions=["doc A vs doc B"])]
    flags = determine_review_flags(_classification(), evidence)
    assert ReviewTrigger.CONTRADICTION_DETECTED in _triggers(flags)


def test_every_flag_has_a_non_empty_explanation():
    classification = _classification(
        **{ClassificationCategory.SCOPE: (ClassificationState.INSUFFICIENT_INFORMATION, 0.0, [])}
    )
    evidence = [_evidence("EU-AI-ACT-ART9", EvidenceStatus.NON_COMPLIANT, contradictions=["x vs y"])]
    flags = determine_review_flags(classification, evidence)
    assert all(f.detail.strip() for f in flags)
