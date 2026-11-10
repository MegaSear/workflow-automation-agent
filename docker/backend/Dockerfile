FROM docker:cli AS docker_cli

FROM python:3.12-slim

COPY --from=docker_cli /usr/local/bin/docker /usr/local/bin/docker

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Устанавливаем uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Сначала копируем только файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости из lock-файла
RUN uv sync --frozen --no-dev --no-install-project

# Затем исходный код
COPY src ./src
COPY config ./config

# Устанавливаем сам проект
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "react_agent.backend.api.server:app", "--host", "0.0.0.0", "--port", "8000"]