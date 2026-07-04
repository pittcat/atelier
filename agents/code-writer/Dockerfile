FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
RUN uv pip install --system .

COPY src ./src
COPY langgraph.json ./
COPY .env.example ./.env.example

EXPOSE 2024
CMD ["langgraph", "up", "--host", "0.0.0.0", "--port", "2024"]
