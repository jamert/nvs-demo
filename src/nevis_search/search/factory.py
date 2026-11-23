from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from functools import partial
from typing import assert_never

from nevis_search.config import Config, Postgres

from .bm25 import rank_bm25
from .core import Search
from .embeddings import DenseRanker, LocalEncoder
from .postgres import SearchStorePostgres
from .query_routing import RankDocuments
from .skg import rank_documents
from .sqlite import SearchStoreSQLite

__all__ = ["search_factory"]


@contextmanager
def search_factory(config: Config) -> Generator[Search]:
    if not isinstance(config, Postgres):
        with SearchStoreSQLite.in_memory() as store:
            yield Search(store)
        return

    with ExitStack() as stack:
        rank: RankDocuments | None
        match config.approach:
            case "postgres-substring":
                rank = None
            case "bm25":
                rank = rank_bm25
            case "dense-e5":
                rank = DenseRanker(stack.enter_context(LocalEncoder.connect()))
            case "skg":
                rank = partial(rank_documents, expand=True)
            case other:  # pragma: no cover - PostgresApproach is exhaustive.
                assert_never(other)
        yield Search(stack.enter_context(SearchStorePostgres.connect(config.dsn, rank)))
