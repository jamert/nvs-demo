from functools import partial

from nevis_search.config import Postgres
from nevis_search.search import ClientInput, DocumentInput, Search, search_factory
from nevis_search.search.postgres import SearchStorePostgres
from nevis_search.search.skg import TermIndex, rank_documents, tokenize
from tests.harness.environment import postgres_container


def test_skg_keeps_the_stronger_seed_and_skips_background_associations() -> None:
    corpus = (
        "alpha pigment common",
        "alpha pigment",
        "beta pigment",
        "other common",
        "other common",
        "other",
    )
    index = TermIndex(tuple(map(tokenize, corpus)))
    edges = index.expansion_edges(tokenize("alpha beta"), set(index.postings))

    assert [edge.term for edge in edges] == ["pigment"]
    assert edges[0].seeds == ("alpha",)
    assert edges[0].supporting_docs == {0, 1}


def test_skg_with_no_documents_returns_no_results() -> None:
    assert rank_documents("retirement statement", [], expand=True) == []


def test_skg_search_expands_from_corpus_evidence() -> None:
    lexical = partial(rank_documents, expand=False)
    enriched = partial(
        rank_documents, expand=True, enrichment=(tokenize("Amethyst pigment"),)
    )
    with postgres_container() as dsn:
        with SearchStorePostgres.connect(dsn, lexical) as store:
            search = Search(store)
            client = search.create_client(
                ClientInput(
                    first_name="Avery", last_name="Rivera", email="a@example.com"
                )
            )
            other = search.create_client(
                ClientInput(first_name="Sam", last_name="Green", email="s@example.com")
            )
            bridge = search.add_document(
                client.id,
                DocumentInput(
                    title="Violet material", content="Pigment for Avery Rivera"
                ),
            )
            related = search.add_document(
                client.id, DocumentInput(title="Pigment report", content="Spectrum")
            )
            search.add_document(
                client.id, DocumentInput(title="Unrelated", content="Journal")
            )
            search.add_document(
                other.id, DocumentInput(title="Pigment report", content="Spectrum")
            )
            assert search.search("Avery Rivera violet sample") == [bridge]
            assert search.search("Avery Rivera amethyst sample") == []

        with search_factory(Postgres(dsn, "skg")) as search:
            assert search.search("Avery Rivera violet sample") == [bridge, related]
            assert search.search("Avery Rivera amethyst sample") == []
            assert search.search("Avery Rivera violet material") == [bridge]
            assert search.search("Avery Rivera") == [client, bridge]

        with SearchStorePostgres.connect(dsn, enriched) as store:
            assert Search(store).search("Avery Rivera amethyst sample") == [
                related,
                bridge,
            ]
