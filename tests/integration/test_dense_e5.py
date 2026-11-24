import pytest

from nevis_search.config import Config
from nevis_search.search import ClientInput, DocumentInput, search_factory


@pytest.mark.parametrize("search_config", ["dense-e5"], indirect=True)
def test_dense_e5_keeps_paraphrase_when_a_literal_document_is_added(
    search_config: Config,
) -> None:
    with search_factory(search_config) as search:
        owner = search.create_client(
            ClientInput(first_name="Jane", last_name="Doe", email="jane@example.com")
        )
        paraphrase = search.add_document(
            owner.id,
            DocumentInput(
                title="Home loan update",
                content="Remaining principal on the home loan is $250,000.",
            ),
        )
        assert search.search("mortgage balance") == [paraphrase]

        literal = search.add_document(
            owner.id, DocumentInput(title="Mortgage balance", content="")
        )
        assert search.search("mortgage balance") == [literal, paraphrase]
