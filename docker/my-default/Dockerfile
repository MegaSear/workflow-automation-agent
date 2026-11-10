FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
	&& apt-get install -y --no-install-recommends docker-cli \
	&& rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src

EXPOSE 8001

CMD ["uv", "run", "--no-sync", "uvicorn", "react_agent.my_default.server:app", "--host", "0.0.0.0", "--port", "8001"]