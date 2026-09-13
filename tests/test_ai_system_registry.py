from sqlalchemy import func, select

from src.persistence.models import AISystem
from src.systems.registry import get_ai_system, get_or_create_ai_system, list_ai_systems


def test_get_or_create_ai_system_creates_new(session):
    system = get_or_create_ai_system(session, "Resume Screener")

    assert system.name == "Resume Screener"
    assert session.scalar(select(func.count(AISystem.id))) == 1


def test_get_or_create_ai_system_reuses_existing_by_exact_name(session):
    first = get_or_create_ai_system(session, "Resume Screener")
    second = get_or_create_ai_system(session, "Resume Screener")

    assert first.id == second.id
    assert session.scalar(select(func.count(AISystem.id))) == 1


def test_get_or_create_ai_system_strips_whitespace(session):
    system = get_or_create_ai_system(session, "  Resume Screener  ")

    assert system.name == "Resume Screener"


def test_get_ai_system_returns_none_for_unknown_id(session):
    assert get_ai_system(session, "not-a-real-id") is None


def test_list_ai_systems_orders_newest_first_with_assessment_counts(session):
    older = get_or_create_ai_system(session, "Older System")
    newer = get_or_create_ai_system(session, "Newer System")

    summaries = list_ai_systems(session)

    assert [s.id for s in summaries] == [newer.id, older.id]
    assert all(s.assessment_count == 0 for s in summaries)
