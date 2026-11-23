# Corpus-derived semantic knowledge graph (SKG)

Select `NEVIS_SEARCH=skg` and set `NEVIS_POSTGRES_DSN`; see the [API setup](../../README.md#api).
There is no model, graph database, extra package, or external corpus required.
This approach is inspired by Grainger et al., [*The Semantic Knowledge Graph*](https://arxiv.org/abs/1609.00464),
§§ III.B–E. It is a one-hop, document-level implementation, not an ontology or
a hand-authored synonym map.

## Mechanism

After [common literal/owner routing](../../src/nevis_search/search/query_routing.py),
[the ranker](../../src/nevis_search/search/skg.py) builds term-to-document
postings and document-to-term sets from the searchable text. It casefolds
Unicode alphanumerics, normalizes forms such as `401(k)` to `401k`, and drops
common stopwords, single characters and pure numbers. Query terms jointly seed
the foreground when they share support; otherwise each known term seeds it.
The ranker adds up to eight positively associated terms supported by the local
corpus. For foreground size `n`, co-occurrence count `y`, and background
frequency `p`, the score is `0.5 × tanh(z/2) × y/(y+2)`, with
`z = (y−np)/sqrt(np(1−p))`. The ranker combines weighted expansions and original
terms with a title-weighted binary-presence IDF score. Ties follow insertion
order. It does not compare evidence dates or verification status.

## Evaluation

With expansion off, the same lexical scorer kept **5/5 exact-set**, **3/10
Reed top-1**, and **9/10 hit@5**. Expansion kept the first two scores and raised
hit@5 to **10/10**. For `utility bill reed`, `bill` had no literal match with
`utility` and the latter was absent as a token, but the obsolete bill supported
`bill → electricity/electric/charges` (weight 0.131 each). The current bill
went from absent to rank 2; the obsolete bill still ranked first. For `reed
401k`, `participant` and `workplace` promoted both statements above the
inventory, but March and June still tied and March was inserted first. The
same lexical scorer with expansion disabled is the valid ablation; a direct
comparison with BM25 also changes tokenization and weighting.

The original branch also tried the [CFPB financial terms glossary](https://www.consumerfinance.gov/consumer-tools/educator-tools/youth-financial-education/glossary/)
(236 public-domain glossary entries; no client documents sent out). It gave no
further judged gain and added false positives. External enrichment is not a
serving option. The fixture-only 11-document Reed slice took about **0.166 ms**
to build postings and **95 KiB** of transient Python allocations, before edge
traversal. The graph is in memory and rebuilt per ranked call; this is not a
scaling estimate.

```sh
uv run --locked pytest --no-cov
uv run --locked pytest -s --no-cov evals/ -k skg
```

A ranked miss produces a nonzero eval exit. See the [fixture guide](../../evals/README.md)
for the synthetic review date.
