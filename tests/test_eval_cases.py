from dataclasses import replace
from unittest.mock import patch

import pytest

from evals.compare import by_task, compare_explicit_recency
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
    run_ranked,
    seed_ranked,
    seed_substrings,
    summarize,
)
from nevis_search.config import SQLite
from nevis_search.search import Client, Document, search_factory


def test_ranked_labels_refer_to_seeded_records_of_the_requested_type() -> None:
    with search_factory(SQLite()) as search:
        ranked = seed_ranked(search)
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
    assert sum(isinstance(row, Client) for row in ranked.values()) == 3
    assert sum(isinstance(row, Document) for row in ranked.values()) == 30
    for owner, keys in additions.items():
        client = ranked[owner]
        for key in keys:
            doc = ranked[key]
            assert isinstance(doc, Document)
            assert doc.client_id == client.id
    for cases in RANKED_GROUPS.values():
        for case in cases:
            assert isinstance(ranked[case.expected_key], case.result_type)


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
        assert reed_case.expected_recency_active is matched.expected_recency_active
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


def test_task_report_keeps_matched_clients_extras_and_typos_separate() -> None:
    with search_factory(SQLite()) as search:
        tasks = by_task(run_ranked(search))

    lookup = tasks["client_lookup"]
    assert "matched" in lookup and "typos" in lookup
    assert lookup["matched"] == {"total": 3, "top1": 3, "hit5": 3}
    assert lookup["typos"] == {"total": 2, "top1": 0, "hit5": 0}
    address = tasks["current_address"]
    assert "matched" in address and "by_client" in address
    assert "extras" in address and "typos" in address
    assert address["matched"]["total"] == 9
    assert {
        client: stats["total"] for client, stats in address["by_client"].items()
    } == {
        "Reed": 3,
        "Krag": 3,
        "Aimee": 3,
    }
    assert address["extras"]["total"] == 2
    assert address["typos"]["total"] == 1
    assert "matched" not in tasks["equity_vesting"]
    assert (
        sum(task["matched"]["total"] for task in tasks.values() if "matched" in task)
        == 30
    )


def test_typos_keep_the_same_target_and_type_as_the_clean_query() -> None:
    for (query, typo), case in zip(TYPO_VARIANTS.items(), TYPO_CASES, strict=True):
        clean = CLEAN_CASES[query]
        assert case.query == typo
        assert case.expected_key == clean.expected_key
        assert case.result_type is clean.result_type
        assert case.task == clean.task
        assert case.expected_recency_active is None
        assert case.query != clean.query


def test_compare_explicit_recency_replays_only_three_marked_matched_cases() -> None:
    with search_factory(SQLite()) as search:
        report = compare_explicit_recency(search)

    assert report["gold_present"] == 3
    assert report["rerank_off"] == {"total": 3, "top1": 0, "hit5": 3}
    assert report["rerank_on"] == {"total": 3, "top1": 3, "hit5": 3}
    assert report["controls"] == report["activation_mismatches"] == []
    assert [row["rerank_off"]["query"] for row in report["cases"]] == [
        "reed latest 401(k) statement",
        "jamie krag latest 401(k) statement",
        "aimee smith-krag latest 403(b) statement",
    ]
    assert all(
        row["expected_active"] and row["actual_active"] for row in report["cases"]
    )


def test_compare_explicit_recency_handles_a_deliberate_year_constraint() -> None:
    control = RankedCase(
        "reed latest 401(k) statement 2025",
        "karen-401k-jun",
        expected_recency_active=False,
    )
    with search_factory(SQLite()) as search:
        report = compare_explicit_recency(search, cases=[control])

    assert report["cases"] == report["activation_mismatches"] == []
    assert report["rerank_off"]["total"] == report["rerank_on"]["total"] == 0
    [row] = report["controls"]
    assert not row["expected_active"] and not row["actual_active"]
    assert row["rerank_off"] == row["rerank_on"]
    assert row["rerank_on"]["query"] == control.query


def test_compare_explicit_recency_reports_both_activation_mismatches_by_query() -> None:
    active = RankedCase(
        "reed latest 401(k) statement", "karen-401k-jun", expected_recency_active=False
    )
    constrained = replace(
        active, query=f"{active.query} 2025", expected_recency_active=True
    )
    with search_factory(SQLite()) as search:
        report = compare_explicit_recency(search, cases=[constrained, active])

    assert report["activation_mismatches"] == [constrained.query, active.query]
    [missing_activation] = report["cases"]
    assert (
        missing_activation["expected_active"]
        and not missing_activation["actual_active"]
    )
    assert missing_activation["rerank_off"] == missing_activation["rerank_on"]
    assert report["rerank_off"]["total"] == report["rerank_on"]["total"] == 1
    [unexpected_activation] = report["controls"]
    assert (
        not unexpected_activation["expected_active"]
        and unexpected_activation["actual_active"]
    )
    assert unexpected_activation["rerank_off"] != unexpected_activation["rerank_on"]
