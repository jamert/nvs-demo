from dataclasses import dataclass, field, replace
from uuid import uuid4

import httpx
from pydantic import BaseModel


class Client(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    description: str = ""

    @staticmethod
    def any() -> Client:
        return ClientBuilder().build()


@dataclass(frozen=True)
class ClientBuilder:
    id: str = field(default_factory=lambda: str(uuid4()))
    email: str = field(default_factory=lambda: f"jane.doe+{uuid4().hex}@example.com")

    def with_id(self, client_id: str) -> ClientBuilder:
        return replace(self, id=client_id)

    def build(self) -> Client:
        return Client(id=self.id, first_name="Jane", last_name="Doe", email=self.email)


class Document(BaseModel):
    id: str
    client_id: str
    title: str
    content: str

    @staticmethod
    def any(*, for_: Client) -> dict[str, str]:
        return {
            "title": "April 2026 utility bill",
            "content": (
                "Electricity account statement — Example Energy\n"
                f"Account holder: {for_.first_name} {for_.last_name}\n"
                "Service address: 123 Example Avenue, Portland, OR 97201\n"
                "Billing period: April 1–30, 2026\n"
                "Electricity used: 412 kWh at $0.16/kWh — $65.92\n"
                "Service charge: $12.50\n"
                "Taxes and fees: $4.70\n"
                "Total due: $83.12 by May 20, 2026"
            ),
        }


def _document_from_response(fields: dict[str, object]) -> Document:
    assert fields.keys() == {"id", "client_id", "title", "content", "created_at"}
    return Document.model_validate(fields)


class SearchApi:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def openapi(self) -> dict[str, object]:
        response = self._http.get("/openapi.json")
        assert response.status_code == 200, response.text
        return response.json()

    def create_client(self, client: Client) -> Client:
        # exclude `id` because we're creating an object here
        response = self._http.post("/clients", json=client.model_dump(exclude={"id"}))
        assert response.status_code == 201, response.text
        return Client.model_validate(response.json())

    def add_document(self, client: Client, payload: dict[str, str]) -> Document:
        response = self._http.post(f"/clients/{client.id}/documents", json=payload)
        response.raise_for_status()
        assert response.status_code == 201, response.text
        return _document_from_response(response.json())

    def find_client(self, email: str) -> Client | None:
        return next(
            (hit for hit in self.search_clients(email) if hit.email == email), None
        )

    def search_clients(self, query: str) -> list[Client]:
        return [
            Client.model_validate(hit) for hit in self._search(query) if "email" in hit
        ]

    def search_documents(self, query: str) -> list[Document]:
        return [
            _document_from_response(hit)
            for hit in self._search(query)
            if "client_id" in hit
        ]

    def _search(self, query: str) -> list[dict[str, object]]:
        response = self._http.get("/search", params={"q": query})
        assert response.status_code == 200, response.text
        return response.json()
