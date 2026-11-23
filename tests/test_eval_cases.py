from unittest.mock import patch

import pytest

from evals.search_quality import (
    AIMEE_CASES,
    CLEAN_CASES,
    KRAG_CASES,
    RANKED_GROUPS,
    REED_CASES,
    TYPO_CASES,
    TYPO_VARIANTS,
    ExactCase,
    RankedCase,
    run_cases,
    seed_ranked,
    seed_substrings,
    summarize,
)
from nevis_search.config import SQLite
from nevis_search.search import Client, Document, search_factory


def test_ranked_labels_refer_to_seeded_records_of_the_requested_type() -> None:
    with search_factory(SQLite()) as search:
        original = seed_ranked(search, expanded=False)
    with search_factory(SQLite()) as search:
        expanded = seed_ranked(search)
    additions = {
        "jamie": ("jamie-release-draft", "jamie-release-signed"),
        "aimee": (
            "aimee-403b-mar",
            "aimee-403b-jun",
            "gas-old-address",
            "aimee-release-draft",
            "aimee-release-signed",
        ),
    }
    assert len(original) == 26  # 3 clients, 23 documents
    assert set(expanded) - set(original) == {
        key for keys in additions.values() for key in keys
    }
    for owner, keys in additions.items():
        client = expanded[owner]
        for key in keys:
            doc = expanded[key]
            assert isinstance(doc, Document)
            assert doc.client_id == client.id
    for cases in RANKED_GROUPS.values():
        for case in cases:
            assert isinstance(expanded[case.expected_key], case.result_type)


@pytest.mark.parametrize(
    ("cases", "owner", "name", "plan", "plain_plan"),
    [
        (KRAG_CASES, "jamie", "jamie krag", "401(k)", "401k"),
        (AIMEE_CASES, "aimee", "aimee smith-krag", "403(b)", "403b"),
    ],
)
def test_matched_queries_only_change_the_owner_and_plan_type(
    cases: tuple[RankedCase, ...], owner: str, name: str, plan: str, plain_plan: str
) -> None:
    with search_factory(SQLite()) as search:
        records = seed_ranked(search)
    client = records[owner]
    for reed_case, matched in zip(REED_CASES, cases, strict=True):
        reed_name = "karen reed" if reed_case.result_type is Client else "reed"
        normalized = (
            matched.query.replace(name, "<owner>")
            .replace(plan, "401(k)")
            .replace(plain_plan, "401k")
        )
        assert reed_case.query.replace(reed_name, "<owner>") == normalized
        assert reed_case.result_type is matched.result_type
        expected = records[matched.expected_key]
        if isinstance(expected, Document):
            assert expected.client_id == client.id
        else:
            assert expected == client


def test_shared_scoring_preserves_exact_sets_and_rank_within_type() -> None:
    with search_factory(SQLite()) as search:
        records = seed_substrings(search)
        client = records["client:test"]
        water = records["Water bill"]
        power = records["Electricity statement"]
        cases = (
            ExactCase("two documents", ("Water bill", "Electricity statement")),
            ExactCase("duplicate", ("Water bill",)),
            ExactCase("empty", ()),
            ExactCase("unexpected client", ()),
            RankedCase("ignore client hits", "Water bill"),
            RankedCase("not first", "Water bill"),
            RankedCase("not retrieved", "Water bill"),
        )
        with patch.object(
            search,
            "search",
            side_effect=[
                [power, water],
                [water, water],
                [],
                [client],
                [client, water],
                [client, power, water],
                [power],
            ],
        ):
            results = run_cases(search, records, cases)

    assert [row["passed"] for row in results] == [
        True,
        False,
        True,
        False,
        True,
        False,
        False,
    ]
    assert [row["gold_ranks"]["Water bill"] for row in results[-3:]] == [1, 2, None]
    assert results[-2]["hit5"] and not results[-1]["hit5"]
    assert results[-2]["top5"] == ["Electricity statement", "Water bill"]
    assert summarize(cases, results).passed == 3


def test_typos_keep_the_same_target_and_type_as_the_clean_query() -> None:
    for (query, typo), case in zip(TYPO_VARIANTS.items(), TYPO_CASES, strict=True):
        clean = CLEAN_CASES[query]
        assert case.query == typo
        assert case.expected_key == clean.expected_key
        assert case.result_type is clean.result_type
        assert case.query != clean.query
