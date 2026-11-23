import sys
from pathlib import Path

import pytest

from evals import commit_message
from evals.search_quality import EvalResult
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

    def ranked(approach: PostgresApproach) -> EvalResult:
        assessed.append(approach)
        return EvalResult(10, ("one miss",) if approach == "bm25" else ())

    monkeypatch.setattr(commit_message, "evaluate", ranked)
    monkeypatch.setattr(
        commit_message, "evaluate_substrings", lambda _: EvalResult(5, ())
    )
    commit_message.main()
    first = message.read_text()
    commit_message.main()
    assert message.read_text() == first
    assert assessed == list(POSTGRES_APPROACHES) * 2
    assert "Search-Eval: " not in first
    assert "Reviewed-by: Tester" in first
    for approach, key in commit_message.TRAILER_KEYS.items():
        assert first.count(f"{key}:") == 1
        if approach not in POSTGRES_APPROACHES:
            assert f"{key}: not integrated" in first
    assert "Search-Eval-BM25: 14/15" in first
    assert "Search-Eval-Substring: 15/15" in first
