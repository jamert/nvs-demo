import random
from collections.abc import Generator

import httpx
import pytest

from nevis_search.config import POSTGRES_APPROACHES
from tests.harness.environment import Environment, environment
from tests.harness.openapi import assert_matches_assignment
from tests.harness.search_api import Client, ClientBuilder, Document, SearchApi
from tests.harness.server import api


@pytest.fixture
def env(request: pytest.FixtureRequest) -> Generator[Environment]:
    with environment(getattr(request, "param", "sqlite-substring")) as ready:
        yield ready


@pytest.fixture
def search(env: Environment) -> Generator[SearchApi]:
    with api(env) as server, server.client() as client:
        yield client


def test_match_openapi_spec(search: SearchApi) -> None:
    assert_matches_assignment(search.openapi())


@pytest.mark.parametrize(
    "env", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)
def test_search_exact_matches(search: SearchApi) -> None:
    client = search.create_client(Client.any())
    document = search.add_document(client, Document.any(for_=client))

    assert client == search.find_client(client.email)
    assert document in search.search_documents(exact_sample_match_query(document))


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


def exact_sample_match_query(document: Document) -> str:
    """Sample two or three consecutive words at random from a single line."""
    lines = [line.split() for line in document.content.splitlines()]
    words = random.choice([line for line in lines if len(line) >= 2])
    length = random.randint(2, min(3, len(words)))
    start = random.randint(0, len(words) - length)
    return " ".join(words[start : start + length])
