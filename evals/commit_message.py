import argparse
import subprocess
from pathlib import Path

from nevis_search.config import POSTGRES_APPROACHES

from .advisor_second_batch import ACTIVITY_GROUP, evaluate_second_batch
from .search_quality import EXACT_GROUP, evaluate

TRAILER_KEYS = {
    "postgres-substring": "Search-Eval-Substring",
    "bm25": "Search-Eval-BM25",
    "dense-e5": "Search-Eval-Dense-E5",
    "skg": "Search-Eval-SKG",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a search eval score to a commit.")
    parser.add_argument("message_file", type=Path)
    args = parser.parse_args()

    # Don't let the trailer turn an empty message into a valid commit.
    message = subprocess.run(
        ["git", "stripspace", "--strip-comments"],
        input=args.message_file.read_bytes(),
        capture_output=True,
        check=True,
    ).stdout
    if not message:
        return

    trailers: list[str] = []
    for approach in POSTGRES_APPROACHES:
        results = evaluate(approach) | evaluate_second_batch(approach)
        total = sum(result.total for result in results.values())
        passed = sum(result.passed for result in results.values())
        breakdown = "; ".join(
            f"{name if name in (EXACT_GROUP, ACTIVITY_GROUP) else name + ' top-1'}: {result.summary}"
            for name, result in results.items()
        )
        summary = f"{passed}/{total} cases passed"
        trailers.extend(("--trailer", f"{TRAILER_KEYS[approach]}: {summary}"))
        print(f"{approach}: {summary} ({breakdown})")
        for label, result in results.items():
            for failure in result.failures:
                print(f"{approach} {label}: {failure}")

    # Remove the exact legacy trailer token. interpret-trailers' replacement
    # can match token prefixes, so don't ask it to replace "Search-Eval".
    original = args.message_file.read_bytes()
    parsed = subprocess.check_output(
        ["git", "interpret-trailers", "--parse"], input=original
    )
    if any(line.startswith(b"Search-Eval:") for line in parsed.splitlines()):
        lines = original.splitlines(keepends=True)
        for i in reversed(range(len(lines))):
            if lines[i].startswith(b"Search-Eval:"):
                end = i + 1
                while end < len(lines) and lines[end].startswith((b" ", b"\t")):
                    end += 1
                del lines[i:end]
                break
        args.message_file.write_bytes(b"".join(lines))

    subprocess.run(
        [
            "git",
            "interpret-trailers",
            "--in-place",
            "--if-exists",
            "replace",
            "--if-missing",
            "add",
            *trailers,
            "--",
            args.message_file,
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
