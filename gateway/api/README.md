"""本 Gateway 的最小 README。"""

# Atelier Gateway

统一的对外 FastAPI 网关。每个 Agent 在这里暴露 / 新建 thread / 流式 / 中断恢复。

## 启

```bash
cd gateway/api
GATEWAY_AUTH_TOKEN=$(openssl rand -hex 32) \
LANGSMITH_TRACING=true \
uvicorn main:app --reload --port 8080
```

## 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | /agents                                    | 列出全部 Agent |
| GET    | /agents/{slug}/threads/{tid}/state         | 读当前状态 |
| GET    | /agents/{slug}/threads/{tid}/history       | 读全部状态历史（回放） |
| POST   | /agents/{slug}/threads/{tid}/runs          | 同步 invoke |
| POST   | /agents/{slug}/threads/{tid}/runs:stream   | SSE 流式 |

## 鉴权

`Authorization: Bearer <GATEWAY_AUTH_TOKEN>`。
开发可省略；生产必带。

## 加新 Agent

1. 在 `registry.py` 加一个 slug 条目
2. 在 `routers/<slug>.py` 加一个 router
3. 在 `routers/__init__.py` 的 `ALL_ROUTERS` 里注册
