#!/bin/sh
# Install the local ONNX helper and verified model artifacts outside git.
set -eu
project=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
home=${NEVIS_EMBEDDINGS_HOME:-"$HOME/.cache/nevis-search/dense-e5"}
mkdir -p -- "$home/model"
home=$(CDPATH='' cd -- "$home" && pwd)
model=https://huggingface.co/intfloat/e5-small-v2/resolve/ffb93f3bd4047442299a41ebb6fa998a38507c52

verify() {
    printf '%s  %s\n' "$2" "$1" | shasum -a 256 -c -
}

fetch() (
    file=$1
    digest=$2
    target="$home/model/$file"
    if [ -f "$target" ] && verify "$target" "$digest"; then
        exit 0
    fi
    tmp=$(mktemp "$target.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    curl --fail --location --silent --show-error --retry 2 "$model/$file" -o "$tmp"
    verify "$tmp" "$digest"
    mv -f -- "$tmp" "$target"
)

fetch model.onnx 4b8205be2a3c5fc53c6534d76a2012064f7309c162b806f2889c6ec8ec4fdcba
fetch tokenizer.json d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66
UV_PROJECT_ENVIRONMENT="$home/helper" uv sync --project "$project" --locked --python 3.12.14
