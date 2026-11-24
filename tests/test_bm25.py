from datetime import UTC, datetime
from math import log1p
from uuid import uuid4

import pytest

from nevis_search.config import Postgres
from nevis_search.search import ClientInput, Document, DocumentInput, search_factory
from nevis_search.search.bm25 import BM25Index
from tests.harness.environment import postgres_container


def document(title: str, content: str) -> Document:
    return Document(
        id=uuid4(),
        client_id=uuid4(),
        title=title,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_bm25_term_scores_use_corpus_idf_length_normalization_and_saturation() -> None:
    short = document("blue", "jay")
    long = document("blue jay", "blue blue blue feather nest")
    other = document("blackbird", "song nest")
    index = BM25Index([short, long, other])

    # df=2 for blue; df=1 for feather. The average field length is 4.
    common_idf = log1p(1.5 / 2.5)
    rare_idf = log1p(2.5 / 1.5)
    assert dict(index.term_scores("blue")) == pytest.approx(
        {
            0: common_idf * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 2 / 4)),
            1: common_idf * 8.8 / (4 + 1.2 * (0.25 + 0.75 * 7 / 4)),
        }
    )
    assert dict(index.term_scores("feather")) == pytest.approx(
        {1: rare_idf * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 7 / 4))}
    )
    assert index.rank("BLUE feather") == [long, short]


def test_bm25_deduplicates_query_terms_and_ties_follow_insertion_order() -> None:
    first = document("blue", "")
    second = document("", "jay")
    index = BM25Index([first, second])

    assert index.rank("JAY, blue blue") == [first, second]
    assert index.rank("bluejay") == []
    assert BM25Index([document("", "")]).rank("blue") == []
    assert BM25Index([]).rank("blue") == []


def test_postgres_bm25_uses_owner_routing_and_literal_precedence() -> None:
    with postgres_container() as dsn, search_factory(Postgres(dsn, "bm25")) as search:
        owner = search.create_client(
            ClientInput(first_name="Ada", last_name="Vega", email="ada@example.com")
        )
        other = search.create_client(
            ClientInput(first_name="Jo", last_name="Lee", email="jo@example.com")
        )
        search.add_document(
            other.id,
            DocumentInput(title="Solar period", content="Vega assisted Ada in billing"),
        )
        first = search.add_document(
            owner.id, DocumentInput(title="Solar invoice", content="Billing period")
        )
        second = search.add_document(
            owner.id, DocumentInput(title="Solar report", content="Billing period")
        )

        referral = search.add_document(
            other.id,
            DocumentInput(title="Referral", content="From Ada Vega (ada@example.com)"),
        )

        assert search.search("ADA VEGA solar invoice") == [first]
        assert search.search("ada vega") == [owner, referral]
        assert search.search("ada@example.com") == [owner, referral]
        assert search.search("ADA VEGA solar period") == [first, second]
