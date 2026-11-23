# Search approaches: integrated comparison

**Recommendation:** Keep substring as the default and try BM25 first as an opt-in candidate fallback. BM25 tied dense on the holdout positives, kept the no-match empty, and needs no extra runtime. Dense is the strongest recall challenger on Reed, but neither it nor BM25 establishes that the first result is usable evidence. SKG added one Reed recall hit over its own lexical control and no first-place wins. All three are available through the same [server selector](../../README.md#api); the research controls are not server options.

## Reproduced results

The [frozen official fixtures](../../evals/README.md) use a synthetic as-of date of **2025-07-10**. All **24 default tests** passed, including exact-match HTTP acceptance for SQLite and each Postgres approach. The official quality run passed all four exact-set suites and failed all four Reed suites (each pytest item requires 10/10 top-1); the commit hook records the partial scores rather than blocking commits for relevance misses.

| Approach | Exact-set /5 | Reed top-1 /10 | Reed hit@5 /10 | Holdout top-1 / hit@5 (of 4) | Holdout no-match | Warm median / p95 (ms) | Index build and footprint |
|---|---:|---:|---:|---:|---|---:|---|
| `postgres-substring` | 5 | 1 | 1 | 0 / 0 | Empty | 0.54 / 0.75 | No added index |
| Shared literal (BM25 and dense control) | 5 | 1 | 3 | 0 / 0 | Empty | 1.01 / 1.51 | No added index |
| [BM25](bm25.md) | 5 | 3 | 8 | 2 / 3 | Empty | 1.71 / 2.48 | 0.325 ms build; ~72 KiB transient |
| [Dense E5](dense-e5.md) | 5 | 5 | 10 | 2 / 3 | Four wrong hits | 3.08 / 3.98 | 536 ms for 23 docs; 34.5 KiB vectors, 127.6 MiB model/tokenizer, ~220 MiB helper env |
| SKG off (same lexical ranker, no expansion) | 5 | 3 | 9 | 1 / 3 | Empty | 1.91 / 2.78 | 0.166 ms build; ~95 KiB transient |
| [SKG](skg.md) | 5 | 3 | 10 | 1 / 3 | Empty | 1.61 / 1.90 | 0.166 ms build; ~95 KiB transient, before edge traversal |

Warm measurements are 100 sequential `Search.search` calls per row (ten repeats of the ten Reed queries after one sweep). They include DB reads and ranking, not HTTP, fixture seeding or serialization. Runs used macOS arm64, Python 3.15.2 and local Docker with `postgres:18`. Build and allocation figures are earlier lane diagnostics excluding DB reads; lexical/SKG use the 11-document Reed slice, and dense uses the full 23-document corpus plus a separate ~177 ms helper startup. These timings are noisy even across repeated runs: they do not show that expansion is faster than its control, or establish production scaling. All three ranked approaches fetch whole tables; only dense caches its index.

The earlier [CFPB glossary](https://www.consumerfinance.gov/consumer-tools/educator-tools/youth-financial-education/glossary/) enrichment was not integrated: relative to fixture-only SKG it did not improve exact-set (5/5), Reed (3/10 top-1, 10/10 hit@5), or holdout positives (1/4 top-1, 3/4 hit@5), and returned four wrong hits on the holdout negative. The hypothesis that the external corpus would help was not supported here.

## What drove the scores

Reed ranks are within the requested result type. A dash means the gold record was absent. Replay prints the returned top five stable keys, not just gold ranks.

| Reed query | Substring | Shared literal | BM25 | Dense | SKG off | SKG |
|---|---:|---:|---:|---:|---:|---:|
| `karen reed` | 1 | 1 | 1 | 1 | 1 | 1 |
| `reed address` | — | 2 | 2 | 2 | 2 | 2 |
| `reed address proof` | — | — | 2 | 3 | 3 | 3 |
| `utility bill reed` | — | — | — | 2 | — | 2 |
| `reed 401k` | — | — | — | 2 | 3 | 2 |
| `401k statement reed` | — | — | 5 | 1 | 2 | 2 |
| `reed latest 401(k) statement` | — | — | 2 | 1 | 2 | 2 |
| `reed authorization` | — | 2 | 2 | 2 | 2 | 2 |
| `reed permission to share with accountant` | — | — | 1 | 1 | 1 | 1 |
| `signed release of information reed` | — | — | 1 | 1 | 1 | 1 |

- **Literal routing accounts for part of the recall gain.** `reed address` and `reed authorization` return the intake note first without invoking any ranked approach. Exact name and email-style queries also bypass ranking but preserve literal document hits.
- **Recall is not evidence selection.** `utility bill reed` finds only the obsolete bill with BM25. Dense and SKG recover the current bill at rank 2, but still lead with the obsolete bill. `reed address proof` leads with the address-change form, which is not independent proof.
- **Dense's two additional top-1 hits over BM25 are both Reed retirement variants.** The June statement wins by a small similarity margin; the same model prefers a stale March statement for Jamie. BM25 and the SKG variants can tie the versions and prefer insertion order. No approach enforces a date or status constraint.

The [holdout cases](../../evals/cases/search-holdout-v1.json) were authored and hashed before implementation, not used in tuning. Their documents are from the official ranked corpus (new wording/targets, not a new corpus). Baseline and shared literal returned nothing for all five cases. For positives, use the document rank; for the negative, require the entire mixed response to be empty.

| Holdout intent | Gold | BM25 | Dense | SKG off | SKG |
|---|---|---:|---:|---:|---:|
| Jamie: proof of where he lives now | `power-current` | — | — | — | — |
| Jamie: newest workplace retirement balance | `jamie-401k-jun` | 3 | 2 | 3 | 3 |
| Jamie: when company shares become his | `jamie-rsu-schedule` | 1 | 1 | 2 | 2 |
| Aimee: long-term income protection if unable to work | `aimee-disability` | 1 | 1 | 1 | 1 |
| Aimee: dental enrollment confirmation | `[]` | Empty | Four wrong hits | Empty | Empty |

The dense false positives were the disability summary, two retirement records, and a gas bill. SKG and its control preferred already-held brokerage shares to the vesting schedule. No approach returned the current Jamie bill. The nine Reed document queries cover just three tasks, and the holdout has one negative: neither is enough to establish a general winner.

## Reproduce and extend

From the repository root, with Docker running and the [pinned local helper](../../experiments/embeddings/README.md) installed:

```sh
uv sync --locked
sh experiments/embeddings/setup.sh
uv run --locked pytest --no-cov
uv run --locked pytest -s --no-cov evals/  # nonzero when any ranked case misses
uv run --locked python -m evals.compare > search-comparison.json
```

The [comparison runner](../../evals/compare.py) emits per-query stable keys, ranks, counts, and latency for all four Postgres approaches plus the two research controls. It uses the same seeded inputs and order as the official suite. `Search-Eval-*` trailers record the four official scores in Git history. The method reports describe ranking parameters, footprint, and explanatory diagnostics.

**Next test:** Freeze new households and records (not just rewrites), randomize ingestion order, and include current/old addresses, newer/older statements, signed/draft releases, and missing artifacts. Compare BM25, normalized lexical retrieval, and dense candidates behind the same separately ablated content-derived evidence check. Prefer dense only if it turns extra recall into more usable first results without increasing critical lookup or no-match failures. None of these options implement authorization; use synthetic data only.
