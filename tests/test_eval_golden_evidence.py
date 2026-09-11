"""Phase 4 DoD: evidence-assessment golden cases, including contradictory-evidence
scenarios, pass -- and the deterministic no-evidence shortcut makes zero LLM calls.
"""

from evals.evidence_runner import run_evidence_golden_suite


def _assert_all_passed(results, label):
    failures = [(c.case_id, c.mismatches) for c in results if not c.passed]
    assert not failures, f"{label} cases failed:\n" + "\n".join(f"{cid}: {m}" for cid, m in failures)


def test_golden_evidence_suite_loads_at_least_eight_cases():
    report = run_evidence_golden_suite()
    assert report.total >= 8


def test_contradictory_evidence_cases_pass_and_surface_contradictions():
    report = run_evidence_golden_suite()
    contradictory = report.by_difficulty("contradictory")
    assert len(contradictory) >= 2
    _assert_all_passed(contradictory, "contradictory")


def test_obvious_evidence_cases_pass_at_100_percent():
    report = run_evidence_golden_suite()
    obvious = report.by_difficulty("obvious")
    assert len(obvious) > 0
    _assert_all_passed(obvious, "obvious")


def test_overall_evidence_pass_rate_is_perfect_on_this_fixed_fixture_set():
    report = run_evidence_golden_suite()
    _assert_all_passed(report.case_results, "all")
    assert report.pass_rate == 1.0
