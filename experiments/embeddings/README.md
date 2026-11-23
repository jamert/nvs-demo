# Local E5 inference helper

From the repository root, install the verified model and the locked Python
3.12.14 helper environment (ONNX Runtime 1.22.0, NumPy 2.2.6, tokenizers 0.21.1):

```sh
sh experiments/embeddings/setup.sh
```

This requires `uv`, `curl`, `shasum`, an internet connection for setup, and a
platform with ONNX Runtime wheels (tested on macOS arm64). The default cache is
`~/.cache/nevis-search/dense-e5`; set `NEVIS_EMBEDDINGS_HOME` to an absolute path
before both setup and use to change it. The application keeps its separate
Python 3.15 environment. No downloads happen during inference, tests, or commits.
The server sends query and document text only to the local helper over pipes.

The MIT-licensed [intfloat/e5-small-v2 model](https://huggingface.co/intfloat/e5-small-v2)
is pinned to [revision `ffb93f3bd4047442299a41ebb6fa998a38507c52`](https://huggingface.co/intfloat/e5-small-v2/tree/ffb93f3bd4047442299a41ebb6fa998a38507c52).
The setup script and helper both check SHA-256:

| Artifact | SHA-256 |
|---|---|
| `model.onnx` | `4b8205be2a3c5fc53c6534d76a2012064f7309c162b806f2889c6ec8ec4fdcba` |
| `tokenizer.json` | `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66` |

See the [Dense E5 report](../../doc/search/dense-e5.md) for search behavior,
evaluation, and server commands.
