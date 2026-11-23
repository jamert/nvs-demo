# Nevis Tiny Search

### Quick start

Start the API and PostgreSQL 18 with Docker Compose:

```sh
docker compose up --build --wait
```

The API is at `http://127.0.0.1:8000`. Compose defaults to `dense-e5`, which
had the best overall top-1 score in the [search benchmark](doc/search/expanded-benchmark.md).
The image installs the locked helper and downloads the checksum-verified model
at build time. The first build needs internet access; inference runs inside the
container. No local Python, PostgreSQL, or helper installation is needed.

Set `NEVIS_SEARCH` to try another mode, and `NEVIS_HTTP_PORT` to change the
host port. Compose supplies the database connection; PostgreSQL is not
published to the host. The built-in credentials are for local use only.

```sh
NEVIS_SEARCH=bm25 NEVIS_HTTP_PORT=8080 docker compose up --wait
```

`docker compose down` stops the stack and keeps its PostgreSQL data. Use
`docker compose down -v` only if you want to delete that data.

To check the containerized API end to end, run the standalone smoke script
(requires Docker Compose, `curl`, and `jq`, not pytest):

```sh
./scripts/smoke-compose.sh
```

It starts a separate stack on an available port, checks readiness, creates a
client and document, verifies exact and proof-of-address search, and exercises
the Dense E5 fallback. It removes its own containers and data on exit. The
script also accepts a `NEVIS_SEARCH` override.

To run directly on your machine instead, use [uv](https://docs.astral.sh/uv/) with Python 3.15.2
(pinned in `.python-version`):

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

#### Proof-of-address search

With the server running, these commands create a fictional client, add a
bill, and find it by intent rather than by its exact wording (requires `jq`):

```sh
CLIENT_ID=$(curl -fsS http://127.0.0.1:8000/clients \
  --json '{"first_name":"Jane","last_name":"Doe","email":"jane.doe@example.com"}' \
  | jq -er '.id')
curl -fsS "http://127.0.0.1:8000/clients/$CLIENT_ID/documents" \
  --json '{"title":"April utility bill","content":"Electricity charges for April."}'
curl -fsS -G http://127.0.0.1:8000/search \
  --data-urlencode 'q=Jane Doe proof of address'
```

Example search response (IDs and timestamp vary):

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

All five modes apply the same rule. The query must be `address proof` or
`proof of address` with no extra words except a uniquely matched full name
(or surname). The phrase matcher ignores case and treats whitespace and
punctuation as word separators. The rule does not run for exact name or email
lookups, ambiguous owners, or additional constraints such as `2025`. When a
unique owner is found, the document results are limited to that client.

The rule adds documents with `utility bill`, `electricity statement`, `gas
bill`, or `gas statement` in the title or body, even when there are literal
matches. It returns each document once, with title cues ahead of body cues
and ordinary hits last. The selected search mode still supplies ordinary
hits, and its order is preserved within each tier for those hits. Searching
for `utility bill` does not trigger the rule in reverse.

A phrase is only a retrieval cue: a form that merely mentions a bill can
still get promoted, and a form that has no bill phrase can still match
normally. The rule does not verify addresses, signatures, dates, or which
bill is most recent.

#### Latest retirement plan statement search

All five modes recognize queries such as `Jane Doe latest 401(k) statement`
(or `newest` or `current`). `Current` means latest by statement period end,
not proof of validity. The rule accepts an optional `the`, `401(k)` / `401k`
or `403(b)` / `403b`, and `statement` or `statements`. A unique full name or
surname scopes the search to that client. Ambiguous or unknown names, extra
constraints such as `March 2025`, and exact name and email lookups keep their
normal behavior.

The cue is removed before retrieval. Documents with clear evidence of the
requested plan and a statement can join the candidates even if another
version matched literally. Only dated versions of the same client's plan
and account are reordered, newest first, in their existing result slots.
Ties, undated documents and unrelated hits keep their existing order and
positions. Account labels such as `Account ending: 0418` split versions into
separate groups; an unlabeled statement is never assumed to belong to a
labeled account. Unlabeled versions can be compared when no candidate for
that client and plan has an account label.

The period end is extracted from the document body on upload. For example,
`Statement period: April 1–June 30, 2025`, `Period ending: June 30, 2025`,
`Period ending: 2025-06-30` and `Statement period: 2025-04-01/2025-06-30`
are supported as standalone lines or pipe-separated fields. Missing,
conflicting, unsupported or invalid labels leave the date unset. The search
never uses upload dates, unlabeled dates, statement issue dates or due dates
as substitutes. This metadata is internal; the API has no date input or
output field for it.

**Existing PostgreSQL data:** startup adds the nullable `document_date`
column if needed, without scanning or updating document bodies. Existing
rows remain searchable as undated until backfilled. After building the
updated Compose image, run this maintenance command explicitly:

```sh
docker compose run --rm search /app/.venv/bin/nevis-tiny-search backfill-document-dates
```

Outside Compose, set `NEVIS_POSTGRES_DSN` to the same database and run
`uv run --locked nevis-tiny-search backfill-document-dates`. The database
role must own the tables to apply the column migration. The command reports
how many rows it filled and can be repeated safely: it only fills nulls
with an unambiguous period end and never overwrites an existing date.

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
and stop the server with SIGTERM so coverage data can be saved. Exact-match,
proof-of-address, and latest statement acceptance run against every approach;
the other API contract tests use SQLite.
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
order. The ranked groups judge the top result of the requested type: ten
[Reed queries](doc/advisor-tasks.md#first-eval-batch-three-tasks), ten matched
Jamie Krag queries, ten matched Aimee Smith-Krag queries, five extra Krag
household queries, and seven
[typo variants](doc/advisor-tasks.md#krag-and-typo-eval-groups).

The `commit-msg` hook writes separate `Search-Eval-Substring`, `Search-Eval-BM25`,
`Search-Eval-Dense-E5`, and `Search-Eval-SKG` trailers with separate exact-set,
Reed, Krag, Aimee, Krag extras, and typo scores. Each approach runs against the same
fixtures regardless of `NEVIS_SEARCH`.
Relevance misses lower scores but don't block commits; setup errors do. Amending a commit
updates its trailers, replacing the old combined `Search-Eval` trailer.

See the [expanded benchmark and replay commands](doc/search/expanded-benchmark.md),
[original comparison](doc/search/comparison.md), [assignment](doc/assignment.md),
and [OpenAPI spec](doc/openapi.yml).
