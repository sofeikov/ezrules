FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY alembic alembic
COPY ezrules ezrules

RUN uv sync --frozen --no-dev

# Container commands use `uv run`; keep it on the frozen production environment
# instead of re-syncing (and downloading) the default dev dependency group.
ENV UV_NO_SYNC=1 \
    UV_NO_DEV=1

ENV PYTHONPATH=/app
