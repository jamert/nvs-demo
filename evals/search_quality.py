from dataclasses import dataclass

from nevis_search.search import ClientInput, Document, DocumentInput, search_factory


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


def evaluate() -> EvalResult:
    failures: list[str] = []
    with search_factory() as search:
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
