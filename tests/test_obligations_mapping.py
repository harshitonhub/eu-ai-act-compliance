from src.legal.ingest import ingest_seed
from src.obligations.mapping import HIGH_RISK_OBLIGATION_KEYS, map_obligations
from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState


def _result(prohibited_state, high_risk_state, cited=None) -> ClassificationResult:
    requires_citation = {ClassificationState.YES, ClassificationState.POSSIBLY}
    assessments = []
    for category in ClassificationCategory:
        if category == ClassificationCategory.PROHIBITED_PRACTICES:
            state = prohibited_state
        elif category == ClassificationCategory.HIGH_RISK:
            state = high_risk_state
        else:
            state = ClassificationState.INSUFFICIENT_INFORMATION

        cited_requirements = (cited or []) if state in requires_citation else []
        assessments.append(
            CategoryClassification(
                category=category,
                state=state,
                cited_requirements=cited_requirements,
                rationale="test fixture",
                confidence=0.9,
            )
        )
    return ClassificationResult(assessments=assessments)


def test_high_risk_yes_maps_to_all_seven_obligations(session):
    ingest_seed(session)
    result = _result(
        ClassificationState.NO,
        ClassificationState.YES,
        cited=[CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="recruitment")],
    )

    obligations = map_obligations(session, result)

    assert {o.requirement_key for o in obligations} == set(HIGH_RISK_OBLIGATION_KEYS)
    assert all(o.triggered_by == ClassificationCategory.HIGH_RISK for o in obligations)


def test_high_risk_possibly_also_triggers_obligations(session):
    ingest_seed(session)
    result = _result(
        ClassificationState.NO,
        ClassificationState.POSSIBLY,
        cited=[CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="borderline")],
    )

    obligations = map_obligations(session, result)

    assert len(obligations) == 7


def test_high_risk_no_yields_no_high_risk_obligations(session):
    ingest_seed(session)
    result = _result(ClassificationState.NO, ClassificationState.NO)

    obligations = map_obligations(session, result)

    assert obligations == []


def test_prohibited_yes_adds_cease_obligation(session):
    ingest_seed(session)
    result = _result(
        ClassificationState.YES,
        ClassificationState.NO,
        cited=[CitedRequirement(requirement_key="EU-AI-ACT-ART5-1-A", citation="Article 5", relevance="subliminal")],
    )

    obligations = map_obligations(session, result)

    assert len(obligations) == 1
    assert obligations[0].triggered_by == ClassificationCategory.PROHIBITED_PRACTICES
    assert obligations[0].citation == "Article 5"


def test_both_prohibited_and_high_risk_yes_yields_eight_obligations(session):
    ingest_seed(session)
    result = _result(
        ClassificationState.YES,
        ClassificationState.YES,
        cited=[CitedRequirement(requirement_key="EU-AI-ACT-ART5-1-C", citation="Article 5", relevance="scoring")],
    )

    obligations = map_obligations(session, result)

    assert len(obligations) == 8
