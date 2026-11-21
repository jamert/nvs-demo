# Nevis Tiny Search

Requires [uv](https://docs.astral.sh/uv/) and Python 3.15 or later. You can pin
an interpreter locally with `uv python pin 3.15.2`.

```sh
uv sync
uv run nevis-tiny-search --help
uv run pyright --warnings                          # Basic type checks; warnings fail
uv run pytest tests/harness/                       # Harness checks: pass
uv run pytest                                      # Smoke test is an expected failure
```

The smoke test uses the harness to launch the installed `nevis-tiny-search serve`
command. The harness polls `GET /health` until it gets HTTP 200 and stops the
server on exit. `/health` is an internal readiness check, not part of the
public API. The `serve` command is still a stub, so the smoke test is marked
as an expected failure. An unexpected pass fails the suite until the marker
is removed.

Install the pre-commit hook with `uv run pre-commit install`. It runs the
full pytest suite, isort, and Ruff lint and format checks on every commit.
Run all hooks manually with `uv run pre-commit run --all-files`.

See the [assignment](doc/assignment.md) and [OpenAPI spec](doc/openapi.yml).
