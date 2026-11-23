from collections.abc import Generator

import pytest

from nevis_search.config import POSTGRES_APPROACHES, Config, Postgres, SQLite
from tests.harness.environment import postgres_container, postgres_database


@pytest.fixture(scope="session")
def postgres_server_dsn() -> Generator[str]:
    with postgres_container() as dsn:
        yield dsn


@pytest.fixture
def search_config(request: pytest.FixtureRequest) -> Generator[Config]:
    approach = getattr(request, "param", "sqlite-substring")
    if approach == "sqlite-substring":
        yield SQLite()
    else:
        assert approach in POSTGRES_APPROACHES
        with postgres_database(request.getfixturevalue("postgres_server_dsn")) as dsn:
            yield Postgres(dsn, approach)
