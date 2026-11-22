import random

import pytest

from tests.harness.search_api import Client, Document
from tests.harness.server import api


def test_smoke() -> None:
    with api():  # Waits for GET /health to return HTTP 200.
        pass


@pytest.mark.xfail(
    reason="Client, document, and search endpoints are not implemented",
    raises=AssertionError,
    strict=True,
)
def test_search_exact_matches() -> None:
    with api() as server, server.client() as search:
        client = search.create_client(Client.new())
        document = search.add_document(client, Document.new(client))

        assert client == search.find_client(client.email)
        assert document in search.search_documents(exact_sample_match_query(document))


def exact_sample_match_query(document: Document) -> str:
    """Sample two or three consecutive words at random from a single line."""
    lines = [line.split() for line in document.content.splitlines()]
    words = random.choice([line for line in lines if len(line) >= 2])
    length = random.randint(2, min(3, len(words)))
    start = random.randint(0, len(words) - length)
    return " ".join(words[start : start + length])
