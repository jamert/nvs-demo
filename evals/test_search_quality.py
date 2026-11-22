import pytest

from .search_quality import EvalResult, evaluate, evaluate_substrings


def report(label: str, result: EvalResult) -> None:
    summary = f"{label}: {result.summary}"
    if result.failures:
        pytest.fail("\n".join([summary, *result.failures]), pytrace=False)
    print(summary)


def test_substring_regressions() -> None:
    report("Substring regressions", evaluate_substrings())


def test_reed_search_quality() -> None:
    report("Reed ranked search", evaluate())
