import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from secrets import token_hex
from time import monotonic, sleep

import psycopg

from nevis_search.config import SearchApproach


@dataclass(frozen=True)
class Environment:
    envvars: dict[str, str] = field(repr=False)


@contextmanager
def environment(
    approach: SearchApproach = "sqlite-substring",
) -> Generator[Environment]:
    if approach == "sqlite-substring":
        yield Environment({"NEVIS_SEARCH": approach})
    else:
        with postgres_container() as dsn:
            yield Environment({"NEVIS_SEARCH": approach, "NEVIS_POSTGRES_DSN": dsn})


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
