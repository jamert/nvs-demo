from collections.abc import Generator
from contextlib import contextmanager

from .core import Search
from .sqlite import SearchStoreSQLite


@contextmanager
def search_factory() -> Generator[Search]:
    """Provide a search service backed by a fresh in-memory store for this scope."""
    with SearchStoreSQLite.in_memory() as store:
        yield Search(store)
