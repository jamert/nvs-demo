from datetime import date

import pytest

from nevis_search.search.document_dates import extract_document_date


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Statement period: April 1–June 30, 2025.", date(2025, 6, 30)),
        ("Statement period: April 1–June 30,\t2025", date(2025, 6, 30)),
        ("Period ending: jUnE 30, 2025", date(2025, 6, 30)),
        ("Statement period end: 2025-06-30", date(2025, 6, 30)),
        ("Plan: 401(k) | Statement period: 2025-04-01/2025-06-30", date(2025, 6, 30)),
        ("Statement period: 2025-04-01 to 2025-06-30", date(2025, 6, 30)),
        ("Statement period: April 1-30, 2025", date(2025, 4, 30)),
        ("Statement period: December 1, 2024—January 31, 2025", date(2025, 1, 31)),
        (
            "Period ending: 2024-02-29\nPeriod ending: February 29, 2024",
            date(2024, 2, 29),
        ),
        ("Period ending: 2025-06-30\nStatement date: 2025-07-01", date(2025, 6, 30)),
        ("", None),
        ("Due date: 2025-07-01\nStatement date: June 30, 2025\nApril 5, 2024", None),
        ("Expected period ending: 2025-06-30", None),
        ("Service period: April 1–June 30, 2025", None),
        ("Period ending: 04/05/2025", None),
        ("Period ending: 2025-02-29", None),
        ("Period ending: 2025-06-30 or 2025-07-01", None),
        ("Statement period: December 1–January 31, 2025", None),
        ("Statement period: 2025-07-01/2025-06-30", None),
        ("Statement period: April 31–June 30, 2025", None),
        ("Statement period: April 1 through June 30, 2025", None),
        ("Period ending: 2025-06-30\nPeriod ending: 2025-03-31", None),
        ("Period ending: 2025-06-30\nPeriod ending: not available", None),
    ],
)
def test_extract_document_date(content: str, expected: date | None) -> None:
    assert extract_document_date(content) == expected
