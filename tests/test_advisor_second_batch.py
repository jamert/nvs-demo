from datetime import date
from unittest.mock import patch

import pytest

from evals.advisor_second_batch import (
    ACTIVITY_GROUP,
    ACTIVITY_NOTE_KEYS,
    ACTIVITY_TASK,
    AS_OF_DATE,
    MEETING_DATE,
    SECOND_BATCH_CORPUS,
    SINGLE_TARGET_GROUP,
    SINGLE_TARGET_TASKS,
    run_second_batch,
    score_activity,
    seed_second_batch,
    summarize_second_batch,
)
from evals.read_documents import CORPORA, load_documents
from evals.search_quality import seed_ranked
from nevis_search.config import SQLite
from nevis_search.search import Client, Document, search_factory


def test_second_batch_fixture_metadata_and_judgments() -> None:
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    old = {
        key: row
        for path in CORPORA.values()
        for key, row in load_documents(path).items()
    }
    tasks = (*SINGLE_TARGET_TASKS, ACTIVITY_TASK)
    queries = [query for task in tasks for query in task.queries]
    gold_keys = {key for task in tasks for key in task.expected_keys}
    distractor_keys = {key for task in tasks for key in task.near_misses}
    assert {task.number for task in tasks} == {1, 2, 4, 5, 6, 9, 10, 11, 12, 13, 14}
    assert len(queries) == len(set(queries)) == 22
    assert len(gold_keys) == sum(len(task.expected_keys) for task in tasks) == 12
    assert all(len(task.expected_keys) == 1 for task in SINGLE_TARGET_TASKS)
    assert len(ACTIVITY_TASK.expected_keys) == 2
    assert fixtures.keys().isdisjoint(old)
    assert len(fixtures) == 21
    assert fixtures.keys() == gold_keys | (distractor_keys - old.keys())
    for row in fixtures.values():
        assert row.basis == "invented" and row.owner != "household"
        assert row.date <= AS_OF_DATE
        assert all(query.casefold() not in row.content.casefold() for query in queries)
    for task in tasks:
        for key in task.expected_keys:
            assert fixtures[key].owner == task.owner
            assert key not in task.near_misses
        for key, reason in task.near_misses.items():
            assert reason and (fixtures | old)[key].owner != "household"

    assert fixtures["karen-meeting-jun10"].date == MEETING_DATE
    assert ACTIVITY_NOTE_KEYS == {
        key
        for key, row in (fixtures | old).items()
        if row.title.startswith("Activity note")
    }
    assert set(ACTIVITY_TASK.expected_keys) == {
        key
        for key in ACTIVITY_NOTE_KEYS
        if fixtures[key].owner == ACTIVITY_TASK.owner
        and MEETING_DATE < fixtures[key].date <= AS_OF_DATE
    }
    assert fixtures["karen-activity-jul10"].date == AS_OF_DATE
    assert fixtures["karen-ips-superseded"].date < fixtures["karen-ips-current"].date
    assert (
        fixtures["karen-questionnaire-completed"].date
        < fixtures["karen-questionnaire-blank"].date
    )
    assert fixtures["karen-vul-prior"].date < fixtures["karen-vul-current"].date


def test_seed_second_batch_keeps_existing_corpora_isolated() -> None:
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    with search_factory(SQLite()) as search:
        combined = seed_second_batch(search, fixtures)
    with search_factory(SQLite()) as search:
        ranked = seed_ranked(search)

    assert sum(isinstance(row, Document) for row in ranked.values()) == 30
    assert fixtures.keys().isdisjoint(ranked)
    assert set(combined) == ranked.keys() | fixtures.keys()
    assert sum(isinstance(row, Client) for row in combined.values()) == 3
    for key, fixture in fixtures.items():
        record = combined[key]
        assert isinstance(record, Document)
        assert record.client_id == combined[fixture.owner].id
        assert (record.title, record.content) == (fixture.title, fixture.content)


def test_score_activity_requires_distinct_notes_in_top_five_and_flags_false_hits() -> (
    None
):
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    first, second = ACTIVITY_TASK.expected_keys
    keys = [
        "karen-activity-jun06",
        first,
        "jamie-activity-jun20",
        "karen-meeting-jun10",
        first,
        second,
    ]
    partial = score_activity("query", keys, fixtures)
    assert partial["gold_ranks"] == {first: 2, second: 6}
    assert partial["ordered_keys"] == keys and partial["top5"] == keys[:5]
    assert partial["expected_in_top5"] == 1
    assert not partial["complete_hit5"]
    assert partial["out_of_window_top5"] == ["karen-activity-jun06"]
    assert partial["wrong_client_top5"] == ["jamie-activity-jun20"]

    complete = score_activity("query", [first, "karen-intake", second], fixtures)
    assert complete["gold_ranks"] == {first: 1, second: 3}
    assert complete["expected_in_top5"] == 2 and complete["complete_hit5"]
    assert complete["out_of_window_top5"] == complete["wrong_client_top5"] == []


@pytest.mark.parametrize("outside_date", [MEETING_DATE, date(2025, 7, 11)])
def test_score_activity_flags_meeting_day_and_future_notes(outside_date: date) -> None:
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    key = "karen-activity-jun06"
    fixtures[key] = fixtures[key].model_copy(update={"date": outside_date})
    result = score_activity("query", [key], fixtures)
    assert result["expected_in_top5"] == 0 and not result["complete_hit5"]
    assert result["out_of_window_top5"] == [key]
    assert result["wrong_client_top5"] == []


def test_run_second_batch_scores_full_document_order_without_client_hits() -> None:
    fixtures = load_documents(SECOND_BATCH_CORPUS)
    with search_factory(SQLite()) as search:
        records = seed_second_batch(search, fixtures)
        keys = ["karen-brokerage-tod", "karen-activity-jun13", "karen-activity-jul10"]
        mixed_hits = [
            records["karen"],
            *(records[key] for key in keys),
            records["jamie"],
        ]
        with (
            patch("evals.advisor_second_batch.seed_second_batch", return_value=records),
            patch.object(search, "search", return_value=mixed_hits),
        ):
            report = run_second_batch(search)

    assert report["documents"] == 51
    assert report["single_target"] == {"total": 20, "top1": 2, "hit5": 2}
    assert set(report["by_task"]) == {task.number for task in SINGLE_TARGET_TASKS}
    for row in report["by_task"][1]["cases"]:
        assert row["ordered_keys"] == row["top5"] == keys
        assert row["gold_ranks"] == {keys[0]: 1}
    assert len(report["activity"]) == 2
    for row in report["activity"]:
        assert row["ordered_keys"] == keys
        assert row["gold_ranks"] == {keys[1]: 2, keys[2]: 3}
        assert row["complete_hit5"]

    _, partial_query = ACTIVITY_TASK.queries
    report["activity"][1] = score_activity(partial_query, keys[:2], fixtures)
    summary = summarize_second_batch(report)
    assert summary[SINGLE_TARGET_GROUP].summary == "2/20 cases passed"
    assert summary[ACTIVITY_GROUP].summary == "1/2 cases passed"
    assert summary[ACTIVITY_GROUP].failures == (
        f"{partial_query!r}: found 1/2 notes in top five",
    )
