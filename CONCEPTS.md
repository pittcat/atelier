# Concepts

> Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Atelier domain

### Agent

A self-contained runnable unit in this monorepo. An Agent is its own Python package under `agents/<slug>/`, with its own `pyproject.toml`, `Makefile`, `langgraph.json`, `AGENTS.md`, `docs/`, and `tests/`. Each Agent has a slug (kebab-case, e.g. `code-writer`), a Pascal-case display name, and an entry-point module (`src/<slug>/agent.py`) that constructs a LangGraph graph via `create_deep_agent(...)`. Cross-agent coordination goes through the gateway HTTP API, never through direct imports. Avoid: assistant, service, worker.

A code-writing Agent (slug `code-writer`) is the reference implementation; it owns its own sub-agents (researcher / tester / reviewer), its own tools (read/write/edit_file, bash, git_status/diff/commit), and its own prompt / interrupt map / checkpointer configuration. Lifecycle: requirements → cookiecutter scaffold → tools + subagents → make format && make lint && make test → langgraph dev → gateway router → langgraph up.

### SubAgent

A subordinate agent declared in `subagents.py` of an Agent. SubAgents are not standalone Agents — they cannot import or reference each other, have a single responsibility, and are limited to ≤5 tools. Depth in the Agent → SubAgent hierarchy is capped at 2 (an Agent's SubAgents cannot themselves spawn further SubAgents).

### LangGraph Studio

The in-browser development UI for testing an Agent. Runs locally on port 2024 via `langgraph dev`; serves an OpenAPI at `/docs` and a Studio frontend at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`. Studio runs the Agent in a separate venv from the user-installed one — environment variables and Python packages available inside Studio may differ from those seen by `python -m <agent>.cli run`. Code that works in Studio may still fail at the CLI, and vice versa.

### Checkpointer

The persistence layer that lets an Agent resume state across invocations (memory across conversations). Default is in-memory; production uses PostgresSaver. `ATELIER_CHECKPOINTER_URL` toggles between them. Note: when running inside LangGraph Studio / langgraph-api, the platform owns persistence and the user-supplied checkpointer is rejected (langgraph-api raises `ValueError: includes a custom checkpointer`).

### Prompt Caching (Anthropic feature)

The Anthropic Messages API feature where stable system prompts and tool definitions are tagged with `cache_control: {type: ephemeral, ttl: 5m}` so repeated prefixes hit a server-side cache. Anthropic-protocol-compatible third-party providers (such as MiniMax at `api.minimaxi.com/anthropic`) may reject this field with HTTP 502. deepagents 0.6 installs `AnthropicPromptCachingMiddleware` unconditionally, so when targeting an Anthropic-compat backend the `wrap_model_call` must be noop-wrapped before the Agent module is imported. Avoid: cache_control is a field name, not a concept.

## Provider / proxy layer

### Anthropic-Protocol-Compatible Provider

A third-party LLM service that speaks the Anthropic Messages wire format (not OpenAI ChatCompletions). MiniMax is the reference example: same `POST /v1/messages` shape, same `x-api-key` header, but with its own model catalog and its own acceptance rules for Anthropic-only fields (`cache_control`, beta headers). Routers like CC Switch on macOS distinguish providers by URL path (`.../anthropic` vs `.../v1`) and route requests to different upstream configurations accordingly.

## Operational concepts

### Shell Env Residue

The phenomenon where a shell session (zsh / bash) carries `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`, `HTTPS_PROXY` and similar variables from prior sessions or from `~/.zshrc`, causing a process that loads `.env` (even with `override=True`) to behave as if the file did not exist when the shell value was already set by an unrelated tool. Mitigation: log the active base URL on Agent startup so the discrepancy is visible immediately.

## Flagged ambiguities

- "Agent" had been used for both the Claude Agent SDK concept and the Atelier-per-package concept; these are distinct. The Atelier Agent is a self-contained runnable package; the Claude Agent SDK is the underlying harness.