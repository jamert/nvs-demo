"""Shared query routing for ranked and rule-based search (not authorization)."""

import re
from collections.abc import Callable, Sequence

from .core import Client, Document, RecencyObserver, RecencyTrace
from .query_rules import (
    add_rule_candidates,
    add_statement_candidates,
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


def route_query(
    query: str,
    clients: Sequence[Client],
    load_documents: Callable[[], Sequence[Document]],
    rank: RankDocuments | None = None,
    *,
    observe_recency: RecencyObserver | None = None,
) -> list[Client | Document] | None:
    """Return insertion-ordered exact/literal hits or use the selected ranker.

    Active rules add candidates to that baseline. With no ranker and no active
    rule, return None to leave ordinary substring search to the store's SQL.
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

    def name_pattern(name: str) -> str:
        return rf"(?<![\w-]){re.escape(name)}(?![\w-])"

    full = [
        (i, name_pattern(name))
        for i, name in enumerate(names)
        if re.search(name_pattern(name), query)
    ]
    surname = [
        (i, pattern)
        for i, client in enumerate(clients)
        if client.last_name.strip()
        and re.search(pattern := name_pattern(client.last_name.casefold()), query)
    ]
    owners = full or surname
    owner_id = None
    if len(owners) == 1:
        i, pattern = owners[0]
        query = re.sub(pattern, " ", query)
        query = " ".join(query.split()).strip(" ,:;–—")
        owner_id = clients[i].id

    rule = (
        match_query_rule(query)
        if len(owners) <= 1 and may_match_query_rule(original)
        else None
    )
    recency = match_recency_query(query) if len(owners) <= 1 else None
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
