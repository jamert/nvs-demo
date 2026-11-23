"""Shared query routing for paired ranking experiments (not authorization)."""

import re
from collections.abc import Callable, Sequence

from .core import Client, Document


def route_query(
    query: str,
    clients: Sequence[Client],
    documents: Sequence[Document],
    rank: Callable[[str, Sequence[Document]], Sequence[Document]],
) -> list[Client | Document]:
    """Use identical exact/literal routing before entering an experimental ranker.

    Rows are in insertion order. Matches on the original client fields remain
    literal. A unique named owner restricts candidates; ambiguous names do not.
    Literal document matches take precedence and keep their original exact set.
    """
    query = query.strip().casefold()
    if not query:
        return []
    names = [f"{c.first_name} {c.last_name}".casefold() for c in clients]
    client_hits = [
        client
        for client, name in zip(clients, names, strict=True)
        if any(
            query in field
            for field in (name, client.email.casefold(), client.description.casefold())
        )
    ]

    def literal_documents(
        candidates: Sequence[Document], phrase: str
    ) -> list[Document]:
        return [
            doc
            for doc in candidates
            if phrase in doc.title.casefold() or phrase in doc.content.casefold()
        ]

    if "@" in query or query in names:
        # A client lookup can also occur literally in a document. Preserve
        # those document hits, but do not add approximate matches.
        return [*client_hits, *literal_documents(documents, query)]

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
    if len(owners) == 1:
        i, pattern = owners[0]
        query = re.sub(pattern, " ", query)
        query = " ".join(query.split()).strip(" ,:;–—")
        documents = [doc for doc in documents if doc.client_id == clients[i].id]
    if not query:
        return list(client_hits)

    literal = literal_documents(documents, query)
    return [*client_hits, *(literal or rank(query, documents))]
