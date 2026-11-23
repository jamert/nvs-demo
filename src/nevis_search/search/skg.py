"""Document-mediated query expansion after Grainger et al. (arXiv:1609.00464)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from math import log1p, sqrt, tanh

from .core import Document

_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "you",
        "your",
    ]
)


def tokenize(text: str) -> frozenset[str]:
    # Treat a parenthesized letter suffix in a numeric identifier as part of it.
    text = re.sub(r"\b(\d+)\(([a-z]+)\)", r"\1\2", text.casefold())
    return frozenset(
        term
        for term in re.findall(r"[^\W_]+", text)
        if len(term) > 1 and not term.isdecimal() and term not in _STOP_WORDS
    )


@dataclass(frozen=True)
class ExpansionEdge:
    seeds: tuple[str, ...]
    term: str
    supporting_docs: frozenset[int]
    weight: float


class TermIndex:
    def __init__(self, doc_terms: tuple[frozenset[str], ...]) -> None:
        self.doc_terms = doc_terms
        self.postings: dict[str, set[int]] = {}
        for i, terms in enumerate(doc_terms):
            for term in terms:
                self.postings.setdefault(term, set()).add(i)

    def expansion_edges(
        self, query_terms: frozenset[str], eligible_terms: set[str]
    ) -> list[ExpansionEdge]:
        seeds = tuple(sorted(query_terms & self.postings.keys()))
        if not seeds:
            return []
        joint = set.intersection(*(self.postings[seed] for seed in seeds))
        contexts = (
            [(seeds, joint)]
            if joint
            else [((seed,), self.postings[seed]) for seed in seeds]
        )
        n_background = len(self.doc_terms)
        best: dict[str, ExpansionEdge] = {}
        for context, foreground in contexts:
            related = set().union(*(self.doc_terms[i] for i in foreground))
            for term in (related & eligible_terms) - query_terms:
                posting = self.postings[term]
                # Avoid expanding to corpus singletons or ubiquitous terms.
                if not 2 <= len(posting) < n_background:
                    continue
                supporting_docs = foreground & posting
                support = len(supporting_docs)
                p = len(posting) / n_background
                expected = len(foreground) * p
                z = (support - expected) / sqrt(expected * (1 - p))
                if z <= 0:
                    continue
                weight = 0.5 * tanh(z / 2) * support / (support + 2)
                if term not in best or weight > best[term].weight:
                    best[term] = ExpansionEdge(
                        context, term, frozenset(supporting_docs), weight
                    )
        return sorted(best.values(), key=lambda edge: (-edge.weight, edge.term))[:8]


class LexicalIndex:
    def __init__(self, documents: Sequence[Document]) -> None:
        self.title_terms = tuple(tokenize(doc.title) for doc in documents)
        self.terms = TermIndex(
            tuple(
                title | tokenize(doc.content)
                for title, doc in zip(self.title_terms, documents, strict=True)
            )
        )

    def scores(self, term_weights: dict[str, float]) -> dict[int, float]:
        scores: dict[int, float] = {}
        n_documents = len(self.terms.doc_terms)
        for term, weight in sorted(term_weights.items()):
            if not (posting := self.terms.postings.get(term)):
                continue
            idf = log1p((n_documents - len(posting) + 0.5) / (len(posting) + 0.5))
            for i in posting:
                field_weight = 2 if term in self.title_terms[i] else 1
                scores[i] = scores.get(i, 0.0) + weight * field_weight * idf
        return scores


def rank_documents(
    query: str,
    documents: Sequence[Document],
    *,
    expand: bool,
    enrichment: tuple[frozenset[str], ...] = (),
) -> list[Document]:
    if not (query_terms := tokenize(query)) or not documents:
        return []
    lexical = LexicalIndex(documents)
    weights = dict.fromkeys(query_terms, 1.0)
    if expand:
        graph = (
            TermIndex(lexical.terms.doc_terms + enrichment)
            if enrichment
            else lexical.terms
        )
        weights.update(
            (edge.term, edge.weight)
            for edge in graph.expansion_edges(query_terms, set(lexical.terms.postings))
        )
    scores = lexical.scores(weights)
    return [documents[i] for i in sorted(scores, key=lambda i: (-scores[i], i))]
