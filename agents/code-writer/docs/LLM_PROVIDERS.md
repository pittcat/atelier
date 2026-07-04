# LLM Providers —— 在 Atelier Agent 接入各种 LLM 服务

atelier 默认走 **Anthropic Messages API**（用 `langchain-anthropic`）。
本文档列三种典型接法，**改 `.env` 即可，代码不动**。

---

## A. 官方 Anthropic（默认）

```bash
ANTHROPIC_API_KEY=sk-ant-...
ATELIER_DEFAULT_MODEL=claude-opus-4-8
ATELIER_SUBAGENT_MODEL=claude-haiku-4-5-20251001
```

`llm.py` 自动读 `ANTHROPIC_API_KEY`，走 https://api.anthropic.com。

---

## B. Minimax 等 Anthropic 兼容三方（推荐：零代码改动）

```bash
ANTHROPIC_API_KEY=<your-minimax-key>
ANTHROPIC_BASE_URL=https://api.minimaxi.com/v1

# 可选：部分三方用 ANTHROPIC_AUTH_TOKEN 当 token 别名
# ANTHROPIC_AUTH_TOKEN=<your-key>

# 可选：自定义 header（逗号分隔 K:V 对）
# ANTHROPIC_CUSTOM_HEADER=X-Source:atelier,X-Trace:on

# 模型名按 Minimax 给出的列表填；可以填任意兼容的：
ATELIER_DEFAULT_MODEL=claude-opus-4-8
ATELIER_SUBAGENT_MODEL=claude-haiku-4-5-20251001
```

`llm.py:get_llm()` 会自动：

1. 读 `ANTHROPIC_API_KEY`（或 `ANTHROPIC_AUTH_TOKEN`）；
2. 读 `ANTHROPIC_BASE_URL`，覆盖默认 endpoint；
3. 解析 `ANTHROPIC_CUSTOM_HEADER`，注入 `default_headers`。

### 验证

```bash
cd agents/code-writer
.venv/bin/python -c "
import os
os.environ['ANTHROPIC_BASE_URL']='https://api.minimaxi.com/v1'
os.environ['ANTHROPIC_API_KEY']='test-key'
from code_writer.llm import get_llm
m = get_llm('claude-opus-4-8')
print('OK base_url=', m.anthropic_api_url if hasattr(m,'anthropic_api_url') else m.client.base_url)
"
```

通的话会打印一个 Anthropic 风格 base URL。

---

## C. OpenAI 兼容格式（含原生 OpenAI）

适用于"必须走 OpenAI ChatCompletions 协议"的服务。

代码侧：在 `src/code_writer/llm.py` 里加一个 `if os.getenv("ATELIER_LLM_PROVIDER")=="openai":` 分支：

```python
from langchain_openai import ChatOpenAI
return ChatOpenAI(
    model=model_name,
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),  # 可选，覆盖 endpoint
)
```

并在 `pyproject.toml` 加 `langchain-openai>=0.2`。

> 如果团队同时混用 Anthropic 与 OpenAI，**推荐**：每个 Agent 目录单独一个
> `llm.py`；通过 `ATELIER_LLM_PROVIDER=anthropic|openai` 切换 provider，不要
> 在 `libs/common` 里搞多态。

---

## D. 排查清单

| 现象 | 检查 |
|------|------|
| 启动立刻 `RuntimeError: langchain_anthropic not installed` | `uv pip install langchain-anthropic` |
| `401 Unauthorized` | key 是否对、是否带前缀（如 Minimax 要 own prefix） |
| `404 Not Found` | base_url 是否去掉 `/v1`、`/anthropic` 等多余后缀 |
| `model not found` | model 名是否在 Minimax 白名单里 |
| Timeout | 加 `ATELIER_LLM_TIMEOUT=180`；修改 llm.py 里 `timeout=` 默认值 |

---

## E. 参考

- [LangChain ChatAnthropic 文档](https://python.langchain.com/docs/integrations/chat/anthropic)
- [LangSmith Tracing 环境变量](https://docs.smith.langchain.com/)
