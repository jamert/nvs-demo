"""Extract a statement period end from explicitly labeled document text."""

import re
from datetime import date

_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH = "(?:" + "|".join(_MONTHS) + ")"
_DAY = r"[0-9]{1,2}"
_YEAR = r"[0-9]{4}"
_ISO = rf"{_YEAR}-[0-9]{{2}}-[0-9]{{2}}"
_NAMED = re.compile(rf"({_MONTH})\s+({_DAY}),\s+({_YEAR})")
_SEPARATOR = r"\s*(?:[-–—]|\bto\b)\s*"
_NAMED_RANGE = re.compile(
    rf"(?P<month>{_MONTH})\s+(?P<day>{_DAY})(?:,\s+(?P<year>{_YEAR}))?"
    rf"{_SEPARATOR}(?P<end>(?:{_MONTH}\s+)?{_DAY},\s+{_YEAR})"
)
_ISO_RANGE = re.compile(rf"({_ISO})(?:{_SEPARATOR}|\s*/\s*)({_ISO})")
_PERIOD_LABEL = re.compile(
    r"(statement period|(?:statement )?period end(?:ing)?)\s*:\s*(.*)"
)


def _parse_date(value: str) -> date:
    if match := _NAMED.fullmatch(value):
        month, day, year = match.groups()
        return date(int(year), _MONTHS.index(month) + 1, int(day))
    if re.fullmatch(_ISO, value):
        return date.fromisoformat(value)
    raise ValueError("Unsupported statement date format")


def _period_end(value: str) -> date:
    if match := _ISO_RANGE.fullmatch(value):
        start_text, end_text = match.groups()
        start, end = _parse_date(start_text), _parse_date(end_text)
    elif match := _NAMED_RANGE.fullmatch(value):
        month, day, year, end_text = match.groups()
        if end_text[0].isdigit():
            end_text = f"{month} {end_text}"
        end = _parse_date(end_text)
        start = date(
            int(year) if year else end.year, _MONTHS.index(month) + 1, int(day)
        )
    else:
        raise ValueError("Unsupported statement period format")
    if start > end:
        raise ValueError("Statement period ends before it starts")
    return end


def extract_document_date(content: str) -> date | None:
    dates: set[date] = set()
    for field in re.split(r"[\n\r|]", content.casefold()):
        if match := _PERIOD_LABEL.fullmatch(field.strip()):
            label, value = match.groups()
            try:
                value = value.removesuffix(".")
                dates.add(
                    _period_end(value)
                    if label == "statement period"
                    else _parse_date(value)
                )
            except ValueError:
                return None
    return next(iter(dates)) if len(dates) == 1 else None
