import json
import os
import sys
from hashlib import file_digest
from pathlib import Path

import numpy as np
from onnxruntime import InferenceSession, SessionOptions
from tokenizers import Tokenizer

ARTIFACTS = {
    "model.onnx": "4b8205be2a3c5fc53c6534d76a2012064f7309c162b806f2889c6ec8ec4fdcba",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
}
TOKEN_LIMIT = 256
PASSAGE_HEADER_LIMIT = 32
BODY_OVERLAP = 32


class E5Encoder:
    def __init__(self, model_dir: Path) -> None:
        for filename, expected in ARTIFACTS.items():
            with (model_dir / filename).open("rb") as artifact:
                if file_digest(artifact, "sha256").hexdigest() != expected:
                    raise ValueError(f"SHA-256 mismatch for {filename}")
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.cls = self.tokenizer.token_to_id("[CLS]")
        self.sep = self.tokenizer.token_to_id("[SEP]")
        options = SessionOptions()
        options.intra_op_num_threads = 2
        self.session = InferenceSession(
            str(model_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def _tokens(self, text: str) -> list[int]:
        return self.tokenizer.encode(text, add_special_tokens=False).ids

    def _pool(self, tokens: list[int]) -> list[float]:
        # Each unpadded window has an all-ones attention mask. Use the mean over
        # the last hidden state, as in the E5 model card, then L2-normalize.
        ids = np.array([[self.cls, *tokens, self.sep]], dtype=np.int64)
        (hidden,) = self.session.run(
            ["last_hidden_state"],
            {
                "input_ids": ids,
                "attention_mask": np.ones_like(ids),
                "token_type_ids": np.zeros_like(ids),
            },
        )
        pooled = hidden.mean(axis=1)[0]
        return (pooled / np.linalg.norm(pooled)).tolist()

    def query(self, text: str) -> list[float]:
        return self._pool(self._tokens(f"query: {text}")[: TOKEN_LIMIT - 2])

    def passage(self, title: str, content: str) -> list[list[float]]:
        header = self._tokens(f"passage: {title}")[:PASSAGE_HEADER_LIMIT]
        body = self._tokens(content)
        width = TOKEN_LIMIT - 2 - len(header)
        windows = []
        for start in range(0, max(1, len(body)), width - BODY_OVERLAP):
            windows.append(self._pool(header + body[start : start + width]))
            if start + width >= len(body):
                break
        return windows


def main() -> None:
    encoder = E5Encoder(Path(os.environ["NEVIS_EMBEDDINGS_MODEL_DIR"]))
    print("ready", flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if "query" in request:
            response = encoder.query(request["query"])
        else:
            response = [
                encoder.passage(title, content)
                for title, content in request["passages"]
            ]
        print(json.dumps(response, allow_nan=False), flush=True)
