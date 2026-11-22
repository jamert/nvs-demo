"""Browse synthetic advisor search corpora from the terminal."""

import argparse
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from nevis_search.search import DocumentInput

CASES_DIR = Path(__file__).with_name("cases")
CORPORA = {
    "krag": CASES_DIR / "krag.jsonl",
    "reed": CASES_DIR / "reed.jsonl",
}


class FixtureDocument(DocumentInput):
    key: str
    owner: Literal["jamie", "aimee", "household", "karen"]
    date: date
    basis: Literal["adapted", "invented"]

    def to_document_input(self) -> DocumentInput:
        return DocumentInput(title=self.title, content=self.content)


def load_documents(path: Path = CORPORA["krag"]) -> dict[str, FixtureDocument]:
    documents: dict[str, FixtureDocument] = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                document = FixtureDocument.model_validate_json(line)
            except ValidationError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if document.key in documents:
                raise ValueError(
                    f"{path}:{line_number}: duplicate key {document.key!r}"
                )
            documents[document.key] = document
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        choices=CORPORA,
        default="krag",
        help="Case to browse (default: krag).",
    )
    parser.add_argument(
        "--list", action="store_true", help="Show titles without bodies."
    )
    parser.add_argument("keys", nargs="*", help="Document keys to show (default: all).")
    args = parser.parse_args()

    try:
        documents = load_documents(CORPORA[args.case])
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")

    keys: list[str] = args.keys or list(documents)
    unknown = [key for key in keys if key not in documents]
    if unknown:
        parser.error(
            f"unknown key(s) in {args.case}: {', '.join(unknown)}; use --list to browse"
        )

    if not args.list:
        print("SYNTHETIC EVALUATION RECORDS — not valid for verification or filing.\n")
    for key in keys:
        document = documents[key]
        if args.list:
            print(f"{key:25} {document.date}  {document.title}")
            continue
        print(f"=== {document.title} ===")
        print(f"{key} | {document.owner} | {document.date} | {document.basis}\n")
        print(f"{document.content}\n")


if __name__ == "__main__":
    main()
