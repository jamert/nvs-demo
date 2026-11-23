import sys
from pathlib import Path

import pytest

from evals import commit_message
from evals.advisor_second_batch import ACTIVITY_GROUP, SINGLE_TARGET_GROUP
from evals.search_quality import EXACT_GROUP, EvalResult
from nevis_search.config import POSTGRES_APPROACHES, PostgresApproach


def test_amend_refreshes_four_trailers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    message = tmp_path / "message"
    message.write_text(
        "Subject\n\nReviewed-by: Tester\nSearch-Eval: old combined score\n"
        "Search-Eval-BM25: 1/47 cases passed (Exact-set: 1/5 cases passed)\n"
    )
    monkeypatch.setattr(sys, "argv", ["commit_message", str(message)])
    assessed: list[PostgresApproach] = []
    assessed_second_batch: list[PostgresApproach] = []

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

    def evaluate_second_batch(approach: PostgresApproach) -> dict[str, EvalResult]:
        assessed_second_batch.append(approach)
        return {
            SINGLE_TARGET_GROUP: EvalResult(
                20, ("one miss",) if approach == "bm25" else ()
            ),
            ACTIVITY_GROUP: EvalResult(2, ("partial hit",)),
        }

    monkeypatch.setattr(commit_message, "evaluate", evaluate)
    monkeypatch.setattr(commit_message, "evaluate_second_batch", evaluate_second_batch)
    commit_message.main()
    first = message.read_text()
    commit_message.main()
    assert message.read_text() == first
    assert assessed == assessed_second_batch == list(POSTGRES_APPROACHES) * 2
    assert "Search-Eval: " not in first
    assert "Reviewed-by: Tester" in first
    assert set(commit_message.TRAILER_KEYS) == set(POSTGRES_APPROACHES)
    assert [line for line in first.splitlines() if line.startswith("Search-Eval-")] == [
        f"{commit_message.TRAILER_KEYS[approach]}: "
        f"{65 if approach == 'bm25' else 67}/69 cases passed"
        for approach in POSTGRES_APPROACHES
    ]
