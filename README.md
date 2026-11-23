# Nevis Tiny Search

Requires [uv](https://docs.astral.sh/uv/) and Python 3.15 or later. You can pin
an interpreter locally with `uv python pin 3.15.2`.

```sh
uv sync
uv run nevis-tiny-search serve --host 127.0.0.1 --port 8000
```

`curl -i http://127.0.0.1:8000/health` returns HTTP 200 with the JSON string
`"ok"`. This is an internal readiness check, not part of the public API.

### API

Open [Swagger UI](http://127.0.0.1:8000/docs) to try the endpoints.
`NEVIS_SEARCH` selects exactly one search approach for the process:

| `NEVIS_SEARCH` | Storage | Search |
|---|---|---|
| `sqlite-substring` (default) | In-memory SQLite | Case-insensitive substring |
| `postgres-substring` | PostgreSQL | Case-insensitive substring |
| `bm25` | PostgreSQL | Exact/literal lookup, then [Okapi BM25](doc/search/bm25.md) |
| `dense-e5` | PostgreSQL | Exact/literal lookup, then [local E5 embeddings](doc/search/dense-e5.md) |
| `skg` | PostgreSQL | Exact/literal lookup, then [corpus-derived query expansion](doc/search/skg.md) |

If you previously used `NEVIS_STORE=sqlite` or `NEVIS_STORE=postgres`, remove it
and use `NEVIS_SEARCH=sqlite-substring` or `NEVIS_SEARCH=postgres-substring`.
SQLite data is lost when the process stops; run a single worker in that mode.
For any PostgreSQL option, use an existing PostgreSQL 18+ UTF-8 database and a
user that can create tables on first startup. The options use the same record
schema, so switching approaches does not require re-ingesting documents.

```sh
NEVIS_SEARCH=bm25 NEVIS_POSTGRES_DSN=postgresql://user:password@localhost/nevis \
  uv run nevis-tiny-search serve
```

- `POST /clients` creates a client and returns its randomly generated UUIDv4.
- `POST /clients/{id}/documents` adds a text document to a client. An unknown
  client UUID returns HTTP 404; a malformed request returns HTTP 400
- `GET /search?q=...` returns a JSON array of matching client and document
  objects, or `[]` when the selected approach finds no matches.

For example, `GET /search?q=NevisWealth` matches a client with email
`john.doe@neviswealth.com`; `GET /search?q=Electricity%20account` matches a
document containing `Electricity account statement`.

UUIDs make IDs hard to guess, but this prototype has no authentication or
authorization. Do not use it with real client data.

### Development

```sh
uv run pyright --warnings
uv run pytest
```

Pytest reports branch coverage for `src/nevis_search`, including code run
by the server subprocess. The acceptance tests launch the installed
`nevis-tiny-search serve` command, wait for `GET /health` to return HTTP 200,
and stop the server with SIGTERM so coverage data can be saved. Exact-match
acceptance runs against every approach; the other API contract tests use SQLite.
Each PostgreSQL test starts an isolated `postgres:18` Docker container. Use
`uv run pytest --no-cov` to skip coverage. The full suite, quality evaluation,
and commit hook need the [local Dense E5 setup](experiments/embeddings/README.md).
Serving any other approach does not require the helper or model.

Install the Git hooks with `uv run pre-commit install`. Rerun that command if
only the `pre-commit` hook was previously installed. The `pre-commit` hook runs
pytest, isort, and Ruff lint and format checks. Run those checks manually with
`uv run pre-commit run --all-files`.

#### Search quality eval

```sh
uv run pytest -s --no-cov evals/
```

The quality suite tests each PostgreSQL approach in isolation (not SQLite).
Both this command and the `commit-msg` hook require local Docker. Use
`-k bm25` to run just that approach. The five original exact-set checks ignore
order. The [Reed ranked eval](doc/advisor-tasks.md#first-eval-batch-three-tasks)
judges the top result of the requested type across ten queries.

The `commit-msg` hook writes separate `Search-Eval-Substring`, `Search-Eval-BM25`,
`Search-Eval-Dense-E5`, and `Search-Eval-SKG` trailers with exact-set and Reed
scores. Each approach runs against the same fixtures regardless of `NEVIS_SEARCH`.
Relevance misses lower scores but don't block commits; setup errors do. Amending a commit
updates its trailers, replacing the old combined `Search-Eval` trailer.

See the [final comparison and replay commands](doc/search/comparison.md),
[assignment](doc/assignment.md), and [OpenAPI spec](doc/openapi.yml).
