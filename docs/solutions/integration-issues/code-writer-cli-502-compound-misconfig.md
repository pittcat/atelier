---
title: code_writer.cli run returns HTTP 502 due to compound env-path, middleware, and dependency misconfig
date: 2026-07-04
category: docs/solutions/integration-issues/
module: agents/code-writer
problem_type: integration_issue
component: development_workflow
symptoms:
  - "`code_writer.cli run \"...\"` raises openai.InternalServerError 502 or anthropic.InternalServerError 502 on every invocation"
  - "Switching between OpenAI ChatCompletions and Anthropic Messages protocols does not affect the failure"
  - "Toggling streaming=False, removing betas=[], killing CC Switch proxy, or switching virtualenvs all leave the failure unchanged"
  - "Shell pre-existing ANTHROPIC_BASE_URL=http://127.0.0.1:15721 survives because load_dotenv is pointed at a non-existent agents/.env and silently no-ops"
  - "Every deepagents-routed model call injects cache_control: {type: ephemeral, ttl: 5m}, which the MiniMax backend at api.minimaxi.com/anthropic rejects"
root_cause: config_error
resolution_type: code_fix
severity: high
tags:
  - atelier
  - code-writer
  - cli
  - dotenv
  - env-loading
  - deepagents
  - anthropic-cache-control
  - minimax
  - 502
---

# code_writer.cli run returns HTTP 502 due to compound env-path, middleware, and dependency misconfig

## Problem

`code_writer.cli run "..."` in `agents/code-writer/` returns HTTP 502 on every LLM
call. `langgraph dev` (Studio) works fine on the same code path; only the CLI
entry-point fails. Three independent misconfigurations must be fixed together;
any one left unaddressed keeps the 502 alive.

## Symptoms

- `code_writer.cli run "<prompt>"` crashes on first model invocation with
  `httpx.HTTPStatusError: Server error '502 Bad Gateway'` (or the SDK-rewrapped
  equivalent, depending on protocol used). Both `openai.InternalServerError`
  and `anthropic.InternalServerError` flavors were observed.
- SDK debug logs show the request targeting `host: 127.0.0.1 port: 15721`,
  but no LLM proxy is listening there — connection is RST immediately.
- The `.env` file explicitly sets `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic`,
  yet that value is not loaded; runtime base URL stays at the shell's stale
  `http://127.0.0.1:15721`.
- `langgraph dev` (Studio) completes the full conversation. Only
  `python -m code_writer.cli run` fails — the two paths load dotenv differently
  because they live in different working directories.
- `echo $ANTHROPIC_BASE_URL` in the user's shell returns the stale 15721
  value, not the `.env.example` suggestion.

## What Didn't Work

- **Switching OpenAI ChatCompletions protocol**: Replacing `ChatAnthropic` with
  `ChatOpenAI` only delayed the symptom; the URL was already wrong, so the
  502 came from the dead proxy regardless of protocol.
- **Toggling streaming parameters**: `streaming=False` / `disable_streaming=True`
  had no effect because the 502 came from upstream unavailability, not from
  SDK streaming parsing.
- **Killing CC Switch**: User explicitly forbade this. CC Switch is healthy on
  the Studio path; killing it would have broken Studio too.
- **Removing the empty `betas=[]` kwarg from ChatAnthropic**: At the time the
  protocol had already been switched to OpenAI, so this Anthropic field was
  never in the request body; the change was noise.
- **Installing `langchain-openai` + rewriting `llm.py`**: Equivalent to the
  protocol switch above. Changes "which upstream rejects" without addressing
  "why is the URL wrong".
- **Temporary `NO_PROXY=127.0.0.1` workaround around 15721**: Did not fix the
  dotenv loading path; regression on every shell restart. Treat-the-symptom,
  not the cause.
- **Patching `ChatOpenAI.__init__` to default `streaming=False`**: The patch
  applied AFTER `build_agent()` had already instantiated the model during
  import. Module-level `build_agent()` runs synchronously on
  `from code_writer.agent import agent`, so any patch placed after that
  import is a no-op.

## Solution

Three independent fixes plus one protocol alignment, applied together.

### A. `agents/code-writer/src/code_writer/cli.py` — dotenv path correction

The off-by-one makes `load_dotenv` resolve to a non-existent path; the shell's
stale `ANTHROPIC_BASE_URL` survives. Add a startup log so future drift is visible.

```python
# before
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env", override=True)

# after
_ROOT = Path(__file__).resolve().parents[2]
_dotenv_path = _ROOT / ".env"
load_dotenv(_dotenv_path, override=True)
assert _dotenv_path.is_file(), f".env not found at {_dotenv_path}"
import os as _os
print(f"[cli] ANTHROPIC_BASE_URL={_os.environ.get('ANTHROPIC_BASE_URL')!r}", file=sys.stderr)
```

### B. `cli.py` — noop `AnthropicPromptCachingMiddleware` before agent import

deepagents 0.6's `graph.py:261` installs `AnthropicPromptCachingMiddleware`.
Its `_apply_caching` tags the model request with
`cache_control: {type: ephemeral, ttl: 5m}` regardless of
`unsupported_model_behavior`. The `ChatAnthropic._create` writes this into
the JSON body. The MiniMax backend at `api.minimaxi.com/anthropic` rejects
the request with HTTP 502.

```python
# Patch must run BEFORE `from code_writer.agent import agent` so the override
# takes effect when deepagents assembles the middleware chain during import.
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

def _noop_wrap_model_call(self, request, handler):
    return handler(request)

AnthropicPromptCachingMiddleware.wrap_model_call = _noop_wrap_model_call
```

### C. `agents/code-writer/pyproject.toml` — declare `deepagents`

```toml
dependencies = [
    "atelier-common>=0.1.0",
    "langgraph>=0.2",
    "deepagents>=0.2",  # ← add this
    "langchain-core>=0.3",
    ...
]
```

The original pyproject comment ("deepagents is not on PyPI") was outdated;
0.6.12 has been published since early 2026. Without this dependency,
`langchain_anthropic.middleware.AnthropicPromptCachingMiddleware` (imported
by deepagents' graph factory) raises `ImportError`, masking root cause #B
as a missing-package crash instead of a 502.

### D. `agents/code-writer/.env` — align protocol with CC Switch active provider

```dotenv
ANTHROPIC_AUTH_TOKEN=<MiniMax key>
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ATELIER_DEFAULT_MODEL=MiniMax-M3
```

The Anthropic Messages endpoint matches the user's active CC Switch provider
configuration and is what `llm.py:get_llm()` (after fix A actually loads
`.env`) sends to.

## Why This Works

The three failures stack into the same single request:

1. **Path off-by-one**: `cli.py` resolves `.env` to `agents/.env` (nonexistent),
   so `load_dotenv(override=True)` silently no-ops. Shell residue
   `ANTHROPIC_BASE_URL=http://127.0.0.1:15721` wins; requests target a dead
   local proxy → 502.
2. **`cache_control` injection**: `AnthropicPromptCachingMiddleware` (in
   deepagents 0.6) tags every model request with Anthropic-only
   `cache_control`. MiniMax (Anthropic-protocol-compatible but rejecting
   `cache_control`) returns 502 server-side.
3. **Missing dep**: Without `deepagents>=0.2`, the middleware import fails,
   so the symptom shifts from "real 502" to "ImportError on startup",
   hiding cause #2 from diagnosis.

Fix A makes dotenv actually load, fix D aligns the URL with the active CC Switch
provider, fix C makes the cache-control middleware importable, fix B prevents
it from injecting the rejected field. All three (or all four) are required:
any one alone leaves at least one of the failure modes intact.

## Prevention

- **`__file__`-relative paths are fragile**: `parents[N]` looks precise but
  silently breaks when the package layout shifts (agent-template upgrade,
  directory layer count change). Always assert
  `assert (_ROOT / ".env").is_file()` after `load_dotenv`, and log the
  resolved root path on startup. Fail loud, not silent.
- **Log the active base URL on startup**: Shell environment residue is the
  most common cause of "I changed `.env` but the SDK still uses the old URL".
  One `stderr` line printing `ANTHROPIC_BASE_URL` makes drift obvious.
- **Audit `AnthropicPromptCachingMiddleware` for Anthropic-protocol-compatible backends**:
  `unsupported_model_behavior="ignore"` is honored by some hooks but deepagents
  0.6 currently does not pass that through; do both — set the flag AND
  noop-wrap `wrap_model_call` if your backend rejects `cache_control`.
- **CLI patches must run before the agent module is imported**: `build_agent()`
  instantiates the model during import. Every patch, default-setting, or
  environment override that affects model construction belongs in a "preamble"
  block at the top of `cli.py` (or whichever entry-point file imports the
  agent), strictly before `from <pkg>.agent import agent`.
- **Trust `pip index versions` over handwritten "not on PyPI" comments**:
  Dependency lists should be tool-generated (`uv lock --check`,
  `pip check` in CI) so a stale comment can't mask a missing dependency.

## Related Issues

- `agents/code-writer/docs/LLM_PROVIDERS.md` — partial overlap (score 5/5).
  Its §D troubleshooting table lists `401 / 404 / model not found / Timeout
  / langchain_anthropic not installed` but is **missing the
  `cache_control → 502` failure mode**. A future refresh should add a row:
  `502 with Anthropic-protocol-compatible provider → likely
  AnthropicPromptCachingMiddleware injecting cache_control; noop-wrap
  wrap_model_call per this doc`.
- `agents/code-writer/AGENTS.md` — project-level hard rules (push, prompts,
  interrupt, cross-agent import). Unaffected by this fix, but `cli.py` path
  change is breaking for any downstream automation and warrants a changelog
  entry.
- `agents/code-writer/.env.example` — the protocol alignment in fix D
  should be mirrored here so the next `cp .env.example .env` does not
  re-introduce the wrong protocol.
- `agents/code-writer/docs/PROMPT.md` v0.1.1 change log entry notes
  `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` support in `llm.py` but
  does not mention the cache_control middleware patch or the dotenv path bug.
  A v0.1.2 entry should link here.
- **Observation worth flagging**: `langgraph dev` worked before the fix
  because `langgraph-cli` ships its own venv without `langchain-anthropic`
  installed, so `AnthropicPromptCachingMiddleware` never instantiated and
  `cache_control` never entered the request body. Studio being green was
  *masking* the bug, not bypassing it. Any validation flow that relies
  exclusively on Studio will miss this class of issue.