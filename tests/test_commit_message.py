import sys
from pathlib import Path

import pytest

from evals import commit_message
from evals.search_quality import EXACT_GROUP, EvalResult
from nevis_search.config import POSTGRES_APPROACHES, PostgresApproach


def test_amend_refreshes_four_trailers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    message = tmp_path / "message"
    message.write_text(
        "Subject\n\nReviewed-by: Tester\nSearch-Eval: old combined score\n"
    )
    monkeypatch.setattr(sys, "argv", ["commit_message", str(message)])
    assessed: list[PostgresApproach] = []

    def evaluate(approach: PostgresApproach) -> dict[str, EvalResult]:
        assessed.append(approach)
        return {
            EXACT_GROUP: EvalResult(5, ()),
            "Reed": EvalResult(10, ("one miss",) if approach == "bm25" else ()),
            "Krag": EvalResult(10, ()),
            "Aimee": EvalResult(10, ()),
            "Krag extras": EvalResult(5, ()),
            "Typos": EvalResult(7, ("misspelled name",)),
        }

    monkeypatch.setattr(commit_message, "evaluate", evaluate)
    commit_message.main()
    first = message.read_text()
    commit_message.main()
    assert message.read_text() == first
    assert assessed == list(POSTGRES_APPROACHES) * 2
    assert "Search-Eval: " not in first
    assert "Reviewed-by: Tester" in first
    assert set(commit_message.TRAILER_KEYS) == set(POSTGRES_APPROACHES)
    for key in commit_message.TRAILER_KEYS.values():
        assert first.count(f"{key}:") == 1
    assert "Search-Eval-BM25: 45/47" in first
    assert "Search-Eval-Substring: 46/47" in first
    assert "Reed top-1: 9/10" in first
    assert first.count("Krag top-1: 10/10") == len(POSTGRES_APPROACHES)
    assert first.count("Aimee top-1: 10/10") == len(POSTGRES_APPROACHES)
    assert first.count("Krag extras top-1: 5/5") == len(POSTGRES_APPROACHES)
    assert first.count("Typos top-1: 6/7") == len(POSTGRES_APPROACHES)
