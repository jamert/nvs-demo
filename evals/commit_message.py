import argparse
import subprocess
from pathlib import Path

from nevis_search.config import POSTGRES_APPROACHES

from .search_quality import evaluate, evaluate_substrings

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

    scores: dict[str, str] = {}
    for approach in POSTGRES_APPROACHES:
        substrings = evaluate_substrings(approach)
        ranked = evaluate(approach)
        total = substrings.total + ranked.total
        passed = total - len(substrings.failures) - len(ranked.failures)
        summary = (
            f"{passed}/{total} cases passed "
            f"(exact-set: {substrings.summary}; Reed top-1: {ranked.summary})"
        )
        scores[approach] = summary
        print(f"{approach}: {summary}")
        for label, result in (("Exact-set", substrings), ("Reed", ranked)):
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

    trailers: list[str] = []
    for approach, key in TRAILER_KEYS.items():
        trailers.extend(
            ("--trailer", f"{key}: {scores.get(approach, 'not integrated')}")
        )
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
