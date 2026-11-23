# Advisor tasks for document search

These tasks are about finding records **already on file** for an existing client. The sources describe the advisor’s work; the document names below are examples of what the advisor might search for.

## Task list

**Sources:**

- **Kitces:** Teresa Riccobuono, [*Financial Advisor Checklists To Enhance The Client Meeting Prep Process*](https://www.kitces.com/blog/client-meeting-prep-checklist-for-financial-advisors/#a-thorough-client-meeting-prep-checklist). The section for each task is listed below.
- **Address verification:** The [Nevis assignment](assignment.md) gives `address proof` → `utility bill` as a search example. [Interactive Brokers’ proof-of-address FAQ](https://www.interactivebrokers.com/support/faq/content/acceptable-proof-address-id-ibllc-135560140) lists gas, electric, and water bills as acceptable examples. The custodian’s actual requirements govern; a utility bill isn’t universally required.

| # | Advisor task | Document to find | Source |
|---|---|---|---|
| 1 | Review who inherits a particular account. | Beneficiary or transfer-on-death designation for that account. | Kitces, “Fundamentals” |
| 2 | Check whether the portfolio follows the agreed investment guidelines. | Current Investment Policy Statement. | Kitces, “Asset Management” and “Prior To Appointment” |
| 3 | Check whether the firm can share client information with the client’s accountant or attorney. | Current signed authorization covering the recipient. | Kitces, “Prior To Appointment” |
| 4 | Decide whether the client needs to update their information. | Most recently completed client questionnaire. | Kitces, “Prior To Appointment” |
| 5 | Check what’s still outstanding from the last appointment. | Previous meeting notes or follow-up letter. | Kitces, “Prior To Appointment” |
| 6 | Gather the record of work done since the last meeting. | All activity notes for that client since the meeting. | Kitces, “Prior To Appointment” |
| 7 | Review the client’s retirement accounts and assets held elsewhere. | Latest relevant 401(k), 403(b), or outside account statement, if on file. | Kitces, “Prior To Appointment” |
| 8 | Review employee stock purchase plans or stock options. | Plan documents, grant notices, or vesting schedules. | Kitces, “Asset Management” and “Prior To Appointment” |
| 9 | Check whether the client can withdraw from a retirement plan while still employed. | Plan document or summary describing in-service withdrawals. | Kitces, “Asset Management” and “Prior To Appointment” |
| 10 | Check how much time remains on term life coverage. | Term life policy or policy schedule. | Kitces, “Fundamentals” |
| 11 | Review a variable universal life policy. | Latest in-force illustration or ledger, if on file. | Kitces, “Fundamentals” |
| 12 | Check whether the client can increase disability coverage. | Disability policy and its Future Purchase Option rider. | Kitces, “Fundamentals” |
| 13 | Review which services the firm promised the client. | Client service calendar or service agreement. | Kitces, “Prior To Appointment” |
| 14 | Check when insurance and employee benefits were last reviewed. | Previous insurance review or meeting notes. | Kitces, “Financial Planning” |
| 15 | While opening a new brokerage account for an existing client, find proof of their current residential address after the custodian requests it. | A recent utility bill on file showing the client’s name and current address, if acceptable to the custodian. | Nevis assignment; Interactive Brokers proof-of-address FAQ |

## First eval batch: three tasks

Use [Karen Reed’s records](../evals/cases/reed.jsonl) as the targets and Jamie Krag’s and Aimee Smith-Krag’s individual records as distractors. Every query names Reed because the API searches across clients. The first **document** in the returned list must be the expected record; client objects do not count toward document rank. The eval also checks that `karen reed` returns Karen as the first **client**. See the [fixture notes](../evals/README.md).

| Advisor task | Likely search queries | Expected document | Wrong match to seed |
|---|---|---|---|
| **15.** Find proof of Reed’s current address for a new brokerage account. | `reed address`, `reed address proof`, `utility bill reed` | `June residential electricity statement` showing Reed’s name and current address. | Reed’s electricity statement for the old address. |
| **7.** Find Reed’s latest 401(k) statement before the review meeting. | `reed 401k`, `401k statement reed`, `reed latest 401(k) statement` | Reed’s June 401(k) statement, the latest one in the fixture. | Reed’s March statement for the same account. |
| **3.** Check whether Reed gave the firm permission to share information with their accountant. | `reed authorization`, `reed permission to share with accountant`, `signed release of information reed` | Reed’s signed, current **Authorization to Release Information** covering the accountant. | An unsigned copy of the same form. |

## Krag and typo eval groups

The **Krag** group pairs all ten Reed queries with Jamie Krag queries in the same multi-client corpus and at the same July 10, 2025 review date. Only the owner phrase changes; `jamie krag` avoids relying on the shared `Krag` name. The counterparts are:

| Advisor task | Jamie queries | Expected fixture key | Near-match |
|---|---|---|---|
| Find the client | `jamie krag` | `jamie` | Aimee Smith-Krag is a separate client. |
| Find proof of current address | `jamie krag address`, `jamie krag address proof`, `utility bill jamie krag` | `power-current` | `power-old-address` is stale; Aimee’s gas bill is not in Jamie’s name. |
| Find the latest 401(k) statement | `jamie krag 401k`, `401k statement jamie krag`, `jamie krag latest 401(k) statement` | `jamie-401k-jun` | March and December statements are older. |
| Check permission to share with an accountant | `jamie krag authorization`, `jamie krag permission to share with accountant`, `signed release of information jamie krag` | `jamie-release-signed` | Jamie’s blank draft does not authorize disclosure. |

The **Aimee** group repeats the same ten queries with `aimee smith-krag` as the owner and `403(b)` / `403b` in place of `401(k)` / `401k`:

| Advisor task | Aimee queries | Expected fixture key | Near-match |
|---|---|---|---|
| Find the client | `aimee smith-krag` | `aimee` | Jamie Krag is a separate client. |
| Find proof of current address | `aimee smith-krag address`, `aimee smith-krag address proof`, `utility bill aimee smith-krag` | `gas-current` | `gas-old-address` is stale; Jamie’s bill has the wrong owner. |
| Find the latest 403(b) statement | `aimee smith-krag 403b`, `403b statement aimee smith-krag`, `aimee smith-krag latest 403(b) statement` | `aimee-403b-jun` | March is older; the hospital balance summary and former-employer 403(b) summary are not current statements. |
| Check permission to share with an accountant | `aimee smith-krag authorization`, `aimee smith-krag permission to share with accountant`, `signed release of information aimee smith-krag` | `aimee-release-signed` | The draft is unsigned; Jamie’s signed copy does not cover Aimee. |

**Krag extras** keeps other Jamie and Aimee searches separate from the matched scores:

| Query | Expected fixture key | Why the near-match does not count |
|---|---|---|
| `jamie krag current electricity bill` | `power-current` | The final bill is at Jamie’s old address; Aimee’s gas bill is not Jamie’s electricity bill. |
| `jamie krag latest 401(k) statement` | `jamie-401k-jun` | The March and December statements are older; Reed’s is not Jamie’s account. |
| `jamie krag signed release of tax records` | `jamie-release-signed` | Jamie’s blank draft is not authorization and the signed copy covers only Jamie. |
| `jamie krag employer equity vesting schedule` | `jamie-rsu-schedule` | The brokerage inventory lists shares already held, not vesting dates. |
| `aimee smith-krag june gas statement` | `gas-current` | Jamie’s electricity statement is a different record even though it shares the address. |
| `aimee smith-krag long-term disability summary` | `aimee-disability` | Jamie’s employer summary describes different coverage. |

The **Typos** group reuses clean judgments from Reed, Krag, Aimee, and Krag extras. Each variant changes one word: a repeated key (`Reeed`), transposed letters (`Karg`, `scheudle`), or a dropped letter (`authoriztion`, `disabilty`). It tests both client-only lookup and document search; a document mentioning the client cannot substitute for a missing client result. See the [expanded benchmark results and clean pairs](search/expanded-benchmark.md).
