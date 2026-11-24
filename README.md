# Nevis Tiny Search

A REST API for finding clients by name, email, or description and searching their text documents by wording or meaning.

## Quick start

```sh
docker compose up --build --wait
```

Open [Swagger UI](http://127.0.0.1:8000/docs). Compose starts PostgreSQL 18 and uses `dense-e5` by default. The first build needs internet access to fetch dependencies and the model; inference runs locally in the container.

Set `NEVIS_SEARCH` to select a different search mode or `NEVIS_HTTP_PORT` to change the host port. `docker compose down` stops the stack and keeps its data; `docker compose down -v` deletes it.

This prototype has no authentication or authorization. Use synthetic data only.

### Run without Docker

Install [uv](https://docs.astral.sh/uv/) and use Python 3.15 or newer:

```sh
uv sync
uv run nevis-tiny-search serve
```

This defaults to in-memory SQLite. Its data is lost on restart. For a PostgreSQL mode, set `NEVIS_SEARCH` and point `NEVIS_POSTGRES_DSN` at a PostgreSQL 18+ UTF-8 database using a role that can create tables. Dense E5 also needs the [local encoder and model](experiments/embeddings/README.md).

## API

See the [OpenAPI contract](doc/openapi.yml) or [interactive API docs](http://127.0.0.1:8000/docs).

| Endpoint | Result |
|---|---|
| `POST /clients` | `201` with the new client |
| `POST /clients/{id}/documents` | `201` with the new document; `404` if the client does not exist |
| `GET /search?q=...` | `200` with an array of matching clients and documents, or `[]` |

Invalid requests return `400`.

### Proof-of-address search

Create a client and a document, then search for `proof of address`. The document can match even though it doesn't contain that phrase. These commands require `curl` and `jq`.

```sh
CLIENT_ID=$(curl -fsS http://127.0.0.1:8000/clients \
  --json '{"first_name":"Jane","last_name":"Doe","email":"jane.doe@neviswealth.example.com"}' \
  | jq -er '.id')
curl -fsS "http://127.0.0.1:8000/clients/$CLIENT_ID/documents" \
  --json '{"title":"April utility bill","content":"Electricity charges for April."}'
curl -fsSG http://127.0.0.1:8000/search \
  --data-urlencode 'q=Jane Doe proof of address'
```

Example search response:

```json
[
  {
    "title": "April utility bill",
    "content": "Electricity charges for April.",
    "id": "1e0d26f3-c104-411e-b73b-f1d7c1335cd6",
    "client_id": "e8c1cecb-9a50-40ef-a7f1-d5217cb92abc",
    "created_at": "2026-11-23T21:14:03.656096Z"
  }
]
```

`GET /search?q=NevisWealth` finds Jane by partial email. `GET /search?q=utility%20bill` searches across clients without naming an owner.

### Search modes

| `NEVIS_SEARCH` | Storage | Search |
|---|---|---|
| `sqlite-substring` (local default) | In-memory SQLite | Case-insensitive substring |
| `postgres-substring` | PostgreSQL | Case-insensitive substring |
| `bm25` | PostgreSQL | Literal lookup with [BM25 ranking](doc/search/bm25.md) |
| `dense-e5` (Compose default) | PostgreSQL | Literal matches plus [semantic embedding matches](doc/search/dense-e5.md) |
| `skg` | PostgreSQL | Literal lookup with [corpus-derived query expansion](doc/search/skg.md) |

In ranked modes, a unique full name can scope a document query to one client. A surname alone does not scope an ordinary document query, but can qualify a supported rule. All modes recognize `address proof` / `proof of address`, queries such as `Reed who inherits account ending 0762` and `Jamie Krag last appointment follow-ups`, and `Jane Doe latest 401(k) statement`. These rules retrieve likely records; they don't verify the contents.

### Statement dates for existing data

Latest-statement queries compare statements for the same client, plan, and account using period ends extracted from the body (e.g. `Period ending: 6/30/2025`), not upload dates. If a PostgreSQL database already contains documents without extracted dates, backfill them explicitly:

```sh
docker compose run --rm search /app/.venv/bin/nevis-tiny-search backfill-document-dates
```

Outside Compose, set `NEVIS_POSTGRES_DSN` and run `uv run nevis-tiny-search backfill-document-dates`.

## Tests and evaluation

Run either check against a disposable Compose stack (requires `curl` and `jq`):

```sh
./scripts/smoke-compose.sh         # quick API smoke test
./scripts/test-search-compose.sh   # seed evaluation documents and check five searches
```

The full test suite requires Docker and the [local Dense E5 setup](experiments/embeddings/README.md):

```sh
uv run pytest
uv run pyright --warnings
```

Run `uv run pytest -s --no-cov evals/` to measure search quality separately; relevance misses are expected. `uv run pre-commit install` installs the test, lint, and search-score hooks.

See the [evaluation fixtures](evals/README.md), [search benchmark](doc/search/expanded-benchmark.md), and [assignment](doc/assignment.md).
