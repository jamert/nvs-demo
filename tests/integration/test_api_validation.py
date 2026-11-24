import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest

from nevis_search.api import create_app
from nevis_search.config import Config
from tests.harness.environment import environment

pytestmark = [
    pytest.mark.usefixtures("api_config"),
    pytest.mark.parametrize(
        "search_config", ("sqlite-substring", "postgres-substring"), indirect=True
    ),
]

CLIENT = {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}
DOCUMENT = {"title": "April utility bill", "content": "Electricity charges for April."}


@pytest.fixture
def api_config(search_config: Config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEVIS_STORE", raising=False)
    for key, value in environment(search_config).envvars.items():
        monkeypatch.setenv(key, value)


@asynccontextmanager
async def api_client() -> AsyncGenerator[httpx.AsyncClient]:
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http,
    ):
        yield http


def assert_invalid_request(response: httpx.Response) -> None:
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Invalid request"}


@pytest.mark.parametrize("field", ("title", "content"))
def test_add_document_rejects_nul_in_text(field: str) -> None:
    async def exercise_api() -> None:
        async with api_client() as http:
            client = await http.post("/clients", json=CLIENT)
            assert client.status_code == 201, client.text
            path = f"/clients/{client.json()['id']}/documents"
            response = await http.post(
                path, json=DOCUMENT | {field: DOCUMENT[field] + "\x00extra"}
            )
            assert_invalid_request(response)

            valid = await http.post(path, json=DOCUMENT)
            assert valid.status_code == 201, valid.text
            assert {key: valid.json()[key] for key in DOCUMENT} == DOCUMENT

    asyncio.run(exercise_api())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("first_name", "Ja\x00ne", id="first_name"),
        pytest.param("last_name", "Do\x00e", id="last_name"),
        pytest.param("email", "ja\x00ne@example.com", id="email"),
        pytest.param("description", "Description\x00text", id="description"),
        pytest.param(
            "social_links",
            ["https://example.com/jane", "https://example.com/ja\x00ne"],
            id="social_links",
        ),
    ],
)
def test_create_client_rejects_nul_in_text(field: str, value: str | list[str]) -> None:
    async def exercise_api() -> None:
        async with api_client() as http:
            response = await http.post("/clients", json=CLIENT | {field: value})
            assert_invalid_request(response)

    asyncio.run(exercise_api())


def test_search_rejects_nul_in_query() -> None:
    async def exercise_api() -> None:
        async with api_client() as http:
            response = await http.get("/search", params={"q": "electricity\x00account"})
            assert_invalid_request(response)

    asyncio.run(exercise_api())
