"""Phase 6 DoD: the full adversarial suite (from the adversarial-testing skill's list)
runs and passes. See evals/adversarial/README.md for the coverage table mapping the
skill's scenarios to specific tests, old and new.
"""

from pathlib import Path

from evals.evidence_runner import run_evidence_golden_suite
from evals.runner import run_golden_suite

ADVERSARIAL_DIR = Path(__file__).resolve().parents[1] / "evals" / "adversarial"
ADVERSARIAL_CLASSIFICATION_DIR = ADVERSARIAL_DIR / "classification"
ADVERSARIAL_EVIDENCE_DIR = ADVERSARIAL_DIR / "evidence"


def test_adversarial_classification_cases_load_and_pass(session):
    report = run_golden_suite(session, cases_dir=ADVERSARIAL_CLASSIFICATION_DIR)

    assert report.total >= 2
    failures = [(c.case_id, c.mismatches) for c in report.case_results if not c.passed]
    assert not failures, "adversarial classification cases failed:\n" + "\n".join(
        f"{cid}: {m}" for cid, m in failures
    )


def test_citation_bypass_attempt_fails_closed_to_insufficient_information(session):
    report = run_golden_suite(session, cases_dir=ADVERSARIAL_CLASSIFICATION_DIR)
    case = next(c for c in report.case_results if c.case_id == "adversarial-citation-bypass-attempt")
    assert case.passed


def test_conflicting_actor_roles_does_not_crash_the_pipeline(session):
    report = run_golden_suite(session, cases_dir=ADVERSARIAL_CLASSIFICATION_DIR)
    case = next(c for c in report.case_results if c.case_id == "adversarial-conflicting-actor-roles")
    assert case.passed


def test_adversarial_evidence_cases_load_and_pass():
    report = run_evidence_golden_suite(cases_dir=ADVERSARIAL_EVIDENCE_DIR)

    assert report.total >= 1
    failures = [(c.case_id, c.mismatches) for c in report.case_results if not c.passed]
    assert not failures, "adversarial evidence cases failed:\n" + "\n".join(f"{cid}: {m}" for cid, m in failures)
