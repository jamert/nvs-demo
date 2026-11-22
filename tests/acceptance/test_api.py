import random
from uuid import uuid4

import httpx
import pytest

from tests.harness.openapi import assert_matches_assignment
from tests.harness.search_api import Client, Document
from tests.harness.server import api


def test_match_openapi_spec() -> None:
    with api() as server, server.client() as search:
        assert_matches_assignment(search.openapi())


def test_search_exact_matches() -> None:
    with api() as server, server.client() as search:
        client = search.create_client(Client.new())
        document = search.add_document(client, Document.new(client))

        assert client == search.find_client(client.email)
        assert document in search.search_documents(exact_sample_match_query(document))


@pytest.mark.parametrize(
    ("client_id", "status_code"),
    [("not-a-uuid", 422), (str(uuid4()), 404)],
)
def test_document_requires_an_existing_client(client_id: str, status_code: int) -> None:
    with api() as server:
        response = httpx.post(
            server.url(f"/clients/{client_id}/documents"),
            json={"title": "Utility bill", "content": "Electricity account statement"},
            trust_env=False,
        )
        assert response.status_code == status_code, response.text


def exact_sample_match_query(document: Document) -> str:
    """Sample two or three consecutive words at random from a single line."""
    lines = [line.split() for line in document.content.splitlines()]
    words = random.choice([line for line in lines if len(line) >= 2])
    length = random.randint(2, min(3, len(words)))
    start = random.randint(0, len(words) - length)
    return " ".join(words[start : start + length])
