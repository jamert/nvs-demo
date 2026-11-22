from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Self

import psycopg
from psycopg.rows import dict_row

from .core import Client, Document


class SearchStorePostgres:
    def __init__(self, db: psycopg.Connection[dict[str, Any]]) -> None:
        self._db = db

    @classmethod
    @contextmanager
    def connect(cls, dsn: str) -> Generator[Self]:
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
                )
            """)
            yield cls(db)

    def insert_client(self, client: Client) -> None:
        self._db.execute(
            """INSERT INTO clients (id, first_name, last_name, email, description, social_links)
               VALUES (%(id)s, %(first_name)s, %(last_name)s, %(email)s, %(description)s, %(social_links)s)""",
            client.model_dump(),
        )

    def insert_document(self, document: Document) -> bool:
        result = self._db.execute(
            """INSERT INTO documents (id, client_id, title, content, created_at)
               SELECT %(id)s, id, %(title)s, %(content)s, %(created_at)s
               FROM clients WHERE id = %(client_id)s""",
            document.model_dump(),
        )
        return result.rowcount != 0

    def search(self, query: str) -> list[Client | Document]:
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
