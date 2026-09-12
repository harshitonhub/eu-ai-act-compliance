from datetime import date

from src.legal.ingest import ingest_seed, seed_is_present
from src.legal.queries import find_requirements
from schemas.enums import ActorRole
from src.persistence.models import LegalProvision, Requirement, SourceDocument


def test_ingest_seed_loads_source_document_and_provisions(session):
    assert not seed_is_present(session)

    ingest_seed(session)

    ai_act = session.query(SourceDocument).filter_by(source_key="eu_ai_act_2024_1689").one()
    assert ai_act.celex_id == "32024R1689"

    ai_act_provisions = session.query(LegalProvision).filter_by(source_document_id=ai_act.id).all()
    citations = {p.citation for p in ai_act_provisions}
    assert citations == {
        "Article 5", "Article 6", "Annex III",
        "Article 9", "Article 10", "Article 11", "Article 12", "Article 13", "Article 14", "Article 15",
        "Article 73", "Article 3(49)", "Article 3(61)",
    }
    # Article 3(61) is a general-EU-law definition (widespread infringement) that
    # doesn't itself mention "AI system" -- everything else ingested does.
    for provision in ai_act_provisions:
        if provision.citation == "Article 3(61)":
            continue
        assert "AI system" in provision.text or "AI practices" in provision.text


def test_ingest_seed_loads_gdpr_source_document_and_provisions(session):
    ingest_seed(session)

    gdpr = session.query(SourceDocument).filter_by(source_key="gdpr_2016_679").one()
    assert gdpr.celex_id == "32016R0679"

    gdpr_provisions = session.query(LegalProvision).filter_by(source_document_id=gdpr.id).all()
    citations = {p.citation for p in gdpr_provisions}
    assert citations == {"Article 22", "Article 35"}
    for provision in gdpr_provisions:
        assert "data subject" in provision.text.lower()


def test_ingest_seed_is_idempotent(session):
    ingest_seed(session)
    first_count = session.query(Requirement).count()

    ingest_seed(session)  # should be a no-op, not a duplicate insert
    second_count = session.query(Requirement).count()

    assert first_count == second_count > 0


def test_annex_iii_category_query_returns_correct_citations(session):
    ingest_seed(session)

    results = find_requirements(session, annex_iii_category="4")

    assert len(results) == 1
    result = results[0]
    assert result.requirement_key == "EU-AI-ACT-ANNEXIII-4"
    assert result.citation == "Annex III"
    assert "Employment" in result.summary
    assert "recruitment" in result.provision_text.lower()


def test_prohibited_practice_with_exception_is_surfaced(session):
    ingest_seed(session)

    results = find_requirements(session, as_of=date(2025, 6, 1))
    art5_1_d = next(r for r in results if r.requirement_key == "EU-AI-ACT-ART5-1-D")

    assert len(art5_1_d.exceptions) == 1
    assert "objective and verifiable facts" in art5_1_d.exceptions[0]


def test_temporal_filter_excludes_requirements_not_yet_in_force(session):
    ingest_seed(session)

    # GDPR (in force since 2018) is already live at this date; the AI Act is not.
    before_any_application = find_requirements(session, as_of=date(2024, 1, 1))
    keys = {r.requirement_key for r in before_any_application}
    assert keys == {"GDPR-ART22", "GDPR-ART35"}

    after_prohibitions_only = find_requirements(session, as_of=date(2025, 6, 1))
    keys = {r.requirement_key for r in after_prohibitions_only}
    assert "EU-AI-ACT-ART5-1-A" in keys
    assert "EU-AI-ACT-ANNEXIII-1" not in keys  # high-risk pathway not yet in force at this date


def test_actor_role_filter_matches_any_scoped_requirements(session):
    ingest_seed(session)

    results = find_requirements(session, actor_role=ActorRole.PROVIDER)

    assert len(results) > 0  # ANY-scoped requirements match every specific actor role query
