# {{ cookiecutter.agent_pascal }} — README

> {{ cookiecutter.agent_description }}

## 启动

```bash
cd agents/{{ cookiecutter.agent_slug }}
uv sync
cp .env.example .env  # 填好 ANTHROPIC_API_KEY / LANGSMITH_API_KEY
make dev              # LangGraph Studio: http://localhost:2024
```

或者命令行：

```bash
python -m {{ cookiecutter.agent_slug }}.cli run "实现某个功能"
```

## 子代理

| 名字 | 职责 |
|------|------|
| `researcher` | 仓库 / 文档调研 |
| `tester`     | 写并跑测试 |
| `reviewer`   | 审 diff |

## 工具

- `bash`（受限 + 人工批准）
- `read_file` / `write_file` / `edit_file`
- `git_status` / `git_diff` / `git_commit`（注意：**不暴露 git_push**）

## 测试

```bash
make test
TEST=tests/unit/test_tools.py make test
```

## 部署

```bash
make build          # 构建 atelier/{{ cookiecutter.agent_slug }} 镜像
make up             # 启动服务
```

## 文档

- `docs/PROMPT.md` —— 提示词运维手册
- `docs/EVAL.md` —— LangSmith 评测（待补）
