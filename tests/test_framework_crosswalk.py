from src.legal.ingest import NIST_AI_RMF_NAME, NIST_CSF_NAME, crosswalks_seeded, ingest_seed
from src.legal.queries import find_crosswalks_by_requirement_key
from src.persistence.models import FrameworkCrosswalk


def test_ingest_seed_loads_nist_ai_rmf_crosswalks(session):
    assert not crosswalks_seeded(session, NIST_AI_RMF_NAME)

    ingest_seed(session)

    assert crosswalks_seeded(session, NIST_AI_RMF_NAME)
    count = session.query(FrameworkCrosswalk).filter_by(framework_name=NIST_AI_RMF_NAME).count()
    assert count == 10  # 9 AI Act/GDPR requirements crosswalked, ART15 gets two entries


def test_ingest_seed_loads_nist_csf_crosswalks(session):
    assert not crosswalks_seeded(session, NIST_CSF_NAME)

    ingest_seed(session)

    assert crosswalks_seeded(session, NIST_CSF_NAME)
    count = session.query(FrameworkCrosswalk).filter_by(framework_name=NIST_CSF_NAME).count()
    assert count == 2  # narrower scope: only EU-AI-ACT-ART15 crosswalks against CSF


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


def test_art15_crosswalks_to_nist_ai_rmf_and_csf(session):
    ingest_seed(session)

    results = find_crosswalks_by_requirement_key(session, "EU-AI-ACT-ART15")

    citations = {r.citation for r in results}
    assert citations == {"MEASURE 2.6", "MEASURE 2.7", "ID.RA-01", "PR.IR-03"}
    frameworks = {r.framework_name for r in results}
    assert frameworks == {NIST_AI_RMF_NAME, NIST_CSF_NAME}


def test_csf_crosswalk_has_verbatim_text_and_does_not_touch_other_obligations(session):
    ingest_seed(session)

    art15 = find_crosswalks_by_requirement_key(session, "EU-AI-ACT-ART15")
    csf_entries = [r for r in art15 if r.framework_name == NIST_CSF_NAME]
    assert {r.citation for r in csf_entries} == {"ID.RA-01", "PR.IR-03"}
    assert any("Vulnerabilities in assets" in r.citation_text for r in csf_entries)

    # Narrower than NIST AI RMF: CSF only crosswalks against ART15.
    art9 = find_crosswalks_by_requirement_key(session, "EU-AI-ACT-ART9")
    assert not any(r.framework_name == NIST_CSF_NAME for r in art9)


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
