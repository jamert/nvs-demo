from collections.abc import Generator

import httpx
import pytest

from nevis_search.config import POSTGRES_APPROACHES, Config
from tests.harness.environment import environment
from tests.harness.openapi import assert_matches_assignment
from tests.harness.search_api import Client, ClientBuilder, Document, SearchApi
from tests.harness.server import api


@pytest.fixture
def search(search_config: Config) -> Generator[SearchApi]:
    with api(environment(search_config)) as server, server.client() as client:
        yield client


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


@pytest.mark.parametrize("search_config", ["dense-e5"], indirect=True)
def test_find_document_without_naming_its_client(search: SearchApi) -> None:
    owner = search.create_client(Client.any())
    document = search.add_document(owner, Document.any(for_=owner))

    # "bill" is part of the search phrase, not a reference to this unrelated client.
    search.create_client(ClientBuilder().with_last_name("Bill").build())

    assert document in search.search_documents("utility bill")


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
