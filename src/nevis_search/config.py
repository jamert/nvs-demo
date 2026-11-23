import os
from dataclasses import dataclass, field
from typing import Literal

type PostgresApproach = Literal["postgres-substring", "bm25", "dense-e5", "skg"]
type SearchApproach = Literal["sqlite-substring"] | PostgresApproach

POSTGRES_APPROACHES: tuple[PostgresApproach, ...] = (
    "postgres-substring",
    "bm25",
    "dense-e5",
    "skg",
)


@dataclass(frozen=True)
class SQLite:
    pass


@dataclass(frozen=True)
class Postgres:
    dsn: str = field(repr=False)
    approach: PostgresApproach = "postgres-substring"


type Config = SQLite | Postgres


def from_env() -> Config:
    if "NEVIS_STORE" in os.environ:
        raise ValueError("NEVIS_STORE was replaced by NEVIS_SEARCH; see README.md")
    approach = os.environ.get("NEVIS_SEARCH", "sqlite-substring")
    if approach == "sqlite-substring":
        return SQLite()
    for postgres in POSTGRES_APPROACHES:
        if approach == postgres:
            if not (dsn := os.environ.get("NEVIS_POSTGRES_DSN")):
                raise ValueError(f"NEVIS_POSTGRES_DSN is required for {approach}")
            return Postgres(dsn, postgres)
    choices = ", ".join(("sqlite-substring", *POSTGRES_APPROACHES))
    raise ValueError(f"Unknown NEVIS_SEARCH: {approach!r} (expected {choices})")
