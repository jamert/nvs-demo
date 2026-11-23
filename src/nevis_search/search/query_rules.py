"""Narrow, directional query rules over title and content phrases."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from .core import Document


@dataclass(frozen=True)
class QueryRule:
    query_phrases: tuple[str, ...]
    document_phrases: tuple[str, ...]


_RULES = (
    QueryRule(
        query_phrases=("address proof", "proof of address"),
        document_phrases=(
            "utility bill",
            "electricity statement",
            "gas bill",
            "gas statement",
        ),
    ),
)


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    words = f" {_normalize(text)} "
    return any(f" {phrase} " in words for phrase in phrases)


def may_match_query_rule(query: str) -> bool:
    """Check cheaply whether the substring stores need to resolve an owner."""
    return "@" not in query and any(
        _contains_phrase(query, rule.query_phrases) for rule in _RULES
    )


def match_query_rule(residual: str) -> QueryRule | None:
    # Do not drop any extra words (e.g. an unknown owner or a date constraint).
    phrase = _normalize(residual)
    return next((rule for rule in _RULES if phrase in rule.query_phrases), None)


def add_rule_candidates(
    rule: QueryRule, baseline: Sequence[Document], candidates: Sequence[Document]
) -> list[Document]:
    title_hits: list[Document] = []
    body_hits: list[Document] = []
    ordinary: list[Document] = []
    seen: set[UUID] = set()
    # Preserve baseline order within each tier; new hits follow in storage order.
    for is_baseline, documents in ((True, baseline), (False, candidates)):
        for doc in documents:
            if doc.id in seen:
                continue
            seen.add(doc.id)
            if _contains_phrase(doc.title, rule.document_phrases):
                title_hits.append(doc)
            elif _contains_phrase(doc.content, rule.document_phrases):
                body_hits.append(doc)
            elif is_baseline:
                ordinary.append(doc)
    return [*title_hits, *body_hits, *ordinary]
