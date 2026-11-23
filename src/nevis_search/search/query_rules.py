"""Narrow, directional query rules over title and content phrases."""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
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


_PLAN_TEXT = r"(?:401(?:\(k\)|k)|403(?:\(b\)|b))"
_PLAN = re.compile(rf"(?<!\w){_PLAN_TEXT}(?!\w)")
_RECENCY_CUE = r"\b(?:latest|newest|current)\b"
_RECENCY_CUE_PATTERN = re.compile(_RECENCY_CUE)
_RECENCY_QUERY = re.compile(
    rf"(?:the\s+)?{_RECENCY_CUE}\s+(?P<plan>{_PLAN_TEXT})\s+statements?"
)
_STATEMENT_TITLE = re.compile(r"\bstatement\b")
_STATEMENT_HEADING = re.compile(rf"{_PLAN_TEXT}\s+statement\b")
_PLAN_LABEL = re.compile(r"plan(?: type)?\s*:")
_ACCOUNT_LABEL = re.compile(r"account( ending| number)?\s*:\s*(.*)")


def _plan_key(plan: str) -> str:
    return plan.replace("(", "").replace(")", "")


def match_recency_query(residual: str) -> tuple[str, str] | None:
    if match := _RECENCY_QUERY.fullmatch(residual):
        plan = match["plan"]
        return _plan_key(plan), f"{plan} statement"
    return None


def _statement_accounts(doc: Document, plan: str) -> frozenset[str] | None:
    title = doc.title.casefold()
    content = doc.content.casefold()
    if {_plan_key(term) for term in _PLAN.findall(f"{title}\n{content}")} != {plan}:
        return None

    fields = [part.strip() for part in re.split(r"[\r\n|]", content)]
    if not (
        any(_STATEMENT_HEADING.match(field) for field in fields)
        or (
            _STATEMENT_TITLE.search(title)
            and (
                _PLAN.search(title)
                or any(
                    _PLAN_LABEL.match(field) and _PLAN.search(field) for field in fields
                )
            )
        )
    ):
        return None

    accounts: set[str] = set()
    for field in fields:
        if match := _ACCOUNT_LABEL.fullmatch(field):
            kind, value = match.groups()
            value = value.removesuffix(".")
            if kind == " ending" and re.fullmatch(r"[0-9]{4}", value):
                accounts.add(f"ending:{value}")
            elif kind != " ending" and re.fullmatch(r"[*x]*[0-9]+", value):
                accounts.add(f"number:{value}")
            else:
                accounts.add("")  # Explicit but unusable; do not infer identity.
    return frozenset(accounts)


def add_statement_candidates(
    plan: str, baseline: Sequence[Document], candidates: Sequence[Document]
) -> tuple[list[Document], dict[UUID, frozenset[str]]]:
    results = list(baseline)
    seen = {doc.id for doc in baseline}
    accounts_by_id: dict[UUID, frozenset[str]] = {}
    for doc in candidates:
        if (accounts := _statement_accounts(doc, plan)) is not None:
            accounts_by_id[doc.id] = accounts
            if doc.id not in seen:
                results.append(doc)
                seen.add(doc.id)
    return results, accounts_by_id


def rerank_statements(
    candidates: Sequence[Document], accounts_by_id: Mapping[UUID, frozenset[str]]
) -> list[Document]:
    labelled = {doc.client_id for doc in candidates if accounts_by_id.get(doc.id)}
    groups: dict[tuple[UUID, frozenset[str]], list[tuple[int, date, Document]]] = (
        defaultdict(list)
    )
    for i, doc in enumerate(candidates):
        accounts = accounts_by_id.get(doc.id)
        if accounts is None or doc.document_date is None:
            continue
        # Unlabelled versions compare only where no candidate has an account label.
        if (not accounts and doc.client_id not in labelled) or (
            len(accounts) == 1 and "" not in accounts
        ):
            groups[doc.client_id, accounts].append((i, doc.document_date, doc))

    results = list(candidates)
    for members in groups.values():
        ranked = sorted(members, key=lambda member: member[1], reverse=True)
        for (i, _, _), (_, _, doc) in zip(members, ranked, strict=True):
            results[i] = doc
    return results


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    words = f" {_normalize(text)} "
    return any(f" {phrase} " in words for phrase in phrases)


def may_match_query_rule(query: str) -> bool:
    """Check cheaply whether the substring stores need to resolve an owner."""
    query = query.casefold()
    return "@" not in query and (
        any(_contains_phrase(query, rule.query_phrases) for rule in _RULES)
        or (
            _RECENCY_CUE_PATTERN.search(query) is not None
            and _PLAN.search(query) is not None
        )
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
