from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TypedDict

from nevis_search.config import Postgres, PostgresApproach
from nevis_search.search import (
    Client,
    ClientInput,
    Document,
    DocumentInput,
    Search,
    search_factory,
)
from tests.harness.environment import postgres_container

from .read_documents import CORPORA, load_documents


@dataclass(frozen=True)
class ExactCase:
    query: str
    expected_keys: tuple[str, ...]


CORPUS = {
    "Electricity statement": "The electricity account shows usage for the service address.",
    "Water bill": "The current balance is for the service address.",
    "Investment report": "The portfolio gained value in the last quarter.",
}

EXACT_GROUP = "Exact-set"
EXACT_CASES = (
    ExactCase("water bill", ("Water bill",)),
    ExactCase("portfolio gained", ("Investment report",)),
    ExactCase("  ELECTRICITY ACCOUNT  ", ("Electricity statement",)),
    ExactCase("service address", ("Electricity statement", "Water bill")),
    ExactCase("passport", ()),
)


@dataclass(frozen=True)
class EvalResult:
    total: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> int:
        return self.total - len(self.failures)

    @property
    def summary(self) -> str:
        return f"{self.passed}/{self.total} cases passed"


def seed_substrings(search: Search) -> dict[str, Client | Document]:
    client = search.create_client(
        ClientInput(first_name="Test", last_name="Client", email="test@example.com")
    )
    return {
        "client:test": client,
        **{
            title: search.add_document(
                client.id, DocumentInput(title=title, content=content)
            )
            for title, content in CORPUS.items()
        },
    }


@dataclass(frozen=True)
class RankedCase:
    query: str
    expected_key: str
    result_type: type[Client | Document] = Document
    task: str | None = None
    expected_recency_active: bool | None = None  # None excludes non-diagnostic cases.


# Judged from the advisor's task, not the baseline's output. See doc/advisor-tasks.md.
REED_CASES = (
    RankedCase("karen reed", "karen", Client, task="client_lookup"),
    RankedCase("reed address", "karen-electric-current", task="current_address"),
    RankedCase("reed address proof", "karen-electric-current", task="current_address"),
    RankedCase("utility bill reed", "karen-electric-current", task="current_address"),
    RankedCase("reed 401k", "karen-401k-jun", task="latest_plan_statement"),
    RankedCase("401k statement reed", "karen-401k-jun", task="latest_plan_statement"),
    RankedCase(
        "reed latest 401(k) statement",
        "karen-401k-jun",
        task="latest_plan_statement",
        expected_recency_active=True,
    ),
    RankedCase(
        "reed authorization", "karen-release-signed", task="signed_authorization"
    ),
    RankedCase(
        "reed permission to share with accountant",
        "karen-release-signed",
        task="signed_authorization",
    ),
    RankedCase(
        "signed release of information reed",
        "karen-release-signed",
        task="signed_authorization",
    ),
)


def match_reed_cases(
    name: str, counterparts: dict[str, str], *, plan: str = "401(k)"
) -> tuple[RankedCase, ...]:
    plain_plan = plan.replace("(", "").replace(")", "")
    return tuple(
        replace(
            case,
            query=case.query.replace(
                "karen reed" if case.result_type is Client else "reed", name
            )
            .replace("401(k)", plan)
            .replace("401k", plain_plan),
            expected_key=counterparts[case.expected_key],
        )
        for case in REED_CASES
    )


# Use full names rather than relying on the shared Krag part of both names.
KRAG_CASES = match_reed_cases(
    "jamie krag",
    {
        "karen": "jamie",
        "karen-electric-current": "power-current",
        "karen-401k-jun": "jamie-401k-jun",
        "karen-release-signed": "jamie-release-signed",
    },
)
AIMEE_CASES = match_reed_cases(
    "aimee smith-krag",
    {
        "karen": "aimee",
        "karen-electric-current": "gas-current",
        "karen-401k-jun": "aimee-403b-jun",
        "karen-release-signed": "aimee-release-signed",
    },
    plan="403(b)",
)

# Retain the additional Krag coverage without mixing it into the paired score.
KRAG_EXTRA_CASES = (
    RankedCase(
        "jamie krag current electricity bill", "power-current", task="current_address"
    ),
    RankedCase(
        "jamie krag signed release of tax records",
        "jamie-release-signed",
        task="signed_authorization",
    ),
    RankedCase(
        "jamie krag employer equity vesting schedule",
        "jamie-rsu-schedule",
        task="equity_vesting",
    ),
    RankedCase(
        "aimee smith-krag june gas statement", "gas-current", task="current_address"
    ),
    RankedCase(
        "aimee smith-krag long-term disability summary",
        "aimee-disability",
        task="disability_coverage",
    ),
)

# One mistake per query; keep clean controls, gold keys and result types fixed.
TYPO_VARIANTS = {
    "karen reed": "karen reeed",  # repeated key
    "aimee smith-krag": "aimee smith-karg",  # transposed letters
    "jamie krag latest 401(k) statement": "jamie karg latest 401(k) statement",
    "utility bill reed": "utility bill reeed",
    "reed authorization": "reed authoriztion",  # dropped letter
    "jamie krag employer equity vesting schedule": "jamie krag employer equity vesting scheudle",
    "aimee smith-krag long-term disability summary": "aimee smith-krag long-term disabilty summary",
}
MATCHED_GROUPS = {"Reed": REED_CASES, "Krag": KRAG_CASES, "Aimee": AIMEE_CASES}
CLEAN_GROUPS = {**MATCHED_GROUPS, "Krag extras": KRAG_EXTRA_CASES}
CLEAN_CASES = {case.query: case for group in CLEAN_GROUPS.values() for case in group}
TYPO_CASES = tuple(
    replace(CLEAN_CASES[clean], query=typo, expected_recency_active=None)
    for clean, typo in TYPO_VARIANTS.items()
)
RANKED_GROUPS = {**CLEAN_GROUPS, "Typos": TYPO_CASES}

# Keep the archived holdout on its original 23-document corpus.
POST_HOLDOUT_KEYS = frozenset(
    {
        "jamie-release-draft",
        "jamie-release-signed",
        "aimee-403b-mar",
        "aimee-403b-jun",
        "gas-old-address",
        "aimee-release-draft",
        "aimee-release-signed",
    }
)


def seed_ranked(
    search: Search, *, expanded: bool = True
) -> dict[str, Client | Document]:
    clients = {
        owner: search.create_client(
            ClientInput(first_name=first, last_name=last, email=email)
        )
        for owner, first, last, email in (
            ("jamie", "Jamie", "Krag", "jamie.krag@example.com"),
            ("aimee", "Aimee", "Smith-Krag", "aimee.smith-krag@example.com"),
            ("karen", "Karen", "Reed", "karen.reed@example.com"),
        )
    }
    records: dict[str, Client | Document] = dict(clients)
    for corpus in ("krag", "reed"):
        for key, fixture in load_documents(CORPORA[corpus]).items():
            if fixture.owner == "household":
                continue  # The API cannot attach one record to two clients.
            if not expanded and key in POST_HOLDOUT_KEYS:
                continue
            records[key] = search.add_document(
                clients[fixture.owner].id, fixture.to_document_input()
            )
    return records


type Case = ExactCase | RankedCase


class CaseResult(TypedDict):
    query: str
    gold_ranks: dict[str, int | None]
    top5: list[str]
    result_count: int
    passed: bool
    hit5: bool


def score_case(case: Case, keys: list[str]) -> CaseResult:
    exact = isinstance(case, ExactCase)
    gold = case.expected_keys if exact else (case.expected_key,)
    # First occurrence matters for rank. Exact-set checks also reject duplicates.
    positions: dict[str, int] = {}
    for rank, key in enumerate(keys, 1):
        positions.setdefault(key, rank)
    ranks = {key: positions.get(key) for key in gold}
    return CaseResult(
        query=case.query,
        gold_ranks=ranks,
        top5=keys[:5],
        result_count=len(keys),
        passed=sorted(keys) == sorted(gold) if exact else keys[:1] == list(gold),
        hit5=any(rank is not None and rank <= 5 for rank in ranks.values()),
    )


def run_cases(
    search: Search, records: dict[str, Client | Document], cases: Sequence[Case]
) -> list[CaseResult]:
    keys_by_id = {record.id: key for key, record in records.items()}
    return [
        score_case(
            case,
            [
                keys_by_id[row.id]
                for row in search.search(case.query)
                if isinstance(case, ExactCase) or isinstance(row, case.result_type)
            ],
        )
        for case in cases
    ]


def summarize(cases: Sequence[Case], results: Sequence[CaseResult]) -> EvalResult:
    failures: list[str] = []
    for case, result in zip(cases, results, strict=True):
        if result["passed"]:
            continue
        if isinstance(case, ExactCase):
            failures.append(
                f"{case.query!r}: expected exact set {list(case.expected_keys)!r}; "
                f"got {result['result_count']} hits, first five: {result['top5']!r}"
            )
        else:
            rank = result["gold_ranks"][case.expected_key]
            failures.append(
                f"{case.query!r}: expected top {case.result_type.__name__.lower()} "
                f"{case.expected_key!r} (rank: {rank or 'absent'}); "
                f"first five of that type: {result['top5']!r}"
            )
    return EvalResult(total=len(cases), failures=tuple(failures))


def run_exact(search: Search) -> list[CaseResult]:
    return run_cases(search, seed_substrings(search), EXACT_CASES)


def run_ranked(search: Search) -> dict[str, list[CaseResult]]:
    records = seed_ranked(search)
    return {
        group: run_cases(search, records, cases)
        for group, cases in RANKED_GROUPS.items()
    }


def evaluate(approach: PostgresApproach) -> dict[str, EvalResult]:
    with postgres_container() as dsn, search_factory(Postgres(dsn, approach)) as search:
        exact = run_exact(search)
    with postgres_container() as dsn, search_factory(Postgres(dsn, approach)) as search:
        ranked = run_ranked(search)
    return {
        EXACT_GROUP: summarize(EXACT_CASES, exact),
        **{
            group: summarize(cases, ranked[group])
            for group, cases in RANKED_GROUPS.items()
        },
    }
