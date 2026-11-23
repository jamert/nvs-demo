# Expanded search benchmark: Krag and typos

The same 30 documents and three fictional clients are seeded for each ranked group. **Krag** and **Aimee** repeat the ten Reed queries against the corresponding records for Jamie Krag and Aimee Smith-Krag. Only the owner and, for Aimee, the retirement plan term (403(b) instead of 401(k)) change. **Krag extras** covers additional Jamie and Aimee records without changing the matched comparison. The [fixture guide](../../evals/README.md) describes the two added Jamie-only releases; Reed queries, existing records and judgments are unchanged. The [original holdout](comparison.md) still runs separately on its original 23 documents. No ranker was changed for this benchmark.

## Results

Each ranked cell shows **top-1 / hit@5** within the requested type. Counts are out of the group size in the header. The hook scores top-1 and exact-set, not hit@5.

| Approach | Exact sets (5) | Reed (10) | Krag (10) | Aimee (10) | Krag extras (5) | Typos (7) |
|---|---:|---:|---:|---:|---:|---:|
| `postgres-substring` | 5/5 | 1 / 1 | 1 / 1 | 1 / 1 | 0 / 0 | 0 / 0 |
| `bm25` | 5/5 | 3 / 8 | 3 / 7 | 4 / 7 | 5 / 5 | 2 / 3 |
| `dense-e5` | 5/5 | 5 / 10 | 7 / 10 | 6 / 8 | 5 / 5 | 3 / 5 |
| `skg` | 5/5 | 3 / 10 | 3 / 9 | 5 / 9 | 5 / 5 | 2 / 3 |
| Shared literal (research control) | 5/5 | 1 / 3 | 2 / 2 | 2 / 2 | 2 / 2 | 0 / 0 |
| SKG without expansion (research control) | 5/5 | 3 / 9 | 4 / 8 | 5 / 8 | 5 / 5 | 2 / 3 |

The paired comparison exposes differences hidden by pooling the household cases. Dense puts the current bill first for `utility bill jamie krag`, but not for `utility bill reed`. All three rankers put Jamie’s unsigned draft first for the permission-to-share query, although they put Reed’s signed copy first for the same wording. The same rankers find Aimee’s signed copy for that phrasing, but her shorter `authorization` query returns only her draft: it contains the literal word in a denial. None puts Aimee’s latest 403(b) statement first. Dense prefers the balance summary; BM25 and SKG prefer the March statement. Higher top-1 overall does not verify authorization or recency.

## Paired typos

| Clean query | Variant | Gold key |
|---|---|---|
| `karen reed` | `karen reeed` | `karen` |
| `aimee smith-krag` | `aimee smith-karg` | `aimee` |
| `jamie krag latest 401(k) statement` | `jamie karg latest 401(k) statement` | `jamie-401k-jun` |
| `utility bill reed` | `utility bill reeed` | `karen-electric-current` |
| `reed authorization` | `reed authoriztion` | `karen-release-signed` |
| `jamie krag employer equity vesting schedule` | `jamie krag employer equity vesting scheudle` | `jamie-rsu-schedule` |
| `aimee smith-krag long-term disability summary` | `aimee smith-krag long-term disabilty summary` | `aimee-disability` |

None of the four approaches found either misspelled client record. All three ranked approaches survived `scheudle` and `disabilty` with the intact words. Dense alone found the signed release first for `reed authoriztion`. The misspelled owner in `utility bill reeed` lost owner scoping: it can return another client's bill first. That's a reason to evaluate owner resolution separately from fuzzy document matching.

## Replay

Run from the repository root with Docker and the [local Dense E5 helper](../../experiments/embeddings/README.md) set up:

```sh
uv run --locked pytest -s --no-cov evals/                    # all quality groups
uv run --locked pytest -s --no-cov evals/ -k Aimee            # Aimee only
uv run --locked python -m evals.compare > search-comparison.json
```

The pytest quality run exits nonzero if any query misses. The JSON replay records stable top-five keys and gold ranks per case and includes `typos_clean_controls`, keyed by the misspelled query. See [advisor tasks](../advisor-tasks.md#krag-and-typo-eval-groups) for the clean Jamie and Aimee relevance judgments.
