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
    spec = search.openapi()
    assert_matches_assignment(spec)
    assert "document_date" not in str(spec)


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
    "env", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)
@pytest.mark.parametrize("newest_first", [False, True])
def test_search_explicit_plan_statement_recency(
    search: SearchApi, newest_first: bool
) -> None:
    owner = search.create_client(Client.any())
    other = search.create_client(
        Client.any().model_copy(update={"first_name": "Alex", "last_name": "Smith"})
    )
    search.add_document(
        other,
        {"title": "401(k) statement", "content": "Period ending: 2029-01-01"},
    )
    search.add_document(
        owner,
        {"title": "403(b) statement", "content": "Period ending: 2029-01-01"},
    )
    search.add_document(
        owner,
        {"title": "Utility bill", "content": "Period ending: 2029-01-01"},
    )
    march_input = {
        "title": "March 401(k) statement",
        "content": (
            "Jane Doe March 401(k) statement\n"
            "Jane Doe latest 401(k) statement for March\n"
            "Account ending: 1234\nPeriod ending: 2025-03-31"
        ),
    }
    june_input = {
        "title": "June 401(k) statement" if newest_first else "Quarterly statement",
        "content": (
            "Plan: Workplace 401(k) | Account ending: 1234\n"
            "Statement period: April 1–June 30, 2025"
        ),
    }
    first_input, last_input = (
        (june_input, march_input) if newest_first else (march_input, june_input)
    )
    first = search.add_document(owner, first_input)
    undated = search.add_document(
        owner,
        {
            "title": "Undated 401(k) statement",
            "content": "Account ending: 1234\nStatement date: 2029-01-01",
            "document_date": "2030-01-01",
        },
    )
    last = search.add_document(owner, last_input)
    june, march = (first, last) if newest_first else (last, first)
    other_account = search.add_document(
        owner,
        {
            "title": "401(k) statement",
            "content": "Account ending: 5678\nPeriod ending: 2029-01-01",
        },
    )

    # The other account and undated row keep their pre-rerank positions.
    tail = [march, other_account] if newest_first else [other_account, march]
    for cue in ("latest", "NEWEST", "current"):
        assert search.search_documents(f"Jane Doe {cue} 401(k) statement") == [
            june,
            undated,
            *tail,
        ]
    assert search.search_documents("Jane Doe March 401(k) statement") == [march]
    assert search.search_documents("Jane Doe latest 401(k) statement for March") == [
        march
    ]


@pytest.mark.parametrize(
    "env", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)
def test_search_beneficiary_and_follow_up_rules(search: SearchApi) -> None:
    owner = search.create_client(Client.any())
    other = search.create_client(
        Client.any().model_copy(update={"first_name": "Alex", "last_name": "Smith"})
    )
    search.add_document(
        owner,
        {
            "title": "Beneficiary designation — wrong account",
            "content": "Account ending: 0418. Reference number 0762.",
        },
    )
    search.add_document(
        owner,
        {
            "title": "Beneficiary designation — account ending 0762 and 0418",
            "content": "Account ending: 0762 | Account ending: 0418",
        },
    )
    search.add_document(
        owner,
        {"title": "Beneficiary designation — unsigned, no account", "content": ""},
    )
    search.add_document(
        other,
        {"title": "Beneficiary designation", "content": "Account number: xxxx0762"},
    )
    statement = search.add_document(
        owner,
        {
            "title": "Quarterly statement",
            "content": "Jane Doe who inherits account ending 0762? See the designation.",
        },
    )
    designation = search.add_document(
        owner, {"title": "Transfer-on-death designation", "content": "Account ••••0762"}
    )
    assert search.search_documents("Jane Doe who inherits account ending 0762") == [
        designation,
        statement,
    ]
    results = search.search_documents(
        "Doe, who will inherit my account ending in 0762?"
    )
    assert results[0] == designation
    assert all(doc in [designation, statement] for doc in results)
    assert search.search_documents("Jane Doe who inherits account ending 9000") == []

    search.add_document(other, {"title": "Follow-up letter", "content": "Open items."})
    query = "what was left to do after the last meeting"
    note = search.add_document(owner, {"title": "Intake note", "content": query})
    letter = search.add_document(
        owner,
        {"title": "Appointment follow-up letter", "content": "Please send a pay stub."},
    )
    results = search.search_documents(f"Jane Doe {query}")
    assert results[0] == letter
    assert all(doc in [letter, note] for doc in results)
    results = search.search_documents("Jane Doe open items from the last meeting")
    assert results[0] == letter
    assert all(doc.client_id == owner.id for doc in results)


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
