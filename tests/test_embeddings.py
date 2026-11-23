import json
from datetime import UTC, datetime
from io import StringIO
from math import sqrt
from pathlib import Path
from uuid import uuid4

import pytest

from nevis_search.search.core import Document
from nevis_search.search.embeddings import DenseRanker, LocalEncoder


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
    assert rank(query, []) == []
    assert rank(query, [irrelevant, first, tied]) == [first, tied]
    assert rank(query, [irrelevant, first, tied, later]) == [first, tied, later]
    assert rank(query, [later, first]) == [first, later]
    assert encoder.passage_batches == [
        [(d.title, d.content) for d in [irrelevant, first, tied]],
        [(later.title, later.content)],
    ]


def test_local_encoder_json_lines_protocol_and_closed_output() -> None:
    requests = StringIO()
    responses = StringIO("[1,0]\n[[[0,1],[1,0]]]\n")
    encoder = LocalEncoder(requests, responses)

    assert encoder.query("retirement balance") == [1, 0]
    assert encoder.passages([("Statement", "Ending balance")]) == [[[0, 1], [1, 0]]]
    assert [json.loads(line) for line in requests.getvalue().splitlines()] == [
        {"query": "retirement balance"},
        {"passages": [["Statement", "Ending balance"]]},
    ]
    with pytest.raises(RuntimeError, match="encoder stopped responding"):
        encoder.query("retirement balance")


def test_local_encoder_reports_missing_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEVIS_EMBEDDINGS_HOME", str(tmp_path))
    with (
        pytest.raises(RuntimeError, match=r"helper not found.*embeddings/setup\.sh"),
        LocalEncoder.connect(),
    ):
        pytest.fail("connected without a helper")


def test_local_encoder_rejects_invalid_startup_handshake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEVIS_EMBEDDINGS_HOME", str(tmp_path))
    helper = tmp_path / "helper/bin/nevis-embedding-encoder"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\necho 'model unavailable'\n", encoding="utf-8")
    helper.chmod(0o755)

    with (
        pytest.raises(RuntimeError, match="encoder did not initialize"),
        LocalEncoder.connect(),
    ):
        pytest.fail("connected without a ready message")
