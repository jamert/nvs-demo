FROM python:3.15.2-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

FROM base AS embeddings
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl perl \
    && rm -rf /var/lib/apt/lists/*
ENV NEVIS_EMBEDDINGS_HOME=/opt/nevis-e5 \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python
COPY experiments/embeddings/ /build/embeddings/
# The runtime image does not include the helper's source checkout.
RUN UV_NO_EDITABLE=1 sh /build/embeddings/setup.sh

FROM base
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    NEVIS_EMBEDDINGS_HOME=/opt/nevis-e5
COPY --from=embeddings /opt/uv-python /opt/uv-python
COPY --from=embeddings /opt/nevis-e5 /opt/nevis-e5
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable

CMD ["/app/.venv/bin/nevis-tiny-search", "serve", "--host", "0.0.0.0", "--port", "8000"]
