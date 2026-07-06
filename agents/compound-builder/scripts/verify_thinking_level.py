#!/usr/bin/env python3
"""验证 thinking level 怎么控 —— 针对当前 ANTHROPIC_* / MiniMax 环境。

用法(在 agents/compound-builder 目录):

    uv run python scripts/verify_thinking_level.py
    uv run python scripts/verify_thinking_level.py --model MiniMax-M2.7-highspeed
    uv run python scripts/verify_thinking_level.py --raw-only

需要 shell 里已有 ANTHROPIC_API_KEY(或 AUTH_TOKEN) + ANTHROPIC_BASE_URL(若走 MiniMax)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 让 ``from compound_builder...`` 在源码树下可用
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from compound_builder.env import load_cli_env  # noqa: E402


@dataclass
class CaseResult:
    name: str
    ok: bool
    elapsed_s: float
    error: str | None = None
    stop_reason: str | None = None
    content_types: list[str] = field(default_factory=list)
    thinking_preview: str | None = None
    text_preview: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_snippet: str | None = None


def _api_key() -> str:
    return os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY") or ""


def _base_url() -> str:
    return (os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")


def _default_model() -> str:
    return (
        os.getenv("ATELIER_DEFAULT_MODEL")
        or os.getenv("ANTHROPIC_MODEL")
        or "MiniMax-M2.7-highspeed"
    )


def _preview(text: str | None, n: int = 120) -> str | None:
    if not text:
        return None
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _content_types(content: Any) -> list[str]:
    if isinstance(content, str):
        return ["text"]
    if not isinstance(content, list):
        return [type(content).__name__]
    out: list[str] = []
    for block in content:
        if isinstance(block, dict):
            out.append(str(block.get("type") or "dict"))
        else:
            out.append(getattr(block, "type", type(block).__name__))
    return out


def _extract_thinking_text(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "thinking":
                parts.append(str(block.get("thinking") or ""))
            elif block.get("type") == "text":
                text = str(block.get("text") or "")
                if "<thinking>" in text:
                    parts.append(text)
        else:
            btype = getattr(block, "type", "")
            if btype == "thinking":
                parts.append(str(getattr(block, "thinking", "") or ""))
    blob = "\n".join(p for p in parts if p.strip())
    return blob or None


def _extract_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "content", "") or getattr(block, "text", "")))
    return "\n".join(parts) if parts else None


def run_langchain_case(name: str, model: str, extra_kwargs: dict[str, Any]) -> CaseResult:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage

    t0 = time.perf_counter()
    try:
        llm = ChatAnthropic(
            model=model,
            api_key=_api_key(),
            base_url=_base_url() if os.getenv("ANTHROPIC_BASE_URL") else None,
            timeout=90,
            max_retries=1,
            streaming=False,
            disable_streaming=True,
            **extra_kwargs,
        )
        msg = llm.invoke([
            HumanMessage(content=(
                "Reply with exactly one word: the opposite of 'hot'. "
                "No explanation."
            )),
        ])
        elapsed = time.perf_counter() - t0
        content = msg.content
        usage = {}
        meta = getattr(msg, "usage_metadata", None) or getattr(msg, "response_metadata", {})
        if isinstance(meta, dict):
            usage = meta.get("usage") or meta
        return CaseResult(
            name=name,
            ok=True,
            elapsed_s=elapsed,
            content_types=_content_types(content),
            thinking_preview=_preview(_extract_thinking_text(content), 160),
            text_preview=_preview(_extract_text(content), 80),
            usage=dict(usage) if isinstance(usage, dict) else {},
        )
    except Exception as e:  # noqa: BLE001
        return CaseResult(
            name=name,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"{type(e).__name__}: {e}",
        )


def run_raw_messages_case(
    name: str,
    model: str,
    body_extra: dict[str, Any],
) -> CaseResult:
    """直连 Anthropic Messages API(MiniMax 兼容),可塞文档未走 LangChain 的字段。"""
    import urllib.error
    import urllib.request

    url = f"{_base_url()}/v1/messages"
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 256,
        "messages": [{
            "role": "user",
            "content": "Reply with exactly one word: the opposite of 'cold'. No explanation.",
        }],
        **body_extra,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "x-api-key": _api_key(),
        "anthropic-version": "2023-06-01",
    }
    if os.getenv("ANTHROPIC_AUTH_TOKEN"):
        headers["authorization"] = f"Bearer {_api_key()}"

    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        elapsed = time.perf_counter() - t0
        content = raw.get("content") or []
        return CaseResult(
            name=name,
            ok=True,
            elapsed_s=elapsed,
            stop_reason=str(raw.get("stop_reason") or ""),
            content_types=_content_types(content),
            thinking_preview=_preview(_extract_thinking_text(content), 160),
            text_preview=_preview(_extract_text(content), 80),
            usage=dict(raw.get("usage") or {}),
            raw_snippet=json.dumps(body_extra, ensure_ascii=False)[:200],
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return CaseResult(
            name=name,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"HTTP {e.code}: {body[:400]}",
            raw_snippet=json.dumps(body_extra, ensure_ascii=False)[:200],
        )
    except Exception as e:  # noqa: BLE001
        return CaseResult(
            name=name,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"{type(e).__name__}: {e}",
            raw_snippet=json.dumps(body_extra, ensure_ascii=False)[:200],
        )


def _print_result(r: CaseResult) -> None:
    status = "OK" if r.ok else "FAIL"
    print(f"\n[{status}] {r.name}  ({r.elapsed_s:.2f}s)")
    if r.error:
        print(f"  error: {r.error}")
    if r.raw_snippet:
        print(f"  payload: {r.raw_snippet}")
    if r.stop_reason:
        print(f"  stop_reason: {r.stop_reason}")
    if r.content_types:
        print(f"  content_types: {r.content_types}")
    if r.thinking_preview:
        print(f"  thinking: {r.thinking_preview}")
    if r.text_preview:
        print(f"  text: {r.text_preview!r}")
    if r.usage:
        print(f"  usage: {r.usage}")


def build_cases(model: str, *, raw_only: bool) -> list[tuple[str, Any]]:
    """返回 (name, runner_kind, kwargs) — runner 在 main 里分派。"""
    cases: list[tuple[str, str, dict[str, Any]]] = []

    if not raw_only:
        cases.extend([
            ("lc:baseline (no thinking)", "lc", {}),
            ("lc:thinking adaptive", "lc", {"thinking": {"type": "adaptive"}}),
            ("lc:thinking disabled", "lc", {"thinking": {"type": "disabled"}}),
            ("lc:thinking enabled budget=1024", "lc", {
                "thinking": {"type": "enabled", "budget_tokens": 1024},
            }),
            ("lc:output_config effort=low", "lc", {"output_config": {"effort": "low"}}),
            ("lc:output_config effort=medium", "lc", {"output_config": {"effort": "medium"}}),
            ("lc:output_config effort=high", "lc", {"output_config": {"effort": "high"}}),
            ("lc:adaptive + effort=high", "lc", {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"},
            }),
        ])

    # Raw HTTP — 试探 MiniMax 文档外字段
    cases.extend([
        ("raw:baseline", "raw", {}),
        ("raw:thinking adaptive", "raw", {"thinking": {"type": "adaptive"}}),
        ("raw:thinking disabled", "raw", {"thinking": {"type": "disabled"}}),
        ("raw:thinking enabled budget=2048", "raw", {
            "thinking": {"type": "enabled", "budget_tokens": 2048},
        }),
        ("raw:metadata reasoning_effort=low", "raw", {
            "metadata": {"reasoning_effort": "low"},
        }),
        ("raw:metadata reasoning_effort=high", "raw", {
            "metadata": {"reasoning_effort": "high"},
        }),
        ("raw:top-level reasoning.effort=low", "raw", {
            "reasoning": {"effort": "low"},
        }),
        ("raw:top-level reasoning.effort=high", "raw", {
            "reasoning": {"effort": "high"},
        }),
    ])
    return [(n, k, {**kw, "_model": model}) for n, k, kw in cases]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify thinking level control")
    parser.add_argument("--model", default=_default_model())
    parser.add_argument("--raw-only", action="store_true")
    parser.add_argument("--filter", default="", help="只跑名称含此子串的 case")
    args = parser.parse_args()

    load_cli_env()

    if not _api_key():
        print("ERROR: set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN", file=sys.stderr)
        return 1

    print("=== thinking level probe ===")
    print(f"model:     {args.model}")
    print(f"base_url:  {_base_url()}")
    print(f"filter:    {args.filter or '(none)'}")

    results: list[CaseResult] = []
    for name, kind, kw in build_cases(args.model, raw_only=args.raw_only):
        if args.filter and args.filter not in name:
            continue
        model = kw.pop("_model")
        if kind == "lc":
            r = run_langchain_case(name, model, kw)
        else:
            r = run_raw_messages_case(name, model, kw)
        results.append(r)
        _print_result(r)

    ok_n = sum(1 for r in results if r.ok)
    print("\n=== summary ===")
    print(f"passed: {ok_n}/{len(results)}")

    # 粗对比: 有 thinking block vs 无
    with_think = [r for r in results if r.ok and r.thinking_preview]
    without_think = [r for r in results if r.ok and not r.thinking_preview]
    if with_think:
        avg_t = sum(r.elapsed_s for r in with_think) / len(with_think)
        print(f"cases with visible thinking blocks: {len(with_think)}, avg {avg_t:.2f}s")
    if without_think:
        avg_t = sum(r.elapsed_s for r in without_think) / len(without_think)
        print(f"cases without visible thinking:   {len(without_think)}, avg {avg_t:.2f}s")

    print("\n解读:")
    print("- 若只有 adaptive/enabled 出现 thinking block → 控的是「是否暴露思考」,不是 low/high")
    print("- 若 effort/metadata/reasoning 报错或无效 → MiniMax Anthropic 路由可能不支持该字段")
    print("- 对比 elapsed_s / usage 看档位是否真影响耗时或 token")

    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
