import argparse
import subprocess
from pathlib import Path

from .search_quality import evaluate


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

    result = evaluate()
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
            f"Search-Eval: {result.summary}",
            "--",
            args.message_file,
        ],
        check=True,
    )
    print(f"Search quality: {result.summary}")
    for failure in result.failures:
        print(failure)


if __name__ == "__main__":
    main()
