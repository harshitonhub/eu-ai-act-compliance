"""Phase 3 DoD: the golden classification suite passes at an explicit threshold --
100% on 'obvious' and 'exception' cases, and adversarial forced-YES/NO cases correctly
resist to POSSIBLY/INSUFFICIENT_INFORMATION/NOT_APPLICABLE rather than a bare guess.
"""

from evals.runner import run_golden_suite


def _assert_all_passed(results, label):
    failures = [(c.case_id, c.mismatches) for c in results if not c.passed]
    assert not failures, f"{label} cases failed:\n" + "\n".join(f"{cid}: {m}" for cid, m in failures)


def test_golden_suite_loads_at_least_fifteen_cases(session):
    report = run_golden_suite(session)
    assert report.total >= 15


def test_obvious_cases_pass_at_100_percent(session):
    report = run_golden_suite(session)
    obvious = report.by_difficulty("obvious")
    assert len(obvious) > 0
    _assert_all_passed(obvious, "obvious")


def test_exception_cases_pass_at_100_percent(session):
    report = run_golden_suite(session)
    exception_cases = report.by_difficulty("exception")
    assert len(exception_cases) > 0
    _assert_all_passed(exception_cases, "exception")


def test_temporal_cases_pass_at_100_percent(session):
    report = run_golden_suite(session)
    temporal_cases = report.by_difficulty("temporal")
    assert len(temporal_cases) > 0
    _assert_all_passed(temporal_cases, "temporal")


def test_adversarial_cases_resist_forced_binary_and_injection(session):
    report = run_golden_suite(session)
    adversarial_cases = report.by_difficulty("adversarial")
    assert len(adversarial_cases) > 0
    _assert_all_passed(adversarial_cases, "adversarial")


def test_overall_pass_rate_is_perfect_on_this_fixed_fixture_set(session):
    # Every fake_llm_response in this suite was authored as the "correct" answer, so a
    # failure here means the deterministic pipeline (retrieval/validation/citation
    # checks) broke, not that a model reasoned badly -- see the golden dataset README.
    report = run_golden_suite(session)
    _assert_all_passed(report.case_results, "all")
    assert report.pass_rate == 1.0
