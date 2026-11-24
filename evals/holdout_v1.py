"""Seed the historical holdout independently of the live evaluation corpora."""

import json
from hashlib import sha256

from nevis_search.search import Client, ClientInput, Document, DocumentInput, Search

from .read_documents import CASES_DIR

HOLDOUT_V1_SEED_PATH = CASES_DIR / "search-holdout-v1-seed.json"
# Pins the ordered Search inputs from ae990d4's seed_reed, not the file formatting.
HOLDOUT_V1_SEED_SHA256 = (
    "0780ca2cb9953624ac2679974c688b1c820559f4d641053326107747035e82fa"
)


def seed_holdout_v1(search: Search) -> dict[str, Client | Document]:
    seed = json.loads(HOLDOUT_V1_SEED_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(
        seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if sha256(canonical.encode("utf-8")).hexdigest() != HOLDOUT_V1_SEED_SHA256:
        raise ValueError(f"{HOLDOUT_V1_SEED_PATH}: holdout v1 seed SHA-256 mismatch")

    clients = {
        row["key"]: search.create_client(ClientInput.model_validate(row["input"]))
        for row in seed["clients"]
    }
    records: dict[str, Client | Document] = dict(clients)
    for row in seed["documents"]:
        records[row["key"]] = search.add_document(
            clients[row["owner"]].id, DocumentInput.model_validate(row["input"])
        )
    return records
