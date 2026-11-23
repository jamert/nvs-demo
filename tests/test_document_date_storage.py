import sys
from datetime import date

import psycopg
import pytest

from nevis_search.cli import main
from nevis_search.search import ClientInput, Document, DocumentInput, Search
from nevis_search.search.postgres import SearchStorePostgres
from nevis_search.search.sqlite import SearchStoreSQLite
from tests.harness.environment import postgres_container


def test_sqlite_document_date_round_trip() -> None:
    with SearchStoreSQLite.in_memory() as store:
        search = Search(store)
        client = search.create_client(
            ClientInput(first_name="Jane", last_name="Doe", email="jane@example.com")
        )
        statement = search.add_document(
            client.id,
            DocumentInput(title="Statement", content="Period ending: 6/30/2025"),
        )
        [stored] = search.search("statement")
        assert isinstance(stored, Document)
        assert stored == statement
        assert stored.document_date == date(2025, 6, 30)
        assert "document_date" not in stored.model_dump()
        assert tuple(
            store._db.execute("SELECT document_date FROM documents").fetchone()
        ) == ("2025-06-30",)


def test_postgres_document_date_migration_and_cli_backfill(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with postgres_container() as dsn, psycopg.connect(dsn, autocommit=True) as db:
        with SearchStorePostgres.connect(dsn) as store:
            search = Search(store)
            client = search.create_client(
                ClientInput(
                    first_name="Jane", last_name="Doe", email="jane@example.com"
                )
            )
            legacy = search.add_document(
                client.id,
                DocumentInput(
                    title="Legacy Statement", content="Period ending: 03/31/2025"
                ),
            )
            undated = search.add_document(
                client.id,
                DocumentInput(
                    title="Undated Statement", content="Statement date: 2025-03-31"
                ),
            )
        # The other columns/rows are exactly what an existing deployment would have.
        db.execute("ALTER TABLE documents DROP COLUMN document_date")

        with SearchStorePostgres.connect(dsn) as store:
            search = Search(store)
            [old, unknown] = search.search("statement")
            assert isinstance(old, Document) and isinstance(unknown, Document)
            assert old.id == legacy.id and old.document_date is None
            assert unknown.id == undated.id and unknown.document_date is None
            current = search.add_document(
                client.id,
                DocumentInput(
                    title="Current Statement", content="Period ending: 2025-06-30"
                ),
            )
        # Existing non-null values aren't overwritten, even if the content disagrees.
        db.execute(
            "UPDATE documents SET document_date = '2025-06-29' WHERE id = %s",
            (current.id,),
        )
        monkeypatch.setenv("NEVIS_POSTGRES_DSN", dsn)
        monkeypatch.setattr(
            sys, "argv", ["nevis-tiny-search", "backfill-document-dates"]
        )
        main()
        assert capsys.readouterr().out == "Updated 1 document dates.\n"
        main()
        assert capsys.readouterr().out == "Updated 0 document dates.\n"

        assert db.execute(
            "SELECT document_date, pg_typeof(document_date)::text FROM documents ORDER BY position"
        ).fetchall() == [
            (date(2025, 3, 31), "date"),
            (None, "date"),
            (date(2025, 6, 29), "date"),
        ]
        with SearchStorePostgres.connect(dsn) as store:
            [stored] = Search(store).search("legacy statement")
            assert stored == legacy
            assert "document_date" not in stored.model_dump()


def test_backfill_document_dates_requires_postgres_dsn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NEVIS_POSTGRES_DSN", raising=False)
    monkeypatch.setattr(sys, "argv", ["nevis-tiny-search", "backfill-document-dates"])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert (
        "NEVIS_POSTGRES_DSN is required for backfill-document-dates"
        in capsys.readouterr().err
    )
