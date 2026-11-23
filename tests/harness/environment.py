import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from secrets import token_hex
from time import monotonic, sleep

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nevis_search.config import Config, Postgres


@dataclass(frozen=True)
class Environment:
    envvars: dict[str, str] = field(repr=False)


def environment(config: Config) -> Environment:
    if isinstance(config, Postgres):
        return Environment(
            {"NEVIS_SEARCH": config.approach, "NEVIS_POSTGRES_DSN": config.dsn}
        )
    return Environment({"NEVIS_SEARCH": "sqlite-substring"})


@contextmanager
def postgres_database(server_dsn: str) -> Generator[str]:
    """Give a test an empty database on a shared PostgreSQL server."""
    name = f"test_{token_hex(8)}"
    with psycopg.connect(server_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield make_conninfo(server_dsn, dbname=name)
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def _docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


@contextmanager
def postgres_container() -> Generator[str]:
    password = token_hex(16)
    container = _docker(
        "run",
        "--detach",
        "--rm",
        "--publish",
        "127.0.0.1::5432",
        "--env",
        f"POSTGRES_PASSWORD={password}",
        "postgres:18",
    )
    try:
        address = _docker("port", container, "5432/tcp")
        dsn = f"postgresql://postgres:{password}@{address}/postgres"
        deadline = monotonic() + 30
        while True:
            try:
                with psycopg.connect(dsn, connect_timeout=2):
                    break
            except psycopg.OperationalError:
                if monotonic() >= deadline:
                    raise TimeoutError(f"Postgres not ready at {address}") from None
                sleep(0.1)
        yield dsn
    finally:
        _docker("rm", "--force", "--volumes", container)
