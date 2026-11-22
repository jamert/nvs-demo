import json
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()


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


@router.get("/health", include_in_schema=False)
async def health() -> str:
    return "ok"


@router.post("/clients", status_code=201, response_description="Client created")
async def create_client(payload: ClientInput, request: Request) -> Client:
    client = Client(id=uuid4(), **payload.model_dump())
    db: sqlite3.Connection = request.app.state.db
    db.execute(
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
    )
    return client


@router.post(
    "/clients/{id}/documents",
    status_code=201,
    response_description="Document created",
    responses={404: {"description": "Client not found"}},
)
async def add_document(id: UUID, payload: DocumentInput, request: Request) -> Document:
    document = Document(
        id=uuid4(),
        client_id=id,
        created_at=datetime.now(UTC),
        **payload.model_dump(),
    )
    db: sqlite3.Connection = request.app.state.db
    result = db.execute(
        """INSERT INTO documents (id, client_id, title, content, created_at)
           SELECT ?, id, ?, ?, ? FROM clients WHERE id = ?""",
        (
            str(document.id),
            document.title,
            document.content,
            document.created_at.isoformat(),
            str(id),
        ),
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return document


@router.get("/search", response_description="Search results")
async def search(
    request: Request, q: Annotated[str, Query(pattern=r"\S")]
) -> list[Client | Document]:
    db: sqlite3.Connection = request.app.state.db
    term = q.strip().casefold()
    clients = db.execute(
        """SELECT * FROM clients
           WHERE instr(casefold(first_name || ' ' || last_name), ?)
              OR instr(casefold(email), ?)
              OR instr(casefold(description), ?)
           ORDER BY rowid""",
        (term, term, term),
    )
    documents = db.execute(
        """SELECT * FROM documents
           WHERE instr(casefold(title), ?) OR instr(casefold(content), ?)
           ORDER BY rowid""",
        (term, term),
    )
    results: list[Client | Document] = []
    for row in clients:
        fields = dict(row)
        fields["social_links"] = json.loads(fields["social_links"])
        results.append(Client.model_validate(fields))
    results.extend(Document.model_validate(dict(row)) for row in documents)
    return results


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # These small, synchronous queries run on the event-loop thread, as does startup.
    with closing(sqlite3.connect(":memory:", autocommit=True)) as db:
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
                created_at TEXT NOT NULL
            );
            """)
        app.state.db = db
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="API", version="1.0.0", lifespan=lifespan)
    app.include_router(router)
    return app
