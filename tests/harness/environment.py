import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from secrets import token_hex
from time import monotonic, sleep

import psycopg

from nevis_search.config import Backend


@dataclass(frozen=True)
class Environment:
    envvars: dict[str, str] = field(repr=False)


@contextmanager
def environment(backend: Backend = "sqlite") -> Generator[Environment]:
    if backend == "postgres":
        with postgres_container() as dsn:
            yield Environment({"NEVIS_STORE": backend, "NEVIS_POSTGRES_DSN": dsn})
    else:
        yield Environment({"NEVIS_STORE": backend})


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
