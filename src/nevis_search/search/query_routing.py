"""Shared query routing for ranked and rule-based search (not authorization)."""

import re
from collections.abc import Callable, Sequence
from itertools import chain
from uuid import UUID

from .core import Client, Document, RecencyObserver, RecencyTrace
from .query_rules import (
    QueryRule,
    add_rule_candidates,
    add_statement_candidates,
    has_explicit_statement_period,
    match_query_rule,
    match_recency_query,
    may_match_query_rule,
    rerank_statements,
)

type RankDocuments = Callable[[str, Sequence[Document]], Sequence[Document]]


def _literal_documents(candidates: Sequence[Document], phrase: str) -> list[Document]:
    return [
        doc
        for doc in candidates
        if phrase in doc.title.casefold() or phrase in doc.content.casefold()
    ]


def _without_owner(query: str, name: str) -> str | None:
    pattern = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
    residual, count = re.subn(pattern, " ", query)
    return " ".join(residual.split()).strip(" ,:;–—") if count else None


def route_query(
    query: str,
    clients: Sequence[Client],
    load_documents: Callable[[], Sequence[Document]],
    rank: RankDocuments | None = None,
    *,
    append_ranked_to_literal: bool = False,
    observe_recency: RecencyObserver | None = None,
) -> list[Client | Document] | None:
    """Use literal hits before ranking, or append ranked hits for ordinary queries.

    Active rules and explicit statement periods keep the literal-or-ranked
    baseline. With no ranker and no active rule, leave ordinary search to SQL.
    """
    original = query = query.strip().casefold()
    if not query:
        return [] if rank is not None else None
    names = [f"{c.first_name} {c.last_name}".casefold() for c in clients]
    client_hits = [
        client
        for client, name in zip(clients, names, strict=True)
        if any(
            query in field
            for field in (name, client.email.casefold(), client.description.casefold())
        )
    ]

    if "@" in query or query in names:
        # Exact lookups can also occur literally in document text.
        if rank is None:
            return None
        return [*client_hits, *_literal_documents(load_documents(), query)]

    may_match_rule = may_match_query_rule(original)

    def match_rules(phrase: str) -> tuple[QueryRule | None, tuple[str, str] | None]:
        return (
            match_query_rule(phrase) if may_match_rule else None,
            match_recency_query(phrase),
        )

    # A complete rule phrase is not an owner reference, even if it contains a name.
    rule, recency = match_rules(original)
    owner_id = None
    if rule is None and recency is None:
        full_names = [
            (client.id, residual)
            for client, name in zip(clients, names, strict=True)
            if (residual := _without_owner(original, name)) is not None
        ]
        if len(full_names) == 1:
            owner_id, query = full_names[0]
            rule, recency = match_rules(query)
        elif not full_names:
            surnames = [
                (client.id, residual)
                for client in clients
                if client.last_name.strip()
                and (residual := _without_owner(original, client.last_name.casefold()))
                is not None
            ]
            if len(surnames) == 1 and surnames[0][1] == "":
                query = ""  # Keep surname-only client lookup.
            elif may_match_rule:
                # A surname scopes document search only if the remaining rule matches.
                qualified = [
                    (client_id, residual, *matches)
                    for client_id, residual in surnames
                    if any(matches := match_rules(residual))
                ]
                if len(qualified) == 1:
                    owner_id, query, rule, recency = qualified[0]
    if rank is None and rule is None and recency is None:
        return None
    if not query:
        return list(client_hits)

    documents = load_documents()
    if owner_id is not None:
        documents = [doc for doc in documents if doc.client_id == owner_id]
    # Use the original substring term except when a rule adapts retrieval itself.
    if recency is not None:
        plan, query = recency
    literal = _literal_documents(
        documents, original if rank is None and recency is None else query
    )
    if (
        append_ranked_to_literal
        and rank is not None
        and rule is None
        and recency is None
        and not has_explicit_statement_period(query)
    ):
        merged: dict[UUID, Document] = {}
        for doc in chain(literal, rank(query, documents)):
            merged.setdefault(doc.id, doc)
        return [*client_hits, *merged.values()]

    baseline = literal or (rank(query, documents) if rank is not None else ())
    if rule is not None:
        baseline = add_rule_candidates(rule, baseline, documents)
    if recency is not None:
        candidates, accounts = add_statement_candidates(plan, baseline, documents)
        before = (
            tuple(doc.id for doc in candidates) if observe_recency is not None else ()
        )
        baseline = rerank_statements(candidates, accounts)
        if observe_recency is not None:
            observe_recency(
                RecencyTrace(True, before, tuple(doc.id for doc in baseline))
            )
    return [*client_hits, *baseline]
