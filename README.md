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

Open [Swagger UI](http://127.0.0.1:8000/docs) to try the endpoints. By default
(`NEVIS_STORE=sqlite`), data lives in an in-memory SQLite database and is lost
when the server stops. Run a single worker in this mode.

For persistent storage, point the API at an existing PostgreSQL 18+ UTF-8 database.
The configured user needs permission to create the tables on first startup:

```sh
NEVIS_STORE=postgres NEVIS_POSTGRES_DSN=postgresql://user:password@localhost/nevis \
  uv run nevis-tiny-search serve
```

- `POST /clients` creates a client and returns its randomly generated UUIDv4.
- `POST /clients/{id}/documents` adds a text document to a client. An unknown
  client UUID returns HTTP 404; a malformed request returns HTTP 400
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
and stop the server with SIGTERM so coverage data can be saved. Only the exact-match
search test runs against both stores; other API tests use SQLite. The Postgres
case requires local Docker and starts an isolated
`postgres:18` container before launching the API. Use `uv run pytest -k 'not postgres'`
to run without Docker, or `uv run pytest --no-cov` to skip coverage.

Install the Git hooks with `uv run pre-commit install`. Rerun that command if
only the `pre-commit` hook was previously installed. The `pre-commit` hook runs
pytest, isort, and Ruff lint and format checks. Run those checks manually with
`uv run pre-commit run --all-files`.

#### Search quality eval

```sh
uv run pytest -s --no-cov evals/
```

The evals run separately from the default test suite. Each suite starts a fresh
PostgreSQL container, so both the eval command and the `commit-msg` hook require
local Docker. The five original
substring checks still compare exact result sets, ignoring order. The
[Reed ranked eval](doc/advisor-tasks.md#first-eval-batch-three-tasks) tests ten
queries against a multi-client corpus, scoring the top client or top document
according to the query’s intent. The current substring engine is not expected
to pass the ranked suite.

The `commit-msg` hook reports both suites in one trailer, for example
`Search-Eval: 6/15 cases passed (substring: 5/5 cases passed; Reed: 1/10 cases passed)`.
Missed cases lower the score but don't block the commit. Amending a commit
updates the existing trailer.

See the [assignment](doc/assignment.md) and [OpenAPI spec](doc/openapi.yml).
