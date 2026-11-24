import json
from functools import partial
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from evals import holdout_v1, search_quality
from evals.compare import compare
from evals.holdout_v1 import (
    HOLDOUT_V1_SEED_PATH,
    HOLDOUT_V1_SEED_SHA256,
    seed_holdout_v1,
)
from evals.read_documents import CORPORA
from nevis_search.config import SQLite
from nevis_search.search import ClientInput, DocumentInput, search_factory


def test_seed_holdout_v1_sends_frozen_inputs_to_search_in_order() -> None:
    seed = json.loads(HOLDOUT_V1_SEED_PATH.read_text(encoding="utf-8"))
    calls = Mock()
    with (
        search_factory(SQLite()) as search,
        patch.object(search, "create_client", wraps=search.create_client) as create,
        patch.object(search, "add_document", wraps=search.add_document) as add,
    ):
        calls.attach_mock(create, "create_client")
        calls.attach_mock(add, "add_document")
        records = seed_holdout_v1(search)

    assert len(seed["clients"]) == 3 and len(seed["documents"]) == 23
    assert list(records) == [row["key"] for row in seed["clients"] + seed["documents"]]
    assert calls.mock_calls == [
        *(
            call.create_client(ClientInput.model_validate(row["input"]))
            for row in seed["clients"]
        ),
        *(
            call.add_document(
                records[row["owner"]].id, DocumentInput.model_validate(row["input"])
            )
            for row in seed["documents"]
        ),
    ]


@pytest.mark.parametrize("change", ["client", "document", "order"])
def test_seed_holdout_v1_rejects_changed_inputs_before_ingestion(
    change: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = json.loads(HOLDOUT_V1_SEED_PATH.read_text(encoding="utf-8"))
    if change == "client":
        seed["clients"][0]["input"]["first_name"] = "Changed"
    elif change == "document":
        seed["documents"][0]["input"]["content"] = "Changed"
    else:
        seed["documents"].reverse()
    path = tmp_path / HOLDOUT_V1_SEED_PATH.name
    path.write_text(json.dumps(seed), encoding="utf-8")
    monkeypatch.setattr(holdout_v1, "HOLDOUT_V1_SEED_PATH", path)

    with (
        search_factory(SQLite()) as search,
        patch.object(search, "create_client", wraps=search.create_client) as create,
        pytest.raises(ValueError, match="holdout v1 seed SHA-256 mismatch"),
    ):
        seed_holdout_v1(search)
    create.assert_not_called()


def test_compare_holdout_v1_is_independent_of_live_ranked_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = compare("sqlite-substring")
    rows = [
        json.loads(line)
        for line in CORPORA["krag"].read_text(encoding="utf-8").splitlines()
    ]
    power = next(row for row in rows if row["key"] == "power-current")
    power["content"] += (
        "\njamie krag current electricity bill"
        "\njamie krag evidence of where he lives now"
    )
    changed_krag = tmp_path / "krag.jsonl"
    changed_krag.write_text(
        "".join(f"{json.dumps(row)}\n" for row in reversed(rows)), encoding="utf-8"
    )
    monkeypatch.setitem(CORPORA, "krag", changed_krag)
    negative_query = "aimee smith-krag dental insurance enrollment confirmation"
    monkeypatch.setattr(
        search_quality, "ClientInput", partial(ClientInput, description=negative_query)
    )

    with search_factory(SQLite()) as search:
        search_quality.seed_ranked(search)
        assert len(search.search(negative_query)) == 3
    after = compare("sqlite-substring")
    assert after["krag_extras_top1"] != before["krag_extras_top1"]
    assert {
        key: value for key, value in after.items() if key.startswith("holdout_")
    } == {key: value for key, value in before.items() if key.startswith("holdout_")}
    assert after["holdout_seed"] == {"version": 1, "sha256": HOLDOUT_V1_SEED_SHA256}
