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
literal lookup and owner scoping. The dense fallback encodes the residual query
with `query:` and each title/body chunk with `passage:`. Windows are capped at
256 WordPiece tokens including special tokens; the title prefix uses at most 32
and body windows overlap by 32. The model's unpadded last hidden states are
mean-pooled and L2-normalized to 384 dimensions. Rank by maximum chunk cosine,
with a fixed cutoff of 0.80 and insertion-order ties. The cutoff was chosen on
separate generic off-topic and paraphrase examples before the quality runs.

Passage vectors are built lazily and cached by document ID for the life of the
store. Search uses an exact scan. There is no fusion, reranking, date/status
boost, or persisted index.

## Evaluation

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

The ranked eval deliberately exits nonzero on a top-1 miss. See the
[fixture guide](../../evals/README.md) for the synthetic review date.
