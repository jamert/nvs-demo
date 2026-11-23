# Synthetic advisor documents

[`krag.jsonl`](cases/krag.jsonl) is a set of text documents based on the fictional Jamie Krag and Aimee Smith-Krag household in the [FPA 2025 Financial Planning Challenge case study](https://www.financialplanningassociation.org/sites/default/files/2025-02/FPC25%20Case%20Study.pdf). The case supplies the household situation, account values, investments, equity awards, and benefit details. The document layouts, addresses, provider details, release forms and quarter-end transactions are invented; `adapted` means the document uses at least some case facts, not that every field comes from the source. Nothing in this fixture is valid for verification or filing.

[`reed.jsonl`](cases/reed.jsonl) is a separate, single-client corpus based on [InvestWise Financial’s *Navigating Retirement as a Single Professional*](https://investwisefinancial.com/case-study/case-study-2-navigating-retirement-as-a-single-professional). The source explicitly says the case is hypothetical. It describes Karen, a 61-year-old retiree, with $2.4 million across a 401(k), an IRA, and a brokerage account. The surname Reed, account-level balances, dates, addresses, and all underlying statements and forms are invented. There are no joint documents.

From the repo root:

```sh
uv run python -m evals.read_documents --case krag --list   # keys and titles
uv run python -m evals.read_documents --case reed          # all Karen Reed documents
uv run python -m evals.read_documents --case reed karen-electric-current karen-electric-old
```

Each JSONL line has a stable `key`, an individual or `household` as `owner`, the date shown in the record (for statements, the period-end date except for utility bills, which use the bill issue date), its `basis` (`adapted` or `invented`), and the `title` and `content` accepted by the Search API. The reader defaults to `krag` if no case is specified. To load a fixture in code, use `load_documents(CORPORA["reed"])` or `load_documents(CORPORA["krag"])` and call `to_document_input()` on each record to strip fixture metadata for insertion.

**Joint documents are not supported by the current API.** Each `Document` has exactly one `client_id`. `owner: "household"` marks shared material in the source-derived fixture; it is not an API ownership field. When seeding Jamie and Aimee as separate `Client` records, attach individually owned documents to the corresponding client and leave shared rows out of that run.

For the [first eval batch](../doc/advisor-tasks.md#first-eval-batch-three-tasks), the ranked eval uses a synthetic review date of July 10, 2025. It seeds Karen, Jamie, and Aimee as three separate `Client` objects, using the Krag individuals’ documents as distractors and skipping shared rows. The expected documents are `karen-electric-current`, `karen-401k-jun`, and `karen-release-signed`; the main near-matches are `karen-electric-old`, `karen-401k-mar`, and `karen-release-draft`. The client address update is not independent proof of address; the IRA statement and account inventory are not the 401(k) statement.

For comparison with the Krag corpus, use the same synthetic review date. Use `power-current` for the task of finding a current utility bill for **Jamie** and `power-old-address` as the wrong-address match. `gas-current` is in **Aimee’s** name at the same address; count it only if the case accepts either household member. Use `jamie-401k-jun` versus `jamie-401k-mar` for the retirement task. The existing `signed-release` and `draft-release` rows are joint examples. To run the authorization task with separate client records, author a Jamie-only signed release and unsigned draft covering only Jamie’s records. The original substring regression suite still uses its own tiny fixture; the ranked suite is the one that loads these corpora.

The [integrated comparison](../doc/search/comparison.md) explains the additional [holdout checks](cases/search-holdout-v1.json) and how to replay them. They are separate from the official quality cases and commit scores.
