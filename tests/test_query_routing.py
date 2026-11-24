from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from nevis_search.search import Client, Document
from nevis_search.search.core import RecencyTrace
from nevis_search.search.query_routing import route_query


def document(
    owner: UUID, title: str, content: str = "", document_date: date | None = None
) -> Document:
    return Document(
        id=uuid4(),
        client_id=owner,
        title=title,
        content=content,
        created_at=datetime.now(UTC),
        document_date=document_date,
    )


@pytest.mark.parametrize("owner_prefix", ["", "Reed ", "June Reed, "])
@pytest.mark.parametrize("phrase", ["mortgage balance", "march mortgage balance"])
def test_route_query_appends_ranked_results_after_literal_results_in_scope(
    owner_prefix: str, phrase: str
) -> None:
    owner = Client(
        id=uuid4(), first_name="June", last_name="Reed", email="june@example.com"
    )
    other = Client(
        id=uuid4(), first_name="Alex", last_name="Smith", email="alex@example.com"
    )
    ranked_later = document(owner.id, "Home loan summary")
    other_doc = document(other.id, f"{phrase.title()} for Alex")
    literal_first = document(owner.id, f"{phrase.title()} note")
    ranked_earlier = document(owner.id, "Outstanding principal")
    literal_second = document(owner.id, "Loan statement", phrase.title())
    documents = [ranked_later, other_doc, literal_first, ranked_earlier, literal_second]

    def rank(query: str, candidates: Sequence[Document]) -> list[Document]:
        assert query == phrase
        assert list(candidates) == [
            doc for doc in documents if not owner_prefix or doc.client_id == owner.id
        ]
        return [
            ranked_earlier,
            literal_second.model_copy(update={"title": "Ranked copy"}),
            ranked_later,
            ranked_earlier,
        ]

    expected = [literal_first, literal_second, ranked_earlier, ranked_later]
    if not owner_prefix:
        expected.insert(0, other_doc)
    assert (
        route_query(
            f"{owner_prefix}{phrase}",
            [owner, other],
            lambda: documents,
            rank,
            append_ranked_to_literal=True,
        )
        == expected
    )


def test_route_query_skips_ranking_literal_hits_by_default() -> None:
    literal = document(uuid4(), "Mortgage balance note")

    def rank(query: str, documents: Sequence[Document]) -> Sequence[Document]:
        pytest.fail("literal hits should bypass ranking by default")

    assert route_query("mortgage balance", [], lambda: [literal], rank) == [literal]


def test_route_query_does_not_apply_address_proof_rule_to_utility_bill_query() -> None:
    owner = uuid4()
    literal = document(owner, "April utility bill")
    gas = document(owner, "Gas bill")
    documents = [gas, literal]

    def rank(query: str, candidates: Sequence[Document]) -> list[Document]:
        assert query == "utility bill"
        assert list(candidates) == documents
        return []

    assert route_query(
        "utility bill", [], lambda: documents, rank, append_ranked_to_literal=True
    ) == [literal]


@pytest.mark.parametrize(
    "phrase",
    [
        "march 401(k) statement",
        "latest 401(k) statement for march",
        "latest 401(k) statement 2025",
        "2025 403(b) statements",
        "403b statement for sept.",
    ],
)
def test_route_query_keeps_literal_or_ranked_baseline_for_explicit_statement_period(
    phrase: str,
) -> None:
    owner = Client(
        id=uuid4(), first_name="Jane", last_name="Doe", email="jane@example.com"
    )
    literal = document(owner.id, phrase.title())
    ranked = document(owner.id, "Retirement statement")
    query = f"Jane Doe {phrase}"

    def rank(query: str, candidates: Sequence[Document]) -> list[Document]:
        assert query == phrase
        assert list(candidates) == [ranked]
        return [ranked]

    assert route_query(
        query, [owner], lambda: [ranked, literal], rank, append_ranked_to_literal=True
    ) == [literal]
    assert route_query(
        query, [owner], lambda: [ranked], rank, append_ranked_to_literal=True
    ) == [ranked]


@pytest.mark.parametrize(
    ("query", "literal_phrase", "rule_title", "rule_content"),
    [
        ("proof of address", "proof of address", "Utility bill", ""),
        (
            "who inherits account ending 0762",
            "who inherits account ending 0762",
            "Beneficiary designation",
            "Account ending: 0762",
        ),
        (
            "what was left to do after the last meeting",
            "what was left to do after the last meeting",
            "Follow-up letter",
            "",
        ),
        (
            "latest 401(k) statement",
            "401(k) statement",
            "Workplace statement",
            "401k Statement",
        ),
    ],
)
def test_route_query_keeps_literal_baseline_for_active_rules(
    query: str, literal_phrase: str, rule_title: str, rule_content: str
) -> None:
    owner = uuid4()
    literal = document(owner, "Client notes", f"{literal_phrase}\nAccount ending: 0762")
    candidate = document(owner, rule_title, rule_content)
    unrelated = document(owner, "Summary")

    def rank(query: str, documents: Sequence[Document]) -> Sequence[Document]:
        pytest.fail("an active rule with literal hits should not call the ranker")

    expected = (
        [literal, candidate] if query.startswith("latest") else [candidate, literal]
    )
    assert (
        route_query(
            query,
            [],
            lambda: [literal, unrelated, candidate],
            rank,
            append_ranked_to_literal=True,
        )
        == expected
    )


@pytest.mark.parametrize("query", ["June Reed", "june@example.com"])
def test_route_query_does_not_rank_exact_name_or_email_queries(query: str) -> None:
    owner = Client(
        id=uuid4(), first_name="June", last_name="Reed", email="june@example.com"
    )
    literal = document(owner.id, "June Reed, june@example.com")
    unrelated = document(owner.id, "Summary")

    def rank(query: str, documents: Sequence[Document]) -> Sequence[Document]:
        pytest.fail("exact name and email queries should not call the ranker")

    assert route_query(
        query,
        [owner],
        lambda: [unrelated, literal],
        rank,
        append_ranked_to_literal=True,
    ) == [owner, literal]


def test_route_query_keeps_ranker_order_within_rule_tiers() -> None:
    owner = Client(
        id=uuid4(), first_name="June", last_name="Reed", email="june@example.com"
    )
    other = Client(
        id=uuid4(), first_name="Alex", last_name="Smith", email="alex@example.com"
    )
    ordinary_first = document(owner.id, "Retirement statement")
    ordinary_second = document(owner.id, "Client notes")
    hint_first = document(owner.id, "Gas bill")
    hint_second = document(owner.id, "Electricity statement")
    other_bill = document(other.id, "Utility bill")
    candidates = [ordinary_first, hint_first, ordinary_second, hint_second]

    def rank(query: str, documents: Sequence[Document]) -> list[Document]:
        assert query == "proof of address"
        assert list(documents) == candidates
        return [ordinary_second, hint_second, ordinary_first, hint_first, hint_second]

    assert route_query(
        "June Reed, proof of address",
        [owner, other],
        lambda: [other_bill, *candidates],
        rank,
    ) == [hint_second, hint_first, ordinary_second, ordinary_first]


def test_route_query_does_not_rank_blank_or_owner_only_queries() -> None:
    owner = Client(
        id=uuid4(), first_name="June", last_name="Reed", email="june@example.com"
    )

    def load_documents() -> Sequence[Document]:
        pytest.fail("no documents should be loaded")

    def rank(query: str, documents: Sequence[Document]) -> Sequence[Document]:
        pytest.fail("no document query should reach the ranker")

    assert (
        route_query(
            " \t ", [owner], load_documents, rank, append_ranked_to_literal=True
        )
        == []
    )
    assert route_query(" \t ", [owner], load_documents) is None
    assert route_query(
        "Reed", [owner], load_documents, rank, append_ranked_to_literal=True
    ) == [owner]


def test_route_query_reranks_comparable_versions_only() -> None:
    query = "the latest 401(k) statements"
    clients = [
        Client(
            id=uuid4(),
            first_name=name,
            last_name="Reed",
            email=email,
            description=query,
        )
        for name, email in (("June", "june@example.com"), ("Sam", "sam@example.com"))
    ]
    owner, other = (client.id for client in clients)
    old, new, later = date(2025, 3, 31), date(2025, 6, 30), date(2029, 1, 1)

    def statement(end: date | None, account: str) -> Document:
        return document(owner, "Quarterly statement", f"401k Statement\n{account}", end)

    march = statement(old, "Account number: xx1234")
    june = statement(new, "Account: xx1234")
    tied = statement(new, "Account number: xx1234")
    undated = statement(None, "Account number: xx1234")
    account_b = statement(later, "Account number: xx5678")
    unlabeled = statement(later, "")
    another_unlabeled = statement(old, "")
    conflicts = statement(later, "Account ending: 1234 | Account ending: 5678")
    malformed = statement(later, "Account ending: unknown")
    unrelated = document(owner, "Electricity statement", "Call about my 401(k).", later)
    wrong_type = document(owner, "403b statement", document_date=later)
    both_types = document(owner, "401k/403b plan statement", document_date=later)
    other_old = document(other, "401k quarterly statement", document_date=old)
    other_new = document(other, "401k quarterly statement", document_date=new)
    baseline = [
        march,
        undated,
        unrelated,
        wrong_type,
        both_types,
        other_old,
        account_b,
        unlabeled,
        another_unlabeled,
        conflicts,
        malformed,
        june,
        tied,
        other_new,
    ]

    retrieval: list[str] = []
    traces: list[RecencyTrace] = []

    def load_documents() -> list[Document]:
        retrieval.append("load")
        return baseline

    def rank(phrase: str, candidates: Sequence[Document]) -> Sequence[Document]:
        retrieval.append("rank")
        assert phrase == "401(k) statement"
        assert list(candidates) == baseline
        return candidates

    ordered = [
        june,
        undated,
        unrelated,
        wrong_type,
        both_types,
        other_new,
        account_b,
        unlabeled,
        another_unlabeled,
        conflicts,
        malformed,
        tied,
        march,
        other_old,
    ]
    assert route_query(
        query, clients, load_documents, rank, observe_recency=traces.append
    ) == [*clients, *ordered]
    assert retrieval == ["load", "rank"]
    assert traces == [
        RecencyTrace(
            True, tuple(doc.id for doc in baseline), tuple(doc.id for doc in ordered)
        )
    ]


@pytest.mark.parametrize(
    ("march_label", "june_label"),
    [
        pytest.param(
            "Account number: 12340762", "Account ••••0762", id="number-vs-suffix"
        ),
        pytest.param(
            "Account number: 0762", "Account ••••0762", id="unmasked-vs-masked"
        ),
        pytest.param(
            "Account ••••0762 | Account ••••0418",
            "Account ••••0762",
            id="conflicting-masks",
        ),
        pytest.param(
            "Account ••••0762 | Account ••••unknown",
            "Account ••••0762",
            id="unusable-mask-alongside-valid-mask",
        ),
        pytest.param("", "", id="unlabelled-with-unusable-account-in-results"),
    ],
)
def test_route_query_does_not_infer_statement_account_identity(
    march_label: str, june_label: str
) -> None:
    owner = Client(
        id=uuid4(), first_name="June", last_name="Reed", email="june@example.com"
    )
    baseline = [
        document(owner.id, "March 401(k) statement", march_label, date(2025, 3, 31)),
        document(owner.id, "June 401(k) statement", june_label, date(2025, 6, 30)),
        document(owner.id, "Other 401(k) statement", "Account ••••unknown"),
    ]

    assert (
        route_query("June Reed latest 401(k) statement", [owner], lambda: baseline)
        == baseline
    )


@pytest.mark.parametrize(
    ("query", "rank_query"),
    [
        ("Reed latest 401(k) statement", "reed latest 401(k) statement"),
        ("Roe latest 401(k) statement", "roe latest 401(k) statement"),
        (
            "June Reed latest 401(k) statement 2025-03-31",
            "latest 401(k) statement 2025-03-31",
        ),
        (
            "June Reed latest 401(k) statement balance",
            "latest 401(k) statement balance",
        ),
        ("June Reed up-to-current 401(k) statement", "up-to-current 401(k) statement"),
        ("June Reed latestish 401(k) statement", "latestish 401(k) statement"),
        ("June Reed current 403(b) contribution", "current 403(b) contribution"),
    ],
)
def test_route_query_preserves_inactive_recency_queries(
    query: str, rank_query: str
) -> None:
    clients = [
        Client(
            id=uuid4(), first_name=name, last_name="Reed", email=f"{name}@example.com"
        )
        for name in ("June", "Sam")
    ]
    doc = document(
        clients[0].id, "401(k) quarterly statement", document_date=date(2025, 6, 30)
    )

    def rank(phrase: str, candidates: Sequence[Document]) -> Sequence[Document]:
        assert phrase == rank_query and list(candidates) == [doc]
        return []

    assert route_query(query, clients, lambda: [doc], rank) == []
    assert (
        route_query(query, clients, lambda: pytest.fail("SQL should handle this"))
        is None
    )
