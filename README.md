# Nevis Tiny Search

Requires [uv](https://docs.astral.sh/uv/) and Python 3.15 or later. You can pin
an interpreter locally with `uv python pin 3.15.2`.

```sh
uv sync
uv run nevis-tiny-search serve --host 127.0.0.1 --port 8000
```

`curl -i http://127.0.0.1:8000/health` returns HTTP 200 with the JSON string
`"ok"`. This is an internal readiness check, not part of the public API.

```sh
uv run pyright --warnings
uv run pytest
```

The smoke test launches the installed `nevis-tiny-search serve` command, waits
for `GET /health` to return HTTP 200, and shuts down the server on exit.

Install the pre-commit hook with `uv run pre-commit install`. It runs the
full pytest suite, isort, and Ruff lint and format checks on every commit.
Run all hooks manually with `uv run pre-commit run --all-files`.

See the [assignment](doc/assignment.md) and [OpenAPI spec](doc/openapi.yml).
