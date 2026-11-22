from pathlib import Path
from typing import Any

import yaml

ASSIGNMENT_SPEC = Path(__file__).resolve().parents[2] / "doc" / "openapi.yml"


def assert_matches_assignment(actual: dict[str, object]) -> None:
    """Check the served contract against the assignment, not byte-for-byte YAML."""
    expected = yaml.safe_load(ASSIGNMENT_SPEC.read_text(encoding="utf-8"))
    _assert_contains(expected, actual, actual)


def _assert_contains(
    expected: Any,
    actual: Any,
    root: dict[str, object],
    path: tuple[str, ...] = (),
    *,
    request_body: bool = False,
) -> None:
    location = " > ".join(path) or "OpenAPI"
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{location}: expected an object"

        # FastAPI uses references for inline body schemas. Keep references that
        # the assignment names, so renaming Client or Document still fails.
        if "$ref" in actual and "$ref" not in expected:
            ref = actual["$ref"]
            assert ref.startswith("#/"), f"{location}: expected a local reference"
            target: Any = root
            for key in ref[2:].split("/"):
                key = key.replace("~1", "/").replace("~0", "~")
                assert key in target, f"{location}: unresolved reference {ref}"
                target = target[key]
            actual = target

        # Search narrows generic objects to Client or Document. Every variant
        # must retain what the assignment requires of an item.
        if "type" in expected and "type" not in actual:
            for keyword in ("anyOf", "oneOf"):
                if keyword in actual:
                    variants = actual[keyword]
                    assert variants, f"{location}: empty {keyword}"
                    for index, variant in enumerate(variants):
                        _assert_contains(
                            expected,
                            variant,
                            root,
                            (*path, keyword, str(index)),
                            request_body=request_body,
                        )
                    return

        path_item_or_operation = path[:1] == ("paths",) and len(path) in (2, 3)
        if path_item_or_operation:
            _assert_parameters(expected, actual, root, path)
            assert "requestBody" not in actual or "requestBody" in expected, (
                f"{location}: unexpected request body"
            )
        if path[-1:] == ("requestBody",):
            assert actual.get("content", {}).keys() == expected["content"].keys(), (
                f"{location}: request body media types differ"
            )
        if request_body and expected.get("type") == "object":
            for key in ("properties", "required"):
                assert set(actual.get(key, [])) == set(expected.get(key, [])), (
                    f"{location}: request body {key} differ"
                )

        for key, value in expected.items():
            if path_item_or_operation and key == "parameters":
                continue  # Parameters were compared by name and location above.
            assert key in actual, f"{location}: missing {key!r}"
            _assert_contains(
                value,
                actual[key],
                root,
                (*path, key),
                request_body=request_body or key == "requestBody",
            )
    elif isinstance(expected, list):
        assert isinstance(actual, list) and all(item in actual for item in expected), (
            f"{location}: expected {expected!r} in {actual!r}"
        )
    else:
        assert type(actual) is type(expected) and actual == expected, (
            f"{location}: expected {expected!r}, got {actual!r}"
        )


def _assert_parameters(
    expected: dict[str, Any],
    actual: dict[str, Any],
    root: dict[str, object],
    path: tuple[str, ...],
) -> None:
    expected_params = {(p["in"], p["name"]): p for p in expected.get("parameters", [])}
    actual_params = {(p["in"], p["name"]): p for p in actual.get("parameters", [])}
    location = " > ".join(path)
    for key in actual_params.keys() - expected_params.keys():
        assert key[0] == "header", (
            f"{location}: unexpected {key[0]} parameter {key[1]!r}"
        )
    for key, parameter in expected_params.items():
        assert key in actual_params, (
            f"{location}: missing {key[0]} parameter {key[1]!r}"
        )
        _assert_contains(
            parameter, actual_params[key], root, (*path, "parameters", *key)
        )
