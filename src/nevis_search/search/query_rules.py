"""Narrow, directional query rules over title and content phrases."""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from .core import Document


@dataclass(frozen=True)
class QueryRule:
    query_phrases: tuple[str, ...]
    document_phrases: tuple[str, ...]
    account_suffix: str | None = None


_BENEFICIARY_RULE = QueryRule(
    query_phrases=("who inherits", "who will inherit"),
    document_phrases=("beneficiary designation", "transfer on death"),
)
_ACCOUNT_QUERY = re.compile(
    r"(?:who inherits|who will inherit) (?:the |my )?account ending (?:in )?(?P<suffix>[0-9]{4})"
)
# Recognize an explicit label even when its identifier is missing or unusable.
# Recency requires a whole field; beneficiary lookup also accepts inline references.
_ACCOUNT_REFERENCE = re.compile(
    r"\baccount(?:"
    r"\s+(?P<ending>ending)\b(?:\s+in\b\s*:?|\s*:|(?=\s*(?:[0-9]|[*•x]{2,})))"
    r"|\s+number\s*:|\s*:|(?=\s+[*•x]{2,}))"
    r"\s*(?:(?P<mask>[*•x]{2,}\s*|[*•x]?)(?P<digits>[0-9]+)(?!\w|[-./][0-9]))?"
)
_UNUSABLE_ACCOUNT = ""

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
    _BENEFICIARY_RULE,
    QueryRule(
        query_phrases=(
            "last appointment follow ups",
            "what was left to do after the last meeting",
            "open items from the last meeting",
        ),
        document_phrases=("follow up letter", "open items", "outstanding action items"),
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


def _plan_key(plan: str) -> str:
    return plan.replace("(", "").replace(")", "")


def match_recency_query(residual: str) -> tuple[str, str] | None:
    if match := _RECENCY_QUERY.fullmatch(residual):
        plan = match["plan"]
        return _plan_key(plan), f"{plan} statement"
    return None


def _statement_account_key(field: str) -> str | None:
    field = field.removesuffix(".")
    if (reference := _ACCOUNT_REFERENCE.match(field)) is None:
        return None
    digits = reference["digits"]
    if digits is None or reference.end() != len(field):
        return _UNUSABLE_ACCOUNT
    mask = reference["mask"].rstrip()
    if reference["ending"]:
        return (
            f"ending:{digits}" if not mask and len(digits) == 4 else _UNUSABLE_ACCOUNT
        )
    # Keep any mask and the entire identifier; a suffix does not identify a full number.
    return f"number:{mask}{digits}"


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

    return frozenset(
        key for field in fields if (key := _statement_account_key(field)) is not None
    )


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
            len(accounts) == 1 and _UNUSABLE_ACCOUNT not in accounts
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
    if match := _ACCOUNT_QUERY.fullmatch(phrase):
        return replace(_BENEFICIARY_RULE, account_suffix=match["suffix"])
    return next((rule for rule in _RULES if phrase in rule.query_phrases), None)


def _matches_account(doc: Document, suffix: str) -> bool:
    references = {
        reference["digits"]
        for reference in _ACCOUNT_REFERENCE.finditer(
            f"{doc.title}\n{doc.content}".casefold()
        )
        if reference["digits"] is not None
        and len(reference["digits"]) == 4
        and len(reference["mask"].rstrip()) != 1
    }
    return references == {suffix}


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
            if rule.account_suffix is not None and not _matches_account(
                doc, rule.account_suffix
            ):
                continue
            if _contains_phrase(doc.title, rule.document_phrases):
                title_hits.append(doc)
            elif _contains_phrase(doc.content, rule.document_phrases):
                body_hits.append(doc)
            elif is_baseline:
                ordinary.append(doc)
    return [*title_hits, *body_hits, *ordinary]
