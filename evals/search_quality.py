from dataclasses import dataclass

from nevis_search.config import Postgres
from nevis_search.search import (
    Client,
    ClientInput,
    Document,
    DocumentInput,
    search_factory,
)
from tests.harness.environment import postgres_container

from .read_documents import CORPORA, load_documents


@dataclass(frozen=True)
class SearchCase:
    query: str
    expected_titles: tuple[str, ...]


CORPUS = {
    "Electricity statement": "The electricity account shows usage for the service address.",
    "Water bill": "The current balance is for the service address.",
    "Investment report": "The portfolio gained value in the last quarter.",
}

CASES = (
    SearchCase("water bill", ("Water bill",)),
    SearchCase("portfolio gained", ("Investment report",)),
    SearchCase("  ELECTRICITY ACCOUNT  ", ("Electricity statement",)),
    SearchCase("service address", ("Electricity statement", "Water bill")),
    SearchCase("passport", ()),
)


@dataclass(frozen=True)
class EvalResult:
    total: int
    failures: tuple[str, ...]

    @property
    def summary(self) -> str:
        return f"{self.total - len(self.failures)}/{self.total} cases passed"


def evaluate_substrings() -> EvalResult:
    failures: list[str] = []
    with postgres_container() as dsn, search_factory(Postgres(dsn)) as search:
        client = search.create_client(
            ClientInput(first_name="Test", last_name="Client", email="test@example.com")
        )
        documents = {
            title: search.add_document(
                client.id, DocumentInput(title=title, content=content)
            )
            for title, content in CORPUS.items()
        }

        for case in CASES:
            results = search.search(case.query)
            expected_ids = sorted(documents[title].id for title in case.expected_titles)
            if sorted(result.id for result in results) != expected_ids:
                actual = [
                    result.title
                    if isinstance(result, Document)
                    else f"client: {result.first_name} {result.last_name}"
                    for result in results
                ]
                failures.append(
                    f"{case.query!r}: expected {list(case.expected_titles)!r}, "
                    f"got {actual!r}"
                )

    return EvalResult(total=len(CASES), failures=tuple(failures))


@dataclass(frozen=True)
class RankedCase:
    query: str
    expected_key: str
    result_type: type[Client | Document] = Document


# Judged from the advisor's task, not the baseline's output. See doc/advisor-tasks.md.
REED_CASES = (
    RankedCase("karen reed", "karen", Client),
    RankedCase("reed address", "karen-electric-current"),
    RankedCase("reed address proof", "karen-electric-current"),
    RankedCase("utility bill reed", "karen-electric-current"),
    RankedCase("reed 401k", "karen-401k-jun"),
    RankedCase("401k statement reed", "karen-401k-jun"),
    RankedCase("reed latest 401(k) statement", "karen-401k-jun"),
    RankedCase("reed authorization", "karen-release-signed"),
    RankedCase("reed permission to share with accountant", "karen-release-signed"),
    RankedCase("signed release of information reed", "karen-release-signed"),
)


def evaluate() -> EvalResult:
    failures: list[str] = []
    with postgres_container() as dsn, search_factory(Postgres(dsn)) as search:
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
                records[key] = search.add_document(
                    clients[fixture.owner].id, fixture.to_document_input()
                )

        keys_by_id = {record.id: key for key, record in records.items()}
        for case in REED_CASES:
            expected = records[case.expected_key]
            results = search.search(case.query)
            # Keep returned order within the requested type. In particular, a
            # client hit cannot satisfy or displace a document hit in this score.
            ranked = [
                record.id for record in results if isinstance(record, case.result_type)
            ]
            if ranked[:1] == [expected.id]:
                continue

            rank = ranked.index(expected.id) + 1 if expected.id in ranked else "absent"
            actual = [keys_by_id[record_id] for record_id in ranked[:5]]
            failures.append(
                f"{case.query!r}: expected top {case.result_type.__name__.lower()} "
                f"{case.expected_key!r} (rank: {rank}); "
                f"first five of that type: {actual!r}"
            )

    return EvalResult(total=len(REED_CASES), failures=tuple(failures))
