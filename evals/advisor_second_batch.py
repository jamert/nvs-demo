"""Replay the second advisor batch on an isolated corpus; emit stable-key JSON."""

import json
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from nevis_search.config import POSTGRES_APPROACHES, SearchApproach
from nevis_search.search import Client, Document, Search

from .compare import Counts, open_search
from .read_documents import CASES_DIR, FixtureDocument, load_documents
from .search_quality import seed_ranked

SECOND_BATCH_CORPUS = CASES_DIR / "advisor-second-batch.jsonl"
MEETING_DATE = date(2025, 6, 10)
AS_OF_DATE = date(2025, 7, 10)


@dataclass(frozen=True)
class AdvisorTask:
    number: int
    owner: str
    queries: tuple[str, str]
    expected_keys: tuple[str, ...]
    near_misses: dict[str, str]


# Judge by the business record each query needs, not by search results.
SINGLE_TARGET_TASKS = (
    AdvisorTask(
        1,
        "karen",
        ("reed brokerage beneficiary", "reed who inherits account ending 0762"),
        ("karen-brokerage-tod",),
        {
            "karen-brokerage-jun": "Identifies account 0762 but not its beneficiary.",
            "karen-intake": "Discusses legacy planning without a filed designation.",
        },
    ),
    AdvisorTask(
        2,
        "karen",
        ("reed investment policy statement", "reed agreed portfolio allocation limits"),
        ("karen-ips-current",),
        {
            "karen-ips-superseded": "Earlier policy with different limits; replaced in June.",
            "karen-brokerage-jun": "Reports holdings, not agreed guidelines.",
        },
    ),
    AdvisorTask(
        4,
        "karen",
        ("reed latest completed client questionnaire", "reed last financial fact find"),
        ("karen-questionnaire-completed",),
        {
            "karen-questionnaire-blank": "Newer, but neither returned nor signed.",
            "karen-intake": "Advisor intake note, not a completed questionnaire.",
            "karen-address-update": "Records only one contact change.",
        },
    ),
    AdvisorTask(
        5,
        "jamie",
        (
            "jamie krag last appointment follow-ups",
            "jamie krag what was left to do after the last meeting",
        ),
        ("jamie-follow-up-letter",),
        {
            "jamie-activity-jun20": "Completed earlier work, not open items from June 26."
        },
    ),
    AdvisorTask(
        9,
        "jamie",
        (
            "jamie krag 401k in-service withdrawal rules",
            "jamie krag can i take money from my 401k while still working",
        ),
        ("jamie-401k-plan-summary",),
        {
            "jamie-401k-jun": "Balance statement, not plan rules.",
            "karen-former-401k-plan-summary": "Governs Karen's former employer plan, not Jamie's.",
        },
    ),
    AdvisorTask(
        10,
        "aimee",
        (
            "aimee smith-krag term life policy schedule",
            "aimee smith-krag when does my level term end",
        ),
        ("aimee-term-life-schedule",),
        {"aimee-disability": "End date applies to a different benefit."},
    ),
    AdvisorTask(
        11,
        "karen",
        (
            "reed latest in-force VUL illustration",
            "reed updated variable universal life policy projections",
        ),
        ("karen-vul-current",),
        {
            "karen-vul-prior": "In-force ledger from the prior year; superseded.",
            "karen-vul-sales": "Pre-issue projections, not actual in-force policy values.",
        },
    ),
    AdvisorTask(
        12,
        "aimee",
        (
            "aimee smith-krag disability future purchase option rider",
            "aimee smith-krag increase disability coverage without new medical underwriting",
        ),
        ("aimee-disability-fpo",),
        {"aimee-disability": "Existing group benefit; no purchase option documented."},
    ),
    AdvisorTask(
        13,
        "karen",
        (
            "reed client service agreement",
            "reed what services are included with my advisor",
        ),
        ("karen-service-agreement",),
        {
            "karen-service-proposal": "Unsigned package with different deliverables.",
            "karen-intake": "Meeting priorities are not contractual deliverables.",
        },
    ),
    AdvisorTask(
        14,
        "jamie",
        (
            "jamie krag last insurance and benefits review",
            "jamie krag when did we last review workplace benefits",
        ),
        ("jamie-benefits-review",),
        {"jamie-disability": "Describes coverage, not a completed review."},
    ),
)
ACTIVITY_TASK = AdvisorTask(
    6,
    "karen",
    (
        "reed activity notes since june 10 2025",
        "reed work completed after the june 10 meeting",
    ),
    ("karen-activity-jun13", "karen-activity-jul10"),
    {
        "karen-meeting-jun10": "Window anchor; minutes, not a later work entry.",
        "karen-activity-jun06": "Activity note, but before the meeting.",
        "jamie-activity-jun20": "In-window activity note, but for the wrong client.",
        "karen-intake": "Planning intake, not a service log entry.",
        "karen-address-update": "Contact change form, not a service log entry.",
    },
)
# Explicit judgments on which records are activity notes; dates alone do not suffice.
ACTIVITY_NOTE_KEYS = frozenset(
    (*ACTIVITY_TASK.expected_keys, "karen-activity-jun06", "jamie-activity-jun20")
)


class DocumentRanking(TypedDict):
    query: str
    ordered_keys: list[str]
    top5: list[str]
    gold_ranks: dict[str, int | None]


class SingleTargetResult(DocumentRanking):
    top1: bool
    hit5: bool


class ActivityResult(DocumentRanking):
    expected_in_top5: int
    complete_hit5: bool
    out_of_window_top5: list[str]
    wrong_client_top5: list[str]


class SingleTargetTaskResult(Counts):
    cases: list[SingleTargetResult]


class BatchResult(TypedDict):
    documents: int
    single_target: Counts
    by_task: dict[int, SingleTargetTaskResult]
    activity: list[ActivityResult]


def document_ranking(
    query: str, ordered_keys: list[str], expected_keys: tuple[str, ...]
) -> DocumentRanking:
    ranks: dict[str, int] = {}
    for rank, key in enumerate(ordered_keys, 1):
        ranks.setdefault(key, rank)
    return DocumentRanking(
        query=query,
        ordered_keys=ordered_keys,
        top5=ordered_keys[:5],
        gold_ranks={key: ranks.get(key) for key in expected_keys},
    )


def score_activity(
    query: str, ordered_keys: list[str], fixtures: dict[str, FixtureDocument]
) -> ActivityResult:
    ranking = document_ranking(query, ordered_keys, ACTIVITY_TASK.expected_keys)
    gold_count = sum(
        rank is not None and rank <= 5 for rank in ranking["gold_ranks"].values()
    )
    return ActivityResult(
        **ranking,
        expected_in_top5=gold_count,
        complete_hit5=gold_count == len(ACTIVITY_TASK.expected_keys),
        out_of_window_top5=[
            key
            for key in ranking["top5"]
            if key in ACTIVITY_NOTE_KEYS
            and not MEETING_DATE < fixtures[key].date <= AS_OF_DATE
        ],
        wrong_client_top5=[
            key
            for key in ranking["top5"]
            if key in ACTIVITY_NOTE_KEYS and fixtures[key].owner != ACTIVITY_TASK.owner
        ],
    )


def seed_second_batch(
    search: Search, fixtures: dict[str, FixtureDocument]
) -> dict[str, Client | Document]:
    records = seed_ranked(search)
    for key, fixture in fixtures.items():
        if key in records:
            raise ValueError(f"Second batch duplicates seeded key: {key}")
        client = records.get(fixture.owner)
        if not isinstance(client, Client):
            raise TypeError(f"Second batch requires an individual owner: {key}")
        records[key] = search.add_document(client.id, fixture.to_document_input())
    return records


def count_single_targets(rows: list[SingleTargetResult]) -> Counts:
    return Counts(
        total=len(rows),
        top1=sum(row["top1"] for row in rows),
        hit5=sum(row["hit5"] for row in rows),
    )


def run_second_batch(search: Search) -> BatchResult:
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    records = seed_second_batch(search, fixtures)
    keys_by_id = {
        doc.id: key for key, doc in records.items() if isinstance(doc, Document)
    }

    def ordered_document_keys(query: str) -> list[str]:
        return [
            keys_by_id[row.id]
            for row in search.search(query)
            if isinstance(row, Document)
        ]

    cases: dict[int, list[SingleTargetResult]] = {}
    for task in SINGLE_TARGET_TASKS:
        (expected,) = task.expected_keys
        rows: list[SingleTargetResult] = []
        for query in task.queries:
            keys = ordered_document_keys(query)
            rows.append(
                SingleTargetResult(
                    **document_ranking(query, keys, task.expected_keys),
                    top1=keys[:1] == [expected],
                    hit5=expected in keys[:5],
                )
            )
        cases[task.number] = rows
    return {
        "documents": len(keys_by_id),
        "single_target": count_single_targets(
            [row for rows in cases.values() for row in rows]
        ),
        "by_task": {
            number: {**count_single_targets(rows), "cases": rows}
            for number, rows in cases.items()
        },
        "activity": [
            score_activity(query, ordered_document_keys(query), fixtures)
            for query in ACTIVITY_TASK.queries
        ],
    }


def replay(mode: SearchApproach) -> dict[str, object]:
    with open_search(mode) as search:
        return {"approach": mode, **run_second_batch(search)}


def main() -> None:
    modes: tuple[SearchApproach, ...] = ("sqlite-substring", *POSTGRES_APPROACHES)
    print(json.dumps([replay(mode) for mode in modes], indent=2))


if __name__ == "__main__":
    main()
