import os
from dataclasses import dataclass, field
from typing import Literal

type Backend = Literal["sqlite", "postgres"]


@dataclass(frozen=True)
class SQLite:
    pass


@dataclass(frozen=True)
class Postgres:
    dsn: str = field(repr=False)


type Config = SQLite | Postgres


def from_env() -> Config:
    match os.environ.get("NEVIS_STORE", "sqlite"):
        case "sqlite":
            return SQLite()
        case "postgres":
            if not (dsn := os.environ.get("NEVIS_POSTGRES_DSN")):  # pragma: no cover
                raise ValueError("NEVIS_POSTGRES_DSN is required for postgres")
            return Postgres(dsn)
        case other:  # pragma: no cover
            raise ValueError(
                f"Unknown NEVIS_STORE: {other!r} (expected sqlite or postgres)"
            )
