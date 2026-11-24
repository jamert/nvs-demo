from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Self

import psycopg
from psycopg.rows import dict_row

from .core import Client, Document, RecencyObserver
from .document_dates import extract_document_date
from .query_routing import RankDocuments, route_query
from .query_rules import may_match_query_rule

__all__ = ["SearchStorePostgres"]


class SearchStorePostgres:
    def __init__(
        self,
        db: psycopg.Connection[dict[str, Any]],
        rank: RankDocuments | None,
        *,
        append_ranked_to_literal: bool = False,
    ) -> None:
        self._db = db
        self._rank = rank
        self._append_ranked_to_literal = append_ranked_to_literal

    @classmethod
    @contextmanager
    def connect(
        cls,
        dsn: str,
        rank: RankDocuments | None = None,
        *,
        append_ranked_to_literal: bool = False,
    ) -> Generator[Self]:
        with psycopg.Connection[dict[str, Any]].connect(
            dsn, row_factory=dict_row, autocommit=True
        ) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    position bigint GENERATED ALWAYS AS IDENTITY,
                    id uuid PRIMARY KEY,
                    first_name text NOT NULL,
                    last_name text NOT NULL,
                    email text NOT NULL,
                    description text NOT NULL,
                    social_links text[] NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    position bigint GENERATED ALWAYS AS IDENTITY,
                    id uuid PRIMARY KEY,
                    client_id uuid NOT NULL REFERENCES clients(id),
                    title text NOT NULL,
                    content text NOT NULL,
                    created_at timestamptz NOT NULL
                );
                ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_date date
            """)
            yield cls(db, rank, append_ranked_to_literal=append_ranked_to_literal)

    def insert_client(self, client: Client) -> None:
        self._db.execute(
            """INSERT INTO clients (id, first_name, last_name, email, description, social_links)
               VALUES (%(id)s, %(first_name)s, %(last_name)s, %(email)s, %(description)s, %(social_links)s)""",
            client.model_dump(),
        )

    def insert_document(self, document: Document) -> bool:
        result = self._db.execute(
            """INSERT INTO documents (id, client_id, title, content, created_at, document_date)
               SELECT %(id)s, id, %(title)s, %(content)s, %(created_at)s, %(document_date)s
               FROM clients WHERE id = %(client_id)s""",
            document.model_dump() | {"document_date": document.document_date},
        )
        return result.rowcount != 0

    def backfill_document_dates(self) -> int:
        updated = 0
        rows = self._db.execute(
            "SELECT id, content FROM documents WHERE document_date IS NULL"
        )
        for row in rows:
            if (document_date := extract_document_date(row["content"])) is not None:
                result = self._db.execute(
                    """UPDATE documents SET document_date = %s
                       WHERE id = %s AND document_date IS NULL""",
                    (document_date, row["id"]),
                )
                updated += result.rowcount
        return updated

    def _load_documents(self) -> list[Document]:
        rows = self._db.execute("SELECT * FROM documents ORDER BY position")
        return [Document.model_validate(row) for row in rows]

    def search(
        self, query: str, *, observe_recency: RecencyObserver | None = None
    ) -> list[Client | Document]:
        if self._rank is not None or may_match_query_rule(query):
            clients = self._db.execute("SELECT * FROM clients ORDER BY position")
            routed = route_query(
                query,
                [Client.model_validate(row) for row in clients],
                self._load_documents,
                self._rank,
                append_ranked_to_literal=self._append_ranked_to_literal,
                observe_recency=observe_recency,
            )
            if routed is not None:
                return routed

        params = {"term": query.strip().casefold()}
        clients = self._db.execute(
            """SELECT * FROM clients
               WHERE strpos(casefold((first_name || ' ' || last_name) COLLATE pg_unicode_fast), %(term)s) > 0
                  OR strpos(casefold(email COLLATE pg_unicode_fast), %(term)s) > 0
                  OR strpos(casefold(description COLLATE pg_unicode_fast), %(term)s) > 0
               ORDER BY position""",
            params,
        )
        documents = self._db.execute(
            """SELECT * FROM documents
               WHERE strpos(casefold(title COLLATE pg_unicode_fast), %(term)s) > 0
                  OR strpos(casefold(content COLLATE pg_unicode_fast), %(term)s) > 0
               ORDER BY position""",
            params,
        )
        results: list[Client | Document] = [
            Client.model_validate(row) for row in clients
        ]
        results.extend(Document.model_validate(row) for row in documents)
        return results
