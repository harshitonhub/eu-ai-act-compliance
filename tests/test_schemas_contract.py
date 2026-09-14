import pytest
from pydantic import ValidationError

from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ActorRole, ClassificationCategory, ClassificationState, EvidenceDimension, EvidenceStatus
from schemas.evidence import DimensionAssessment, EvidenceAssessment
from schemas.facts import ExtractedFacts


def _all_dimensions(unmet: set[EvidenceDimension] = frozenset()) -> list[DimensionAssessment]:
    return [
        DimensionAssessment(dimension=d, met=d not in unmet, note="Generic." if d in unmet else "Meets requirement.")
        for d in EvidenceDimension
    ]


def test_extracted_facts_valid_minimal_round_trips():
    facts = ExtractedFacts(system_description="A CV screening tool.", intended_purpose="Filter job applicants.")
    assert facts.actor_roles == []
    assert ExtractedFacts.model_validate_json(facts.model_dump_json()) == facts


def test_extracted_facts_rejects_empty_description():
    with pytest.raises(ValidationError):
        ExtractedFacts(system_description="", intended_purpose="x")


def test_extracted_facts_accepts_actor_roles_and_insufficient_information_marker():
    facts = ExtractedFacts(
        system_description="An HR tool.",
        intended_purpose="Rank candidates.",
        actor_roles=[ActorRole.DEPLOYER],
        insufficient_information_fields=["sector"],
    )
    assert facts.insufficient_information_fields == ["sector"]


def _cited_requirement() -> CitedRequirement:
    return CitedRequirement(
        requirement_key="EU-AI-ACT-ANNEXIII-4",
        citation="Annex III",
        relevance="System is used for recruitment.",
    )


def test_category_classification_yes_requires_citation():
    with pytest.raises(ValidationError):
        CategoryClassification(
            category=ClassificationCategory.HIGH_RISK,
            state=ClassificationState.YES,
            cited_requirements=[],
            rationale="No basis given.",
            confidence=0.9,
        )


def test_category_classification_yes_with_citation_is_valid():
    classification = CategoryClassification(
        category=ClassificationCategory.HIGH_RISK,
        state=ClassificationState.YES,
        cited_requirements=[_cited_requirement()],
        rationale="Used for recruitment, matches Annex III point 4(a).",
        confidence=0.85,
    )
    assert classification.state == ClassificationState.YES


def test_category_classification_insufficient_information_needs_no_citation():
    classification = CategoryClassification(
        category=ClassificationCategory.HIGH_RISK,
        state=ClassificationState.INSUFFICIENT_INFORMATION,
        rationale="Sector not stated; cannot determine Annex III applicability.",
        confidence=0.0,
    )
    assert classification.cited_requirements == []


def _all_categories_assessment(state: ClassificationState = ClassificationState.NO) -> list[CategoryClassification]:
    return [
        CategoryClassification(category=cat, state=state, rationale="n/a", confidence=1.0)
        for cat in ClassificationCategory
    ]


def test_classification_result_requires_every_category_exactly_once():
    with pytest.raises(ValidationError):
        ClassificationResult(assessments=_all_categories_assessment()[:-1])  # missing one category


def test_classification_result_valid_with_all_five_categories():
    result = ClassificationResult(assessments=_all_categories_assessment())
    assert result.for_category(ClassificationCategory.GPAI).state == ClassificationState.NO


def test_classification_result_rejects_duplicate_category():
    assessments = [
        *_all_categories_assessment()[:-1],
        CategoryClassification(
            category=ClassificationCategory.SCOPE, state=ClassificationState.NO, rationale="dup", confidence=1.0
        ),
    ]
    with pytest.raises(ValidationError):
        ClassificationResult(assessments=assessments)


def test_evidence_assessment_compliant_requires_all_dimensions_met():
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            requirement_key="EU-AI-ACT-ANNEXIII-4",
            status=EvidenceStatus.COMPLIANT,
            dimensions=_all_dimensions(unmet={EvidenceDimension.SPECIFICITY}),
            rationale="Should not be compliant.",
        )


def test_evidence_assessment_partially_compliant_allows_unmet_dimension():
    assessment = EvidenceAssessment(
        requirement_key="EU-AI-ACT-ANNEXIII-4",
        status=EvidenceStatus.PARTIALLY_COMPLIANT,
        dimensions=_all_dimensions(unmet={EvidenceDimension.SPECIFICITY}),
        rationale="Policy exists but lacks specificity.",
    )
    assert assessment.status == EvidenceStatus.PARTIALLY_COMPLIANT


def test_evidence_assessment_requires_all_seven_dimensions():
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            requirement_key="EU-AI-ACT-ANNEXIII-4",
            status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
            dimensions=[],
            rationale="No evidence supplied.",
        )


def test_evidence_assessment_rejects_partial_dimension_coverage():
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            requirement_key="EU-AI-ACT-ANNEXIII-4",
            status=EvidenceStatus.COMPLIANT,
            dimensions=[DimensionAssessment(dimension=EvidenceDimension.RELEVANCE, met=True, note="ok")],
            rationale="Only one of seven dimensions assessed.",
        )


def test_evidence_assessment_rejects_duplicate_dimension():
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            requirement_key="EU-AI-ACT-ANNEXIII-4",
            status=EvidenceStatus.COMPLIANT,
            dimensions=[
                *_all_dimensions(),
                DimensionAssessment(dimension=EvidenceDimension.RELEVANCE, met=True, note="dup"),
            ],
            rationale="Relevance assessed twice.",
        )
