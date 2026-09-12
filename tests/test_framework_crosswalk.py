from src.legal.ingest import NIST_AI_RMF_NAME, crosswalks_seeded, ingest_seed
from src.legal.queries import find_crosswalks_by_requirement_key
from src.persistence.models import FrameworkCrosswalk


def test_ingest_seed_loads_nist_crosswalks(session):
    assert not crosswalks_seeded(session)

    ingest_seed(session)

    assert crosswalks_seeded(session)
    count = session.query(FrameworkCrosswalk).filter_by(framework_name=NIST_AI_RMF_NAME).count()
    assert count == 10  # 9 AI Act/GDPR requirements crosswalked, ART15 gets two entries


def test_ingest_seed_crosswalks_is_idempotent(session):
    ingest_seed(session)
    first_count = session.query(FrameworkCrosswalk).count()

    ingest_seed(session)
    second_count = session.query(FrameworkCrosswalk).count()

    assert first_count == second_count > 0


def test_find_crosswalks_returns_verbatim_nist_text(session):
    ingest_seed(session)

    results = find_crosswalks_by_requirement_key(session, "EU-AI-ACT-ART14")

    assert len(results) == 1
    assert results[0].framework_name == NIST_AI_RMF_NAME
    assert results[0].citation == "GOVERN 3.2"
    assert "human-AI configurations" in results[0].citation_text


def test_art15_crosswalks_to_two_measure_subcategories(session):
    ingest_seed(session)

    results = find_crosswalks_by_requirement_key(session, "EU-AI-ACT-ART15")

    citations = {r.citation for r in results}
    assert citations == {"MEASURE 2.6", "MEASURE 2.7"}


def test_gdpr_requirements_also_have_crosswalks(session):
    ingest_seed(session)

    art22 = find_crosswalks_by_requirement_key(session, "GDPR-ART22")
    art35 = find_crosswalks_by_requirement_key(session, "GDPR-ART35")

    assert art22[0].citation == "GOVERN 3.2"
    assert art35[0].citation == "MAP 5.1"


def test_find_crosswalks_returns_empty_for_uncrosswalked_requirement(session):
    ingest_seed(session)

    results = find_crosswalks_by_requirement_key(session, "NOT-A-REAL-KEY")

    assert results == []
