import argparse
import subprocess
from pathlib import Path

from .search_quality import evaluate, evaluate_substrings


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

    substrings = evaluate_substrings()
    ranked = evaluate()
    total = substrings.total + ranked.total
    passed = total - len(substrings.failures) - len(ranked.failures)
    summary = (
        f"{passed}/{total} cases passed "
        f"(substring: {substrings.summary}; Reed: {ranked.summary})"
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
            "--trailer",
            f"Search-Eval: {summary}",
            "--",
            args.message_file,
        ],
        check=True,
    )
    print(f"Search quality: {summary}")
    for label, result in (("Substring", substrings), ("Reed", ranked)):
        for failure in result.failures:
            print(f"{label}: {failure}")


if __name__ == "__main__":
    main()
