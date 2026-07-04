FROM python:3.11-slim

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先装依赖再装代码（更好的缓存）
COPY pyproject.toml ./
RUN uv pip install --system .

COPY src ./src
COPY tests ./tests
COPY langgraph.json ./
COPY .env.example ./.env.example

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:${PORT:-2024}/health || exit 1

EXPOSE 2024

CMD ["langgraph", "up", "--host", "0.0.0.0", "--port", "2024"]
