FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY ezrules ezrules

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app
