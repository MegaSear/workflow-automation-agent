FROM docker:cli AS docker_cli

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "react_agent.backend.api.server:app", "--host", "0.0.0.0", "--port", "8000"]