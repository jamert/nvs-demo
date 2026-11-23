import pytest

from nevis_search.config import (
    POSTGRES_APPROACHES,
    Postgres,
    PostgresApproach,
    SQLite,
    from_env,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("NEVIS_STORE", "NEVIS_SEARCH", "NEVIS_POSTGRES_DSN"):
        monkeypatch.delenv(key, raising=False)


def test_default_search_is_in_memory_substring() -> None:
    assert from_env() == SQLite()


@pytest.mark.parametrize("approach", POSTGRES_APPROACHES)
def test_postgres_search_requires_dsn(
    monkeypatch: pytest.MonkeyPatch, approach: PostgresApproach
) -> None:
    monkeypatch.setenv("NEVIS_SEARCH", approach)
    with pytest.raises(ValueError, match="NEVIS_POSTGRES_DSN is required"):
        from_env()
    monkeypatch.setenv("NEVIS_POSTGRES_DSN", "postgresql://test")
    assert from_env() == Postgres("postgresql://test", approach)


def test_only_one_known_search_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEVIS_SEARCH", "bm25,postgres-substring")
    with pytest.raises(ValueError, match="Unknown NEVIS_SEARCH"):
        from_env()


def test_old_selector_does_not_silently_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEVIS_STORE", "postgres")
    with pytest.raises(ValueError, match="NEVIS_STORE was replaced"):
        from_env()
