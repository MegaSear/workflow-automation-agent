FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* 

RUN useradd --create-home --uid 10001 runner

USER runner
WORKDIR /workspace

RUN git init
RUN echo "Hello, World!" > /workspace/hello.txt

CMD ["git", "status", "--short"]
