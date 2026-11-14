FROM python:3.12-slim

WORKDIR /app

COPY src/react_agent/my_default/docker_proxy.py /app/docker_proxy.py
COPY src/react_agent/my_default/sandbox_commands.py /app/react_agent/my_default/sandbox_commands.py

ENV PYTHONPATH=/app
EXPOSE 2375

CMD ["python", "/app/docker_proxy.py"]