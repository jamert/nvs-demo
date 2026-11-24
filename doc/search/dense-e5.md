# Dense E5 retrieval

Install the [local encoder and pinned model](../../experiments/embeddings/README.md),
then select `NEVIS_SEARCH=dense-e5`:

```sh
sh experiments/embeddings/setup.sh
NEVIS_SEARCH=dense-e5 NEVIS_POSTGRES_DSN=postgresql://user:password@localhost/nevis \
  uv run --locked nevis-tiny-search serve
```

The Python 3.15 [ranker](../../src/nevis_search/search/embeddings.py) uses a
local [Python 3.12 ONNX helper](../../experiments/embeddings/src/nevis_embedding_encoder/__init__.py).
Only the explicit setup downloads model files; client records and queries
stay local. Other server options do not load the model.

## Mechanism

The [common router](../../src/nevis_search/search/query_routing.py) handles
literal lookup and owner scoping. An ordinary document query returns literal
hits first in insertion order, then semantic hits in descending score order,
keeping only the first hit for each document ID. The ranker searches the full
candidate set allowed by owner scoping, even when the query has literal hits.

Exact email/name, blank and owner-only queries bypass ranking. Recognized
proof-of-address, beneficiary, meeting follow-up and statement recency rules
keep their existing retrieval and ordering: the ranker runs only when their
literal baseline is empty. A 401(k) or 403(b) statement query containing a month
name (including standard abbreviations) or a year also keeps the literal-or-ranked
behavior, with or without a recency cue. This is a routing guard, not a date filter.

The ranker encodes the residual query with `query:` and each title/body chunk
with `passage:`. Windows are capped at 256 WordPiece tokens including special
tokens; the title prefix uses at most 32 and body windows overlap by 32. The
model's unpadded last hidden states are mean-pooled and L2-normalized to 384
dimensions. Rank by maximum chunk cosine, with a fixed cutoff of 0.80 and
insertion-order ties. The cutoff was chosen on separate generic off-topic and
paraphrase examples before the quality runs.

Passage vectors are built lazily and cached by document ID for the life of the
store. The dense ranker uses an exact scan with no score fusion, date/status
boost, or persisted index.

## Evaluation

### Literal-first retrieval

Dense E5 replay against the fallback-only baseline (`9d1825f`), with the same
fixtures and cutoff:

| Check | Before | Literal-first |
|---|---:|---:|
| Exact sets | 5/5 | 4/5 |
| Ranked top-1 | 27/42 | 27/42 |
| Ranked hit@5 | 38/42 | 39/42 |
| Historical holdout top-1 / hit@5 | 2 / 3 | 2 / 3 |
| Second batch top-1 / hit@5 (20 single-target queries) | 15 / 19 | 15 / 19 |

`water bill` still ranks the water bill first but now also returns an
unwanted electricity statement. Conversely, `aimee smith-krag authorization`
now finds the signed release at rank 2; the literal draft stays first. The
holdout no-match result and both second-batch activity results are unchanged.

On one local 23-document run, median `mortgage balance` latency rose from
1.3 ms to 97.3 ms on an empty passage cache (7 runs, excluding helper startup),
and from 0.6 ms to 3.3 ms with a warm cache (210 runs). These timings are not
capacity estimates.

### Original fallback-only evaluation

Compared with the same router with no ranker, Dense kept **5/5 exact-set** and
raised Reed **top-1 from 1/10 to 5/10** and **hit@5 from 3/10 to 10/10**. `reed
permission to share with accountant` put the signed release first (cosine
0.877 vs 0.853 for its draft). `utility bill reed` put the stale bill first
(0.868 vs 0.863); `reed address proof` put an address-change form first even
though the form is not independent proof. `reed latest 401(k) statement` put
June first by about 0.0013 cosine; that does not establish date understanding.

The branch diagnostic measured about **177 ms** for helper startup and hash
checks and **536 ms** to encode all 23 ranked records. The cache payload was
**34.5 KiB** (one vector per record); model and tokenizer occupy **127.6 MiB**
and the separate helper environment used about **220 MiB**. Exact scan and
per-process caching are prototype choices; these are not capacity estimates.

```sh
uv run --locked pytest --no-cov
uv run --locked pytest -s --no-cov evals/ -k dense-e5
```

The quality eval deliberately exits nonzero on any exact-set or top-1 miss. See the
[fixture guide](../../evals/README.md) for the synthetic review date.
