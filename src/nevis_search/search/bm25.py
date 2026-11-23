import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from math import log1p

from .core import Document

_TERMS = re.compile(r"\w+")
_K1 = 1.2
_B = 0.75


def tokenize(text: str) -> list[str]:
    return _TERMS.findall(text.casefold())


class BM25Index:
    """Okapi BM25 over title and content treated as one equally weighted field."""

    def __init__(self, documents: Sequence[Document]) -> None:
        self._documents = documents
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for position, document in enumerate(documents):
            terms = Counter(tokenize(document.title))
            terms.update(tokenize(document.content))
            self._lengths.append(terms.total())
            for term, frequency in terms.items():
                self._postings[term].append((position, frequency))
        self._average_length = sum(self._lengths) / len(documents) if documents else 0.0

    def term_scores(self, term: str) -> Iterator[tuple[int, float]]:
        if not (postings := self._postings.get(term)):
            return
        n = len(self._documents)
        df = len(postings)
        idf = log1p((n - df + 0.5) / (df + 0.5))
        for position, frequency in postings:
            norm = 1 - _B + _B * self._lengths[position] / self._average_length
            yield position, idf * (frequency * (_K1 + 1)) / (frequency + _K1 * norm)

    def rank(self, query: str) -> list[Document]:
        scores: dict[int, float] = defaultdict(float)
        for term in dict.fromkeys(tokenize(query)):
            for position, score in self.term_scores(term):
                scores[position] += score
        ranked = sorted(scores, key=lambda position: (-scores[position], position))
        return [self._documents[position] for position in ranked]


def rank_bm25(query: str, documents: Sequence[Document]) -> list[Document]:
    return BM25Index(documents).rank(query)
