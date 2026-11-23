from datetime import UTC, datetime
from math import sqrt
from uuid import uuid4

from nevis_search.search.core import Document
from nevis_search.search.embeddings import DenseRanker


class FixtureEncoder:
    def __init__(self) -> None:
        self.passage_batches: list[list[tuple[str, str]]] = []

    def query(self, text: str) -> list[float]:
        assert text == "emergency supply checklist"
        return [1.0, 0.0]

    def passages(self, texts: list[tuple[str, str]]) -> list[list[list[float]]]:
        self.passage_batches.append(texts)
        chunks = {
            "Evacuation guide": [[0.0, 1.0], [1.0, 0.0]],
            "Readiness notes": [[1.0, 0.0]],
            "Museum opening hours": [[0.7, sqrt(1 - 0.7**2)]],
            "Storm plan": [[0.9, sqrt(1 - 0.9**2)]],
        }
        return [chunks[title] for title, _ in texts]


def test_dense_ranker_uses_best_chunk_cutoff_and_insertion_order_ties() -> None:
    owner = uuid4()

    def document(title: str) -> Document:
        return Document(
            id=uuid4(),
            client_id=owner,
            created_at=datetime.now(UTC),
            title=title,
            content="Body of " + title,
        )

    irrelevant = document("Museum opening hours")
    first = document("Evacuation guide")
    tied = document("Readiness notes")
    later = document("Storm plan")
    encoder = FixtureEncoder()
    rank = DenseRanker(encoder)
    query = "emergency supply checklist"
    assert rank(query, [irrelevant, first, tied]) == [first, tied]
    assert rank(query, [irrelevant, first, tied, later]) == [first, tied, later]
    assert encoder.passage_batches == [
        [(d.title, d.content) for d in [irrelevant, first, tied]],
        [(later.title, later.content)],
    ]
