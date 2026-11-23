from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from nevis_search.search import Client, Document
from nevis_search.search.query_routing import route_query


def document(owner: UUID, title: str) -> Document:
    return Document(
        id=uuid4(),
        client_id=owner,
        title=title,
        content="",
        created_at=datetime.now(UTC),
    )


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

    assert route_query(" \t ", [owner], load_documents, rank) == []
    assert route_query(" \t ", [owner], load_documents) is None
    assert route_query("Reed", [owner], load_documents, rank) == [owner]
