import random

import httpx
import pytest

from tests.harness.openapi import assert_matches_assignment
from tests.harness.search_api import Client, ClientBuilder, Document
from tests.harness.server import api


def test_match_openapi_spec() -> None:
    with api() as server, server.client() as search:
        assert_matches_assignment(search.openapi())


def test_search_exact_matches() -> None:
    with api() as server, server.client() as search:
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
    client: Client, expected_status: int
) -> None:
    with api() as server, server.client() as search:
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
