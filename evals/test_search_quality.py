import pytest

from nevis_search.config import POSTGRES_APPROACHES, PostgresApproach

from .search_quality import EvalResult, evaluate, evaluate_substrings


def report(label: str, result: EvalResult) -> None:
    summary = f"{label}: {result.summary}"
    if result.failures:
        pytest.fail("\n".join([summary, *result.failures]), pytrace=False)
    print(summary)


@pytest.mark.parametrize("approach", POSTGRES_APPROACHES)
def test_substring_regressions(approach: PostgresApproach) -> None:
    report(f"{approach} substring regressions", evaluate_substrings(approach))


@pytest.mark.parametrize("approach", POSTGRES_APPROACHES)
def test_reed_search_quality(approach: PostgresApproach) -> None:
    report(f"{approach} Reed ranked search", evaluate(approach))
