from collections.abc import Generator

import httpx
import pytest

from nevis_search.config import POSTGRES_APPROACHES, Config
from tests.harness.environment import environment
from tests.harness.openapi import assert_matches_assignment
from tests.harness.search_api import Client, ClientBuilder, Document, SearchApi
from tests.harness.server import api


@pytest.fixture
def http(search_config: Config) -> Generator[httpx.Client]:
    with (
        api(environment(search_config)) as server,
        httpx.Client(base_url=server.url("/"), trust_env=False) as client,
    ):
        yield client


@pytest.fixture
def search(http: httpx.Client) -> SearchApi:
    return SearchApi(http)


def test_match_openapi_spec(search: SearchApi) -> None:
    spec = search.openapi()
    assert_matches_assignment(spec)
    assert "document_date" not in str(spec)


@pytest.mark.parametrize(
    "search_config", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)
def test_search_exact_matches(search: SearchApi) -> None:
    client = search.create_client(Client.any())
    document = search.add_document(client, Document.any(for_=client))

    assert client == search.find_client(client.email)
    assert document in search.search_documents("electricity account statement")


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [
        pytest.param(Client.any(), 404, id="unknown-id"),
        pytest.param(
            ClientBuilder().with_id("not-a-uuid").build(), 400, id="malformed-id"
        ),
    ],
)
def test_document_requires_an_existing_client(
    search: SearchApi, client: Client, expected_status: int
) -> None:
    with pytest.raises(httpx.HTTPStatusError) as error:
        search.add_document(client, Document.any(for_=client))

    assert error.value.response.status_code == expected_status


@pytest.mark.parametrize(
    "search_config", ("sqlite-substring", "postgres-substring"), indirect=True
)
@pytest.mark.parametrize("field", ("title", "content"))
def test_add_document_rejects_nul_in_text(
    http: httpx.Client, search: SearchApi, field: str
) -> None:
    client = search.create_client(Client.any())
    payload = Document.any(for_=client)

    response = http.post(
        f"/clients/{client.id}/documents",
        json=payload | {field: payload[field] + "\x00extra"},
    )

    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Invalid request"}
    document = search.add_document(client, payload)
    assert document.title == payload["title"]
    assert document.content == payload["content"]


@pytest.mark.parametrize(
    "search_config", ("sqlite-substring", "postgres-substring"), indirect=True
)
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
def test_create_client_rejects_nul_in_text(
    http: httpx.Client, field: str, value: str | list[str]
) -> None:
    payload = Client.any().model_dump(exclude={"id"})
    response = http.post("/clients", json=payload | {field: value})

    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Invalid request"}


@pytest.mark.parametrize(
    "search_config", ("sqlite-substring", "postgres-substring"), indirect=True
)
def test_search_rejects_nul_in_query(http: httpx.Client) -> None:
    response = http.get("/search", params={"q": "electricity\x00account"})

    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "Invalid request"}
