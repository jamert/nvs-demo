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

Open [Swagger UI](http://127.0.0.1:8000/docs) to try the endpoints. Data lives in
an in-memory SQLite database and is lost when the server stops. Run a single
worker; separate processes don't share data.

- `POST /clients` creates a client and returns its randomly generated UUIDv4.
- `POST /clients/{id}/documents` adds a text document to a client. An unknown
  UUID returns HTTP 404; a malformed UUID returns HTTP 422.
- `GET /search?q=...` returns a JSON array of matching client and document
  objects, or `[]` when nothing matches. This first version uses case-insensitive
  substring matching, not semantic search.

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
and stop the server with SIGTERM so coverage data can be saved. Use
`uv run pytest --no-cov` to skip coverage.

Install the pre-commit hook with `uv run pre-commit install`. It runs the
full pytest suite, isort, and Ruff lint and format checks on every commit.
Run all hooks manually with `uv run pre-commit run --all-files`.

See the [assignment](doc/assignment.md) and [OpenAPI spec](doc/openapi.yml).
