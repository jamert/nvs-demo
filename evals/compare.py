"""Compare integrated Postgres search and research controls; emit stable-key JSON."""

import json
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from functools import partial
from math import ceil
from statistics import median
from time import perf_counter_ns
from typing import Literal

from nevis_search.config import POSTGRES_APPROACHES, Postgres, PostgresApproach
from nevis_search.search import Document, Search, search_factory
from nevis_search.search.postgres import SearchStorePostgres
from nevis_search.search.skg import rank_documents
from tests.harness.environment import postgres_container

from .read_documents import CASES_DIR
from .search_quality import (
    CLEAN_GROUPS,
    REED_CASES,
    TYPO_VARIANTS,
    ExactCase,
    RankedCase,
    run_cases,
    run_exact,
    run_ranked,
    seed_ranked,
)

type Mode = PostgresApproach | Literal["shared-literal", "skg-off"]


def _no_rank(_: str, __: Sequence[Document]) -> list[Document]:
    return []


@contextmanager
def open_search(mode: Mode) -> Generator[Search]:
    with postgres_container() as dsn:
        if mode in ("shared-literal", "skg-off"):
            rank = (
                _no_rank
                if mode == "shared-literal"
                else partial(rank_documents, expand=False)
            )
            with SearchStorePostgres.connect(dsn, rank) as store:
                yield Search(store)
        else:
            with search_factory(Postgres(dsn, mode)) as search:
                yield search


def compare(mode: Mode) -> dict[str, object]:
    with open_search(mode) as search:
        exact = run_exact(search)
    with open_search(mode) as search:
        ranked = run_ranked(search)
        elapsed: list[float] = []
        for _ in range(10):
            for c in REED_CASES:
                start = perf_counter_ns()
                search.search(c.query)
                elapsed.append((perf_counter_ns() - start) / 1e6)
    # Replay the historical holdout with its original 23 documents.
    holdout = json.loads((CASES_DIR / "search-holdout-v1.json").read_text())
    holdout_cases = [
        ExactCase(row["query"], ())
        if row["expected"] is None
        else RankedCase(row["query"], row["expected"])
        for row in holdout["cases"]
    ]
    with open_search(mode) as search:
        blind = run_cases(search, seed_ranked(search, expanded=False), holdout_cases)

    clean = {row["query"]: row for group in CLEAN_GROUPS for row in ranked[group]}
    typo_controls = {typo: clean[query] for query, typo in TYPO_VARIANTS.items()}
    groups = {
        f"{group.lower().replace(' ', '_')}_{key}": value
        for group, rows in ranked.items()
        for key, value in (
            ("top1", sum(row["passed"] for row in rows)),
            ("hit5", sum(row["hit5"] for row in rows)),
            ("cases", rows),
        )
    }
    return {
        "approach": mode,
        "exact_set": sum(row["passed"] for row in exact),
        **groups,
        "typos_clean_controls": typo_controls,
        "holdout_top1": sum(row["passed"] for row in blind if row["gold_ranks"]),
        "holdout_hit5": sum(row["hit5"] for row in blind),
        "holdout_no_match_empty": [
            row["passed"] for row in blind if not row["gold_ranks"]
        ],
        "warm_store_ms": {
            "samples": len(elapsed),
            "median": median(elapsed),
            "p95": sorted(elapsed)[ceil(0.95 * len(elapsed)) - 1],
        },
        "exact_cases": exact,
        "holdout_cases": blind,
    }


def main() -> None:
    modes: tuple[Mode, ...] = (*POSTGRES_APPROACHES, "shared-literal", "skg-off")
    print(json.dumps([compare(mode) for mode in modes], indent=2))


if __name__ == "__main__":
    main()
