import httpx
from pydantic import UUID4, BaseModel


class Client(BaseModel):
    id: UUID4
    first_name: str
    last_name: str
    email: str

    @staticmethod
    def new() -> dict[str, str]:
        return {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
        }


class Document(BaseModel):
    id: UUID4
    client_id: UUID4
    title: str
    content: str

    @staticmethod
    def new(client: Client) -> dict[str, str]:
        return {
            "title": "April 2026 utility bill",
            "content": (
                "Electricity account statement — Example Energy\n"
                f"Account holder: {client.first_name} {client.last_name}\n"
                "Service address: 123 Example Avenue, Portland, OR 97201\n"
                "Billing period: April 1–30, 2026\n"
                "Electricity used: 412 kWh at $0.16/kWh — $65.92\n"
                "Service charge: $12.50\n"
                "Taxes and fees: $4.70\n"
                "Total due: $83.12 by May 20, 2026"
            ),
        }


class SearchApi:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def openapi(self) -> dict[str, object]:
        response = self._http.get("/openapi.json")
        assert response.status_code == 200, response.text
        return response.json()

    def create_client(self, payload: dict[str, str]) -> Client:
        response = self._http.post("/clients", json=payload)
        assert response.status_code == 201, response.text
        return Client.model_validate(response.json())

    def add_document(self, client: Client, payload: dict[str, str]) -> Document:
        response = self._http.post(f"/clients/{client.id}/documents", json=payload)
        assert response.status_code == 201, response.text
        return Document.model_validate(response.json())

    def find_client(self, email: str) -> Client | None:
        for hit in self._search(email):
            if hit.get("email") == email:
                return Client.model_validate(hit)
        return None

    def search_documents(self, query: str) -> list[Document]:
        return [
            Document.model_validate(hit)
            for hit in self._search(query)
            if "client_id" in hit
        ]

    def _search(self, query: str) -> list[dict[str, object]]:
        response = self._http.get("/search", params={"q": query})
        assert response.status_code == 200, response.text
        return response.json()
