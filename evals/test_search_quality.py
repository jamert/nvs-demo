import pytest

from .search_quality import evaluate


def test_document_search_quality() -> None:
    result = evaluate()
    summary = f"Search quality: {result.summary}"
    if result.failures:
        pytest.fail("\n".join([summary, *result.failures]), pytrace=False)
    print(summary)
