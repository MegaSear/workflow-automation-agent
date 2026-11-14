# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends docker-cli \
	&& rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY config ./config

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
	
ENV PYTHONPATH=/app/src

EXPOSE 8001

CMD ["uv", "run", "--no-sync", "uvicorn", "react_agent.my_default.server:app", "--host", "0.0.0.0", "--port", "8001"]