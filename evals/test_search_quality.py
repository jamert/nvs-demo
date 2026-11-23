import pytest

from nevis_search.config import POSTGRES_APPROACHES, PostgresApproach

from .search_quality import EXACT_GROUP, RANKED_GROUPS, EvalResult, evaluate


def report(label: str, result: EvalResult) -> None:
    summary = f"{label}: {result.summary}"
    if result.failures:
        pytest.fail("\n".join([summary, *result.failures]), pytrace=False)
    print(summary)


@pytest.fixture(scope="module", params=POSTGRES_APPROACHES)
def approach(request: pytest.FixtureRequest) -> PostgresApproach:
    return request.param


@pytest.fixture(scope="module")
def results(approach: PostgresApproach) -> dict[str, EvalResult]:
    return evaluate(approach)


def test_substring_regressions(
    approach: PostgresApproach, results: dict[str, EvalResult]
) -> None:
    report(f"{approach} substring regressions", results[EXACT_GROUP])


@pytest.mark.parametrize("group", RANKED_GROUPS)
def test_ranked_search_quality(
    approach: PostgresApproach, group: str, results: dict[str, EvalResult]
) -> None:
    report(f"{approach} {group} ranked search", results[group])
