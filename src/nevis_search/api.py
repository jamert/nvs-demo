from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from nevis_search.search import (
    Client,
    ClientInput,
    ClientNotFound,
    Document,
    DocumentInput,
    Search,
    search_factory,
)

router = APIRouter()


async def get_search(request: Request) -> Search:
    return request.app.state.search


type SearchDependency = Annotated[Search, Depends(get_search)]


@router.get("/health", include_in_schema=False)
async def health() -> str:
    return "ok"


@router.post("/clients", status_code=201, response_description="Client created")
async def create_client(payload: ClientInput, service: SearchDependency) -> Client:
    return service.create_client(payload)


@router.post(
    "/clients/{id}/documents",
    status_code=201,
    response_description="Document created",
    responses={404: {"description": "Client not found"}},
)
async def add_document(
    id: UUID, payload: DocumentInput, service: SearchDependency
) -> Document:
    return service.add_document(id, payload)


@router.get("/search", response_description="Search results")
async def search(
    service: SearchDependency, q: Annotated[str, Query(pattern=r"\S")]
) -> list[Client | Document]:
    return service.search(q)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    with search_factory() as service:
        app.state.search = service
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="API",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            400: {"description": "Invalid request"},
            # A 4XX entry suppresses FastAPI's default OpenAPI 422 response;
            # the validation handler below returns 400 instead.
            "4XX": {"description": "Client error"},
        },
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "Invalid request"})

    @app.exception_handler(ClientNotFound)
    async def client_not_found(_: Request, exc: ClientNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Client not found"})

    app.include_router(router)
    return app
