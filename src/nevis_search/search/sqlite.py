import json
import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from threading import Lock
from typing import Self

from .core import Client, Document, RecencyObserver
from .query_routing import route_query
from .query_rules import may_match_query_rule

__all__ = ["SearchStoreSQLite"]


def _client_from_row(row: sqlite3.Row) -> Client:
    fields = dict(row)
    fields["social_links"] = json.loads(fields["social_links"])
    return Client.model_validate(fields)


class SearchStoreSQLite:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        # Serialize whole store operations on the shared connection, not just execute().
        self._lock = Lock()

    @classmethod
    @contextmanager
    def in_memory(cls) -> Generator[Self]:
        with closing(
            sqlite3.connect(":memory:", autocommit=True, check_same_thread=False)
        ) as db:
            db.row_factory = sqlite3.Row
            db.create_function("casefold", 1, str.casefold, deterministic=True)
            db.executescript("""
                PRAGMA foreign_keys = ON;
                CREATE TABLE clients (
                    id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    description TEXT NOT NULL,
                    social_links TEXT NOT NULL
                );
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    document_date TEXT
                );
                """)
            yield cls(db)

    def insert_client(self, client: Client) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO clients
                       (id, first_name, last_name, email, description, social_links)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(client.id),
                    client.first_name,
                    client.last_name,
                    client.email,
                    client.description,
                    json.dumps(client.social_links),
                ),
            ).close()

    def insert_document(self, document: Document) -> bool:
        with self._lock:
            result = self._db.execute(
                """INSERT INTO documents (id, client_id, title, content, created_at, document_date)
                   SELECT ?, id, ?, ?, ?, ? FROM clients WHERE id = ?""",
                (
                    str(document.id),
                    document.title,
                    document.content,
                    document.created_at.isoformat(),
                    document.document_date.isoformat()
                    if document.document_date
                    else None,
                    str(document.client_id),
                ),
            )
            with closing(result):
                return result.rowcount != 0

    def _load_documents_locked(self) -> list[Document]:
        with closing(
            self._db.execute("SELECT * FROM documents ORDER BY rowid")
        ) as rows:
            return [Document.model_validate(dict(row)) for row in rows]

    def search(
        self, query: str, *, observe_recency: RecencyObserver | None = None
    ) -> list[Client | Document]:
        with self._lock:
            return self._search_locked(query, observe_recency=observe_recency)

    def _search_locked(
        self, query: str, *, observe_recency: RecencyObserver | None
    ) -> list[Client | Document]:
        if may_match_query_rule(query):
            with closing(
                self._db.execute("SELECT * FROM clients ORDER BY rowid")
            ) as rows:
                clients = [_client_from_row(row) for row in rows]
            routed = route_query(
                query,
                clients,
                self._load_documents_locked,
                observe_recency=observe_recency,
            )
            if routed is not None:
                return routed

        term = query.strip().casefold()
        client_rows = self._db.execute(
            """SELECT * FROM clients
               WHERE instr(casefold(first_name || ' ' || last_name), ?)
                  OR instr(casefold(email), ?)
                  OR instr(casefold(description), ?)
               ORDER BY rowid""",
            (term, term, term),
        )
        with closing(client_rows):
            results: list[Client | Document] = [
                _client_from_row(row) for row in client_rows
            ]
        document_rows = self._db.execute(
            """SELECT * FROM documents
               WHERE instr(casefold(title), ?) OR instr(casefold(content), ?)
               ORDER BY rowid""",
            (term, term),
        )
        with closing(document_rows):
            results.extend(Document.model_validate(dict(row)) for row in document_rows)
        return results
