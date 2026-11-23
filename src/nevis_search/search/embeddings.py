import json
import os
from array import array
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from math import fsum
from pathlib import Path
from subprocess import PIPE, Popen
from threading import Lock
from typing import IO, Protocol, cast
from uuid import UUID

from .core import Document

# Rounded up from 0.793427, the strongest negative on an independent calibration
# set. No official or blind cases were used to choose this value.
MIN_COSINE = 0.80


type Vector = list[float]
type TextPassage = tuple[str, str]


class Encoder(Protocol):
    def query(self, text: str) -> Vector: ...

    def passages(self, texts: list[TextPassage]) -> list[list[Vector]]: ...


class LocalEncoder:
    def __init__(self, requests: IO[str], responses: IO[str]) -> None:
        self._requests = requests
        self._responses = responses

    @classmethod
    @contextmanager
    def connect(cls) -> Generator[LocalEncoder]:
        home = (
            Path(
                os.environ.get(
                    "NEVIS_EMBEDDINGS_HOME", "~/.cache/nevis-search/dense-e5"
                )
            )
            .expanduser()
            .resolve()
        )
        helper = home / "helper" / "bin" / "nevis-embedding-encoder"
        if not helper.is_file():
            raise RuntimeError(
                f"Dense E5 helper not found at {helper}; run "
                "sh experiments/embeddings/setup.sh (see doc/search/dense-e5.md)"
            )
        with Popen(
            [helper],
            env=os.environ | {"NEVIS_EMBEDDINGS_MODEL_DIR": str(home / "model")},
            stdin=PIPE,
            stdout=PIPE,
            text=True,
            encoding="utf-8",
        ) as proc:
            assert proc.stdin is not None and proc.stdout is not None
            if proc.stdout.readline().rstrip("\n") != "ready":
                raise RuntimeError("Local embedding encoder did not initialize")
            yield cls(proc.stdin, proc.stdout)

    def _exchange(self, request: dict[str, str | list[TextPassage]]) -> object:
        self._requests.write(json.dumps(request) + "\n")
        self._requests.flush()
        response = self._responses.readline()
        if not response:
            raise RuntimeError("Local embedding encoder stopped responding")
        return json.loads(response)

    def query(self, text: str) -> Vector:
        return cast(Vector, self._exchange({"query": text}))

    def passages(self, texts: list[TextPassage]) -> list[list[Vector]]:
        return cast(list[list[Vector]], self._exchange({"passages": texts}))


class DenseRanker:
    def __init__(self, encoder: Encoder) -> None:
        self._encoder = encoder
        self._passages: dict[UUID, list[array[float]]] = {}
        self._lock = Lock()

    def __call__(self, query: str, documents: Sequence[Document]) -> list[Document]:
        if not documents:
            return []
        # One pipe and one cache are shared by requests using this search store.
        with self._lock:
            missing = [doc for doc in documents if doc.id not in self._passages]
            if missing:
                vectors = self._encoder.passages(
                    [(d.title, d.content) for d in missing]
                )
                for doc, chunks in zip(missing, vectors, strict=True):
                    self._passages[doc.id] = [array("f", chunk) for chunk in chunks]
            q = self._encoder.query(query)
            scores = [
                max(
                    fsum(a * b for a, b in zip(q, chunk, strict=True))
                    for chunk in self._passages[doc.id]
                )
                for doc in documents
            ]
        ranked = sorted(zip(scores, documents, strict=True), key=lambda pair: -pair[0])
        return [doc for score, doc in ranked if score >= MIN_COSINE]
