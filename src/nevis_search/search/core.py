from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field

from .document_dates import extract_document_date

__all__ = [
    "Client",
    "ClientInput",
    "ClientNotFound",
    "Document",
    "DocumentInput",
    "Search",
    "SearchStore",
]


class ClientNotFound(Exception):
    pass


class ClientInput(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    description: str = ""
    social_links: list[str] = Field(default_factory=list)


class Client(ClientInput):
    id: UUID


class DocumentInput(BaseModel):
    title: str
    content: str


class Document(DocumentInput):
    id: UUID
    client_id: UUID
    created_at: datetime
    document_date: date | None = Field(default=None, exclude=True)


@dataclass(frozen=True)
class RecencyTrace:
    active: bool
    before_document_ids: tuple[UUID, ...]
    after_document_ids: tuple[UUID, ...]


type RecencyObserver = Callable[[RecencyTrace], None]


class SearchStore(Protocol):
    def insert_client(self, client: Client) -> None: ...

    def insert_document(self, document: Document) -> bool:
        """Insert the document only if its client exists; return whether inserted."""
        ...

    def search(
        self, query: str, *, observe_recency: RecencyObserver | None = None
    ) -> list[Client | Document]: ...


class Search:
    def __init__(self, store: SearchStore) -> None:
        self._store = store

    def create_client(self, payload: ClientInput) -> Client:
        client = Client(id=uuid4(), **payload.model_dump())
        self._store.insert_client(client)
        return client

    def add_document(self, client_id: UUID, payload: DocumentInput) -> Document:
        document = Document(
            id=uuid4(),
            client_id=client_id,
            created_at=datetime.now(UTC),
            document_date=extract_document_date(payload.content),
            **payload.model_dump(),
        )
        if not self._store.insert_document(document):
            raise ClientNotFound(client_id)
        return document

    def search(self, query: str) -> list[Client | Document]:
        return self._store.search(query)

    def search_with_recency_trace(
        self, query: str
    ) -> tuple[list[Client | Document], RecencyTrace]:
        """Run one search and observe recency sorting, not its candidate retrieval."""
        trace: RecencyTrace | None = None

        def observe(event: RecencyTrace) -> None:
            nonlocal trace
            trace = event

        results = self._store.search(query, observe_recency=observe)
        if trace is None:
            # No sorter ran; this also covers the stores' SQL substring fallback.
            order = tuple(row.id for row in results if isinstance(row, Document))
            trace = RecencyTrace(False, order, order)
        return results, trace
