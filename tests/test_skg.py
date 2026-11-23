from functools import partial

from nevis_search.config import Postgres
from nevis_search.search import ClientInput, DocumentInput, Search, search_factory
from nevis_search.search.postgres import SearchStorePostgres
from nevis_search.search.skg import rank_documents, tokenize
from tests.harness.environment import postgres_container


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
            assert search.search("Rivera violet sample") == [bridge]
            assert search.search("Rivera amethyst sample") == []

        with search_factory(Postgres(dsn, "skg")) as search:
            assert search.search("Rivera violet sample") == [bridge, related]
            assert search.search("Rivera amethyst sample") == []
            assert search.search("Rivera violet material") == [bridge]
            assert search.search("Avery Rivera") == [client, bridge]

        with SearchStorePostgres.connect(dsn, enriched) as store:
            assert Search(store).search("Rivera amethyst sample") == [related, bridge]
