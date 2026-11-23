# Expanded search benchmark: Krag and typos

The tables below record the baseline at `8911f9c`, before the shared
[proof-of-address rule](../../README.md#proof-of-address-search). Replaying on
a revision with the rule applies it to all replay modes, including the two
research controls. To measure the rule's effect, run `evals.compare` on both
revisions and compare case rows by query and stable document key.

The same 30 documents and three fictional clients are seeded for each ranked group. **Krag** and **Aimee** repeat the ten Reed queries against the corresponding records for Jamie Krag and Aimee Smith-Krag. Only the owner and, for Aimee, the retirement plan term (403(b) instead of 401(k)) change. **Krag extras** covers additional Jamie and Aimee records without changing the matched comparison. The [fixture guide](../../evals/README.md) describes the additions to the Krag corpus; the original Reed queries and judgments are unchanged. The [original holdout](comparison.md) still runs separately on its original 23 documents. No ranker was changed for this benchmark.

## Results by task

The table uses the 30 matched clean queries across Karen, Jamie and Aimee. Each cell is **top-1 / hit@5** within the requested result type; the number of queries is in the first column. These are counts of query variants, not independent advisor tasks. Extras, typos, and exact-set regressions are not pooled into this table.

| Advisor task (queries) | Postgres substring | BM25 | Dense E5 | SKG | Shared literal | SKG off |
|---|---:|---:|---:|---:|---:|---:|
| Find the client (3) | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 |
| Find current address proof (9) | 0 / 0 | 2 / 6 | 5 / 9 | 3 / 9 | 2 / 3 | 4 / 6 |
| Find the latest plan statement (9) | 0 / 0 | 0 / 6 | 4 / 8 | 0 / 9 | 0 / 0 | 0 / 9 |
| Find signed authorization (9) | 0 / 0 | 5 / 7 | 6 / 8 | 5 / 7 | 0 / 1 | 5 / 7 |

**Latest statement is the clearest ranking bottleneck.** SKG finds all nine targets in the top five but never ranks the latest statement first; its expansion-off control already does the same. Dense gets four first-place results across Karen and Jamie, but none for Aimee. SKG expansion helps address-proof recall (6 → 9) but loses one first-place hit (4 → 3).

The clean client lookup score hides a typo failure: all four approaches missed both misspelled names. The narrower extras for equity vesting and disability coverage have one clean and one typo query each. All three ranked approaches put the right record first on both versions of those tasks.

### Results by eval group

Each ranked cell is again **top-1 / hit@5**. The hook scores top-1 and exact-set, not hit@5.

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

## Shared proof-of-address rule: paired replay

| Search mode | Address proof top-1 / hit@5 before | After |
|---|---:|---:|
| SQLite substring | 0 / 0 | 2 / 2 |
| Postgres substring | 0 / 0 | 2 / 2 |
| BM25 | 2 / 6 | 4 / 6 |
| Dense E5 | 5 / 9 | 6 / 9 |
| SKG | 3 / 9 | 3 / 9 |

Of the nine address-proof queries, only the three containing `address proof`
changed in any mode. All five modes kept 5/5 exact sets. Client lookup, latest
statement, signed authorization, extras, typos, and the historical holdout
were unchanged, including its missing-document case. In particular, the rule
does not trigger for `evidence of where he lives now`.

For `aimee smith-krag address proof`, the stale record says `gas bill`, while
the current `gas service statement` lacks a configured phrase. Dense and SKG
therefore dropped the current bill from first to second. This rule retrieves
likely document types; it does not establish recency or verify evidence.

## Replay

Run from the repository root with Docker and the [local Dense E5 helper](../../experiments/embeddings/README.md) set up:

```sh
uv run --locked pytest -s --no-cov evals/                    # all quality groups
uv run --locked pytest -s --no-cov evals/ -k Aimee            # Aimee only
uv run --locked python -m evals.compare > search-comparison.json
```

The pytest quality run exits nonzero if any query misses. The JSON replay records stable top-five keys and gold ranks per case. Its `by_task` view reports `total`, `top1`, and `hit5` for the matched queries, with a `by_client` breakdown and separate `extras` and `typos` counts when applicable. Existing group fields are unchanged. `typos_clean_controls` is keyed by the misspelled query. See [advisor tasks](../advisor-tasks.md#krag-and-typo-eval-groups) for the clean Jamie and Aimee relevance judgments.
