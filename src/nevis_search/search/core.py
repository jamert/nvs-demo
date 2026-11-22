from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


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


class SearchStore(Protocol):
    def insert_client(self, client: Client) -> None: ...

    def insert_document(self, document: Document) -> bool:
        """Insert the document only if its client exists; return whether inserted."""
        ...

    def search(self, query: str) -> list[Client | Document]: ...


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
            **payload.model_dump(),
        )
        if not self._store.insert_document(document):
            raise ClientNotFound(client_id)
        return document

    def search(self, query: str) -> list[Client | Document]:
        return self._store.search(query)
