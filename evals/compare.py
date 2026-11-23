"""Compare integrated Postgres search and research controls; emit stable-key JSON."""

import json
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from functools import partial
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Literal, TypedDict
from uuid import UUID

from nevis_search.config import POSTGRES_APPROACHES, Postgres, PostgresApproach
from nevis_search.search import Client, Document, Search, search_factory
from nevis_search.search.postgres import SearchStorePostgres
from nevis_search.search.skg import rank_documents
from tests.harness.environment import postgres_container

from .search_quality import CASES, REED_CASES, seed_reed, seed_substrings

type Mode = PostgresApproach | Literal["shared-literal", "skg-off"]


class CaseResult(TypedDict):
    query: str
    gold_ranks: dict[str, int | None]
    top5: list[str]
    result_count: int
    passed: bool
    hit5: bool


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


def check(
    search: Search,
    keys_by_id: dict[UUID, str],
    query: str,
    gold: tuple[str, ...],
    *,
    result_type: type[Client | Document] | None = None,
    exact: bool = False,
) -> CaseResult:
    keys = [
        keys_by_id[row.id]
        for row in search.search(query)
        if result_type is None or isinstance(row, result_type)
    ]
    ranks = {key: keys.index(key) + 1 if key in keys else None for key in gold}
    return {
        "query": query,
        "gold_ranks": ranks,
        "top5": keys[:5],
        "result_count": len(keys),
        "passed": sorted(keys) == sorted(gold) if exact else keys[:1] == list(gold),
        "hit5": any(rank is not None and rank <= 5 for rank in ranks.values()),
    }


def compare(mode: Mode) -> dict[str, object]:
    with open_search(mode) as search:
        keys = {row.id: key for key, row in seed_substrings(search).items()}
        exact = [
            check(search, keys, c.query, c.expected_titles, exact=True) for c in CASES
        ]
    with open_search(mode) as search:
        keys = {row.id: key for key, row in seed_reed(search).items()}
        reed = [
            check(search, keys, c.query, (c.expected_key,), result_type=c.result_type)
            for c in REED_CASES
        ]
        elapsed: list[float] = []
        for _ in range(10):
            for c in REED_CASES:
                start = perf_counter_ns()
                search.search(c.query)
                elapsed.append((perf_counter_ns() - start) / 1e6)
        holdout = json.loads(
            Path(__file__)
            .with_name("cases")
            .joinpath("search-holdout-v1.json")
            .read_text()
        )
        blind = [
            check(search, keys, c["query"], (c["expected"],), result_type=Document)
            if c["expected"]
            else check(search, keys, c["query"], (), exact=True)
            for c in holdout["cases"]
        ]

    return {
        "approach": mode,
        "exact_set": sum(row["passed"] for row in exact),
        "reed_top1": sum(row["passed"] for row in reed),
        "reed_hit5": sum(row["hit5"] for row in reed),
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
        "reed_cases": reed,
        "holdout_cases": blind,
    }


def main() -> None:
    modes: tuple[Mode, ...] = (*POSTGRES_APPROACHES, "shared-literal", "skg-off")
    print(json.dumps([compare(mode) for mode in modes], indent=2))


if __name__ == "__main__":
    main()
