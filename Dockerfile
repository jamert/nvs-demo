FROM python:3.15.2-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never
COPY .python-version pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable

CMD ["/app/.venv/bin/nevis-tiny-search", "serve", "--host", "0.0.0.0", "--port", "8000"]
