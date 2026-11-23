# Second advisor search benchmark

This replay uses the current serving code, including the beneficiary and
meeting follow-up rules, and a synthetic review date of July 10, 2025. The
pre-rule baseline is reproducible at `02a59cb`. It seeds the existing three clients and 30 documents, plus
[21 individually owned records](../../evals/cases/advisor-second-batch.jsonl):
12 targets and nine distractors. The [22 queries](../advisor-tasks.md#second-eval-batch-remaining-advisor-tasks),
gold keys, and near-miss reasons were fixed before replay. Fixture dates and
ownership labels are not submitted as document fields; dates are evaluated
from fixture metadata, and ownership is set through the existing client IDs.

## Single-target tasks

Each cell is **top-1 / hit@5**, counted within document results. Each task
has two query variants; totals count queries, not independent tasks.

| Advisor task | SQLite substring | Postgres substring | BM25 | Dense E5 | SKG |
|---|---:|---:|---:|---:|---:|
| 1. Brokerage beneficiary | 1 / 1 | 1 / 1 | 2 / 2 | 2 / 2 | 2 / 2 |
| 2. Investment policy | 0 / 0 | 0 / 0 | 1 / 2 | 1 / 2 | 1 / 2 |
| 4. Completed questionnaire | 0 / 0 | 0 / 0 | 0 / 2 | 0 / 1 | 2 / 2 |
| 5. Open follow-ups | 2 / 2 | 2 / 2 | 2 / 2 | 2 / 2 | 2 / 2 |
| 9. In-service withdrawals | 0 / 0 | 0 / 0 | 1 / 2 | 1 / 2 | 2 / 2 |
| 10. Term life schedule | 0 / 0 | 0 / 0 | 2 / 2 | 2 / 2 | 2 / 2 |
| 11. In-force VUL illustration | 0 / 0 | 0 / 0 | 0 / 2 | 2 / 2 | 1 / 2 |
| 12. Disability purchase option | 0 / 0 | 0 / 0 | 2 / 2 | 2 / 2 | 2 / 2 |
| 13. Agreed services | 0 / 0 | 0 / 0 | 1 / 2 | 1 / 2 | 2 / 2 |
| 14. Completed benefits review | 0 / 0 | 0 / 0 | 2 / 2 | 2 / 2 | 2 / 2 |
| **Total (20 queries)** | **3 / 3** | **3 / 3** | **13 / 20** | **15 / 19** | **18 / 20** |
| *Pre-rule total* | *0 / 0* | *0 / 0* | *11 / 20* | *13 / 18* | *16 / 19* |

All five modes now put the account 0762 designation first for `reed who
inherits account ending 0762` (previously eighth with SKG), and the follow-up
letter first for `jamie krag what was left to do after the last meeting`
(previously absent with Dense E5). The substring modes also recover the letter
for `jamie krag last appointment follow-ups`. No other query results changed.

BM25 still puts the sales illustration first for both VUL queries, while
Dense E5 puts the current ledger first on both. Dense puts the newer blank
questionnaire first for both wordings and the completed form 11th for `reed
latest completed client questionnaire`. All three ranked modes still prefer
the superseded IPS for `reed agreed portfolio allocation limits`.

## Task 6: activity notes

The eligible notes are `karen-activity-jun13` and `karen-activity-jul10`, after
June 10 through July 10 inclusive. A complete hit requires **both** in the
top five. False hits are reported separately, so a complete hit can still
include an ineligible note. The June 10 meeting minutes are not an activity
note and do not count as a date or owner violation.

| Mode | `reed activity notes since june 10 2025` | `reed work completed after the june 10 meeting` | Complete queries | Queries with out-of-window notes in top 5 | Queries with wrong-client notes in top 5 |
|---|---:|---:|---:|---:|---:|
| SQLite substring | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Postgres substring | 0/2 | 0/2 | 0/2 | 0/2 | 0/2 |
| BM25 | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 |
| Dense E5 | 1/2 | 0/2 | 0/2 | 2/2 | 0/2 |
| SKG | 2/2 | 0/2 | 1/2 | 2/2 | 0/2 |

Every ranked mode returned the June 6 note in the top five for both queries.
For the second query, SKG put the correct notes sixth and seventh, and Dense
returned only the June 6 note and the June 10 meeting minutes. No mode
returned Jamie's activity note in either top five.

## Replay

Run from the repository root with Docker and the
[local Dense E5 helper](../../experiments/embeddings/README.md):

```sh
uv run --locked python -m evals.advisor_second_batch > advisor-second-batch.json
```

For each query, `ordered_keys` contains all returned document keys in serving
order, `top5` is its first five, and `gold_ranks` records each expected rank
(one-based; `null` means the document was not returned). Client results do not
consume document ranks. `by_task` contains single-target case rows and counts;
`activity` contains task 6's two rows with their note counts and flag lists.

Relevance misses are benchmark results, not failures of this command or of
ordinary `pytest` and pre-commit. The normal tests validate fixture isolation
and scoring rules without holding serving modes to these rankings. The old
benchmark and historical holdout do not include this batch. The commit
trailer adds the 22 second-batch queries to the original 47. A single-target
query counts on a top-1 hit; an activity query counts when both required notes
are in the top five. False-hit flags remain available in the replay. A paired
`evals.compare` replay against `57d0e83` matched all legacy non-timing output
across the five serving modes and both research controls.
