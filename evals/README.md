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

For the [original Reed group](../doc/advisor-tasks.md#first-eval-batch-three-tasks), the ranked eval uses a synthetic review date of July 10, 2025. It seeds Karen, Jamie, and Aimee as three separate `Client` objects, skipping shared rows. The Reed queries treat the Krag records as distractors. The expected documents are `karen-electric-current`, `karen-401k-jun`, and `karen-release-signed`; the main near-matches are `karen-electric-old`, `karen-401k-mar`, and `karen-release-draft`. The client address update is not independent proof of address; the IRA statement and account inventory are not the 401(k) statement.

The [Krag, Aimee, Krag extras, and Typos groups](../doc/advisor-tasks.md#krag-and-typo-eval-groups) use the same review date. All ranked groups share 30 documents: the original 23 individual records plus two Jamie-only releases and five Aimee-only records in [the Krag fixture](cases/krag.jsonl). Aimee’s additions are March and June 403(b) statements, an old-address gas bill, and signed/draft releases. The joint `signed-release` and `draft-release` remain excluded. Krag and Aimee repeat the ten Reed queries with the owner changed to the relevant client and the plan term adapted to 403(b) for Aimee. Krag extras covers other Jamie and Aimee searches. Typos changes one word per query and reuses its clean counterpart’s target and result type. The exact-set suite still loads its separate tiny fixture.

The [expanded benchmark](../doc/search/expanded-benchmark.md) documents the current metrics and replay. The [historical holdout](cases/search-holdout-v1.json) is still replayed on its original 23 documents and is separate from the official quality cases and commit scores.

Run `uv run --locked python -m evals.compare` for stable-key JSON from all five approaches and both research controls. The `explicit_recency` section reports the three matched explicit-cue plan-statement cases separately from the full task scores. It captures actual candidate order before recency sorting (`rerank_off`) and compares it with final order (`rerank_on`) from the same search. `gold_present` measures candidate retrieval independently of sorting. Both views ingest fixture bodies through the normal service, without the fixture dates.
