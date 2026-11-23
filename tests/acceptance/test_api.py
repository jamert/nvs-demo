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
    "env", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)
def test_search_proof_of_address_rule(search: SearchApi) -> None:
    owner = search.create_client(
        Client.any().model_copy(update={"description": "Address proof requested."})
    )
    other = search.create_client(
        Client.any().model_copy(update={"first_name": "Alex", "last_name": "Smith"})
    )
    form = search.add_document(
        owner,
        {
            "title": "Address change form",
            "content": f"Jane Doe address proof. PROOF-of\tADDRESS. Contact {owner.email}.",
        },
    )
    assert search.search_documents("address proof") == [form]

    other_bill = search.add_document(
        other, {"title": "Other utility bill", "content": ""}
    )
    assert search.search_documents("Jane Doe address proof") == [form]

    body = search.add_document(
        owner, {"title": "Attachments", "content": "See attached GAS STATEMENT."}
    )
    electricity = search.add_document(
        owner, {"title": "Electricity–statement", "content": ""}
    )
    utility = search.add_document(
        owner,
        {
            "title": "April utility bill",
            "content": "Jane Doe address proof. Utility bill.",
        },
    )
    gas = search.add_document(owner, {"title": "Gas bill", "content": ""})
    misleading = search.add_document(
        owner, {"title": "Utility billing notice", "content": ""}
    )

    assert search.search_clients("address proof") == [owner]
    assert search.search_documents("address proof") == [
        utility,
        other_bill,
        electricity,
        gas,
        body,
        form,
    ]
    assert search.search_documents("  PROOF-of\tADDRESS  ") == [
        other_bill,
        electricity,
        utility,
        gas,
        body,
        form,
    ]
    assert search.search_documents("Jane Doe address proof") == [
        utility,
        electricity,
        gas,
        body,
        form,
    ]
    assert search.search_documents("Doe address proof") == [
        utility,
        electricity,
        gas,
        body,
        form,
    ]

    assert search.search_clients("Jane Doe") == [owner]
    assert search.search_documents("Jane Doe") == [form, utility]
    assert search.search_clients(owner.email) == [owner]
    assert search.search_documents(owner.email) == [form]
    assert search.search_documents("utility bill") == [other_bill, utility, misleading]

    search.create_client(Client.any().model_copy(update={"first_name": "Sam"}))
    assert search.search_documents("Doe address proof") == [form, utility]

    constrained = search.add_document(
        owner, {"title": "Roe proof of address 2025", "content": "A reminder."}
    )
    assert search.search_documents("Roe proof of address 2025") == [constrained]

    named = search.create_client(
        Client.any().model_copy(update={"first_name": "Address", "last_name": "Proof"})
    )
    assert search.search_clients("Address Proof") == [owner, named]
    assert search.search_documents("Address Proof") == [form, utility]


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
