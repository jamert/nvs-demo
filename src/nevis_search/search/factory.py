from collections.abc import Generator
from contextlib import contextmanager

from nevis_search.config import Config, Postgres

from .core import Search
from .postgres import SearchStorePostgres
from .sqlite import SearchStoreSQLite

__all__ = ["search_factory"]


@contextmanager
def search_factory(config: Config) -> Generator[Search]:
    connection = (
        SearchStorePostgres.connect(config.dsn)
        if isinstance(config, Postgres)
        else SearchStoreSQLite.in_memory()
    )
    with connection as store:
        yield Search(store)
