from collections.abc import Generator
from dataclasses import dataclass

import pytest

from nevis_search.config import POSTGRES_APPROACHES, Config
from nevis_search.search import (
    Client,
    ClientInput,
    Document,
    DocumentInput,
    Search,
    search_factory,
)

pytestmark = pytest.mark.parametrize(
    "search_config", ("sqlite-substring", *POSTGRES_APPROACHES), indirect=True
)


@dataclass
class Scenario:
    search: Search
    owner: Client

    def add(
        self, title: str, content: str = "", *, owner: Client | None = None
    ) -> Document:
        return self.search.add_document(
            (owner or self.owner).id, DocumentInput(title=title, content=content)
        )

    def documents(self, query: str) -> list[Document]:
        return [hit for hit in self.search.search(query) if isinstance(hit, Document)]


@pytest.fixture
def scenario(search_config: Config) -> Generator[Scenario]:
    with search_factory(search_config) as search:
        owner = search.create_client(
            ClientInput(
                first_name="Jane",
                last_name="Doe",
                email="jane@example.com",
                description="Address proof requested.",
            )
        )
        yield Scenario(search, owner)


@pytest.fixture
def other(scenario: Scenario) -> Client:
    return scenario.search.create_client(
        ClientInput(first_name="Alex", last_name="Smith", email="alex@example.com")
    )


def test_address_proof_prioritizes_title_then_body_without_duplicates(
    scenario: Scenario,
) -> None:
    form = scenario.add("Address change form", "Address proof. PROOF-of\tADDRESS.")
    attachment = scenario.add("Attachments", "See attached GAS STATEMENT.")
    electricity = scenario.add("Electricity–statement")
    utility = scenario.add("April utility bill", "Address proof. Utility bill.")
    gas = scenario.add("Gas bill")
    billing_notice = scenario.add("Utility billing notice")

    assert scenario.search.search("address proof") == [
        scenario.owner,
        utility,
        electricity,
        gas,
        attachment,
        form,
    ]
    assert scenario.documents("  PROOF-of\tADDRESS  ") == [
        electricity,
        utility,
        gas,
        attachment,
        form,
    ]
    assert scenario.documents("utility bill") == [utility, billing_notice]


def test_address_proof_scopes_full_name_and_surname(
    scenario: Scenario, other: Client
) -> None:
    scenario.add("Other utility bill", owner=other)
    form = scenario.add("Address change form", "Jane Doe address proof.")
    assert scenario.documents("Jane Doe address proof") == [form]

    bill = scenario.add("Utility bill")
    assert scenario.documents("Jane Doe address proof") == [bill, form]
    assert scenario.documents("Doe address proof") == [bill, form]

    scenario.search.create_client(
        ClientInput(first_name="Sam", last_name="Doe", email="sam@example.com")
    )
    assert scenario.documents("Doe address proof") == [form]


def test_address_proof_rule_does_not_override_exact_client_lookup(
    scenario: Scenario,
) -> None:
    form = scenario.add(
        "Address change form", "Jane Doe address proof. jane@example.com"
    )
    scenario.add("Utility bill")
    named = scenario.search.create_client(
        ClientInput(first_name="Address", last_name="Proof", email="named@example.com")
    )

    assert scenario.search.search("Address Proof") == [scenario.owner, named, form]
    assert scenario.search.search("Jane Doe") == [scenario.owner, form]
    assert scenario.search.search(scenario.owner.email) == [scenario.owner, form]


def test_address_proof_rule_preserves_extra_constraints(scenario: Scenario) -> None:
    constrained = scenario.add("Roe proof of address 2025")
    scenario.add("Utility bill")

    assert scenario.documents("Roe proof of address 2025") == [constrained]


@pytest.mark.parametrize(
    "newest_first", [False, True], ids=["oldest-first", "newest-first"]
)
def test_statement_recency_reorders_only_comparable_dated_statements(
    scenario: Scenario, other: Client, newest_first: bool
) -> None:
    scenario.add("401(k) statement", "Period ending: 2029-01-01", owner=other)
    scenario.add("403(b) statement", "Period ending: 2029-01-01")
    scenario.add("Utility bill", "Period ending: 2029-01-01")
    march_input = (
        "March 401(k) statement",
        "Account ending: 1234\nPeriod ending: 2025-03-31",
    )
    june_input = (
        "June 401(k) statement" if newest_first else "Quarterly statement",
        "Plan: Workplace 401(k) | Account ending: 1234\nStatement period: April 1–June 30, 2025",
    )
    first_input, last_input = (
        (june_input, march_input) if newest_first else (march_input, june_input)
    )
    first = scenario.add(*first_input)
    undated = scenario.add(
        "Undated 401(k) statement", "Account ending: 1234\nStatement date: 2029-01-01"
    )
    last = scenario.add(*last_input)
    june, march = (first, last) if newest_first else (last, first)
    other_account = scenario.add(
        "401(k) statement", "Account ending: 5678\nPeriod ending: 2029-01-01"
    )

    tail = [march, other_account] if newest_first else [other_account, march]
    assert scenario.documents("Jane Doe latest 401(k) statement") == [
        june,
        undated,
        *tail,
    ]


@pytest.mark.parametrize(
    "same_account", [False, True], ids=["different-accounts", "same-account"]
)
def test_statement_recency_groups_masked_accounts(
    scenario: Scenario, same_account: bool
) -> None:
    march = scenario.add(
        "March 401(k) statement", "Account ••••0762\nPeriod ending: 2025-03-31"
    )
    june_suffix = "0762" if same_account else "0418"
    june = scenario.add(
        "June 401(k) statement", f"Account ••••{june_suffix}\nPeriod ending: 2025-06-30"
    )

    expected = [june, march] if same_account else [march, june]
    assert scenario.documents("Jane Doe latest 401(k) statement") == expected


@pytest.mark.parametrize("cue", ["NEWEST", "current"])
def test_statement_recency_accepts_aliases(scenario: Scenario, cue: str) -> None:
    march = scenario.add(
        "March 401(k) statement",
        "Account ending balance: $100\nPeriod ending: 3/31/2025",
    )
    june = scenario.add("June 401(k) statement", "Period ending: 6/30/2025")

    assert scenario.documents(f"{cue} 401(k) statement") == [june, march]


def test_statement_recency_preserves_explicit_period_query(scenario: Scenario) -> None:
    march = scenario.add(
        "March 401(k) statement",
        "Jane Doe March 401(k) statement\nJane Doe latest 401(k) statement for March\n"
        "Period ending: 2025-03-31",
    )
    scenario.add("June 401(k) statement", "Period ending: 2025-06-30")

    assert scenario.documents("Jane Doe March 401(k) statement") == [march]
    assert scenario.documents("Jane Doe latest 401(k) statement for March") == [march]


def test_beneficiary_rule_requires_a_matching_account_and_owner(
    scenario: Scenario, other: Client
) -> None:
    scenario.add(
        "Beneficiary designation — wrong account",
        "Account ending: 0418. Reference number 0762.",
    )
    scenario.add(
        "Beneficiary designation — multiple accounts",
        "Account ending: 0762 | Account ending: 0418",
    )
    scenario.add("Beneficiary designation — no account")
    scenario.add("Beneficiary designation — full number", "Account number: 07620418")
    scenario.add("Beneficiary designation — full number", "Account number: 04180762")
    scenario.add("Beneficiary designation — split number", "Account number: 0762-0418")
    scenario.add("Beneficiary designation — malformed suffix", "Account ••••0762x")
    scenario.add("Beneficiary designation", "Account number: xxxx0762", owner=other)
    statement = scenario.add(
        "Quarterly statement",
        "Jane Doe who inherits account ending 0762? See the designation.",
    )
    designation = scenario.add("Transfer-on-death designation", "Account ••••0762")
    attachment = scenario.add(
        "Attached form", "Beneficiary designation. Account number: xxxx0762."
    )

    assert scenario.documents("Jane Doe who inherits account ending 0762") == [
        designation,
        attachment,
        statement,
    ]
    alternate = scenario.documents("Doe, who will inherit my account ending in 0762?")
    assert alternate[:2] == [designation, attachment]
    assert all(doc in [designation, attachment, statement] for doc in alternate)
    assert scenario.documents("Jane Doe who inherits account ending 9000") == []


def test_follow_up_rule_ranks_letter_above_literal_note(
    scenario: Scenario, other: Client
) -> None:
    scenario.add("Follow-up letter", "Open items.", owner=other)
    query = "what was left to do after the last meeting"
    note = scenario.add("Intake note", f"Jane Doe {query}")
    letter = scenario.add("Appointment follow-up letter", "Please send a pay stub.")

    assert scenario.documents(f"Jane Doe {query}") == [letter, note]
    results = scenario.documents("Jane Doe open items from the last meeting")
    assert results[0] == letter
    assert all(doc.client_id == scenario.owner.id for doc in results)
