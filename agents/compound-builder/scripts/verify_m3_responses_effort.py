#!/usr/bin/env python3
"""验证 MiniMax-M3 + Responses API 的 reasoning.effort 是否可控。

与 Anthropic Messages 路由不同,Responses API 文档明确有 ``reasoning.effort``:
  none | minimal | low | medium | high

用法:

    cd agents/compound-builder
    uv run python scripts/verify_m3_responses_effort.py

环境变量:
  ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN  — Bearer
  MINIMAX_RESPONSES_BASE_URL (可选,默认从 ANTHROPIC_BASE_URL 推导)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from compound_builder.env import load_cli_env  # noqa: E402


@dataclass
class EffortResult:
    effort: str
    base_url: str
    ok: bool
    elapsed_s: float
    error: str | None = None
    has_reasoning_output: bool = False
    reasoning_preview: str | None = None
    output_text: str | None = None
    reasoning_tokens: int | None = None
    output_tokens: int | None = None
    status: str | None = None


def _api_key() -> str:
    return os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY") or ""


def _responses_bases() -> list[str]:
    explicit = (os.getenv("MINIMAX_RESPONSES_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return [explicit]

    anthropic = (os.getenv("ANTHROPIC_BASE_URL") or "").strip().rstrip("/")
    bases: list[str] = []
    if anthropic:
        # https://api.minimaxi.com/anthropic → https://api.minimaxi.com
        root = anthropic.replace("/anthropic", "").rstrip("/")
        if root:
            bases.append(root)
    # 文档默认域
    for b in ("https://api.minimaxi.com", "https://api.minimax.io"):
        if b not in bases:
            bases.append(b)
    return bases


def _preview(text: str | None, n: int = 140) -> str | None:
    if not text:
        return None
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _extract_reasoning(output: list[Any]) -> tuple[bool, str | None]:
    parts: list[str] = []
    for item in output or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "reasoning":
            continue
        for seg in item.get("reasoning") or []:
            if isinstance(seg, dict) and seg.get("text"):
                parts.append(str(seg["text"]))
            elif isinstance(seg, dict) and seg.get("type") == "reasoning_text":
                parts.append(str(seg.get("text") or ""))
    blob = "\n".join(p for p in parts if p.strip())
    return bool(blob.strip()), blob or None


def call_responses(
    base: str,
    effort: str | None,
    *,
    model: str,
) -> EffortResult:
    url = f"{base.rstrip('/')}/v1/responses"
    payload: dict[str, Any] = {
        "model": model,
        "input": "Reply with exactly one word: the opposite of 'hot'. No explanation.",
        "max_output_tokens": 512,
    }
    label = "omitted"
    if effort is not None:
        label = effort
        payload["reasoning"] = {"effort": effort}

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {_api_key()}",
    }

    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        elapsed = time.perf_counter() - t0

        output = raw.get("output") or []
        has_r, r_text = _extract_reasoning(output)
        usage = raw.get("usage") or {}
        out_details = usage.get("output_tokens_details") or {}
        r_tok = out_details.get("reasoning_tokens")
        if r_tok is None and isinstance(usage.get("reasoning_tokens"), int):
            r_tok = usage["reasoning_tokens"]

        return EffortResult(
            effort=label,
            base_url=base,
            ok=True,
            elapsed_s=elapsed,
            has_reasoning_output=has_r,
            reasoning_preview=_preview(r_text),
            output_text=_preview(raw.get("output_text") or ""),
            reasoning_tokens=int(r_tok) if r_tok is not None else None,
            output_tokens=int(usage.get("output_tokens") or 0) or None,
            status=str(raw.get("status") or ""),
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return EffortResult(
            effort=label,
            base_url=base,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"HTTP {e.code}: {body[:500]}",
        )
    except Exception as e:  # noqa: BLE001
        return EffortResult(
            effort=label,
            base_url=base,
            ok=False,
            elapsed_s=time.perf_counter() - t0,
            error=f"{type(e).__name__}: {e}",
        )


def _print(r: EffortResult) -> None:
    tag = "OK" if r.ok else "FAIL"
    print(f"\n[{tag}] effort={r.effort!r}  base={r.base_url}  ({r.elapsed_s:.2f}s)")
    if r.error:
        print(f"  error: {r.error}")
        return
    print(f"  status: {r.status}")
    print(f"  reasoning_output: {r.has_reasoning_output}")
    if r.reasoning_preview:
        print(f"  reasoning: {r.reasoning_preview}")
    if r.output_text:
        print(f"  text: {r.output_text!r}")
    print(
        f"  tokens: output={r.output_tokens} reasoning={r.reasoning_tokens}"
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Probe MiniMax-M3 Responses reasoning.effort")
    parser.add_argument("--model", default=os.getenv("ATELIER_M3_MODEL", "MiniMax-M3"))
    parser.add_argument(
        "--efforts",
        default="omitted,none,minimal,low,medium,high",
        help="comma-separated; use 'omitted' for no reasoning field",
    )
    args = parser.parse_args()
    load_cli_env()

    if not _api_key():
        print("ERROR: set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN", file=sys.stderr)
        return 1

    efforts: list[str | None] = []
    for e in args.efforts.split(","):
        e = e.strip()
        if e == "omitted":
            efforts.append(None)
        else:
            efforts.append(e)

    bases = _responses_bases()
    print("=== MiniMax M3 Responses API — reasoning.effort probe ===")
    print(f"model:  {args.model}")
    print(f"bases:  {bases}")
    print(f"efforts: {[x if x is not None else 'omitted' for x in efforts]}")

    results: list[EffortResult] = []
    working_base: str | None = None

    for base in bases:
        print(f"\n--- trying base {base} ---")
        probe = call_responses(base, None, model=args.model)
        _print(probe)
        if probe.ok:
            working_base = base
            results.append(probe)
            break
        results.append(probe)

    if not working_base:
        print("\n=== no working Responses base URL ===")
        print("Tried:", bases)
        print("Set MINIMAX_RESPONSES_BASE_URL if your tenant uses a custom host.")
        return 1

    for effort in efforts[1:]:  # first already ran as omitted
        r = call_responses(working_base, effort, model=args.model)
        results.append(r)
        _print(r)

    ok = [r for r in results if r.ok]
    print("\n=== summary ===")
    print(f"working base: {working_base}")
    print(f"passed: {len(ok)}/{len(results)}")

    if ok:
        print("\n| effort | reasoning_out | reasoning_tok | output_tok | time(s) |")
        print("|--------|-----------------|---------------|------------|---------|")
        for r in ok:
            print(
                f"| {r.effort!s:7} | {str(r.has_reasoning_output):15} | "
                f"{str(r.reasoning_tokens):13} | {str(r.output_tokens):10} | "
                f"{r.elapsed_s:6.2f} |"
            )

    # 判断 effort 是否「真控深度」
    by_effort = {r.effort: r for r in ok}
    none_like = by_effort.get("none") or by_effort.get("omitted")
    high = by_effort.get("high")
    print("\n=== interpretation ===")
    if none_like and high:
        if none_like.has_reasoning_output and high.has_reasoning_output:
            if (
                none_like.reasoning_tokens == high.reasoning_tokens
                and abs(none_like.elapsed_s - high.elapsed_s) < 0.15
            ):
                print(
                    "- none vs high: 同样有/无 reasoning, token/耗时几乎一样 "
                    "→ effort 可能只控「是否输出 reasoning」,不控深度(符合 MiniMax 文档)"
                )
            else:
                print(
                    "- none vs high: reasoning_tokens 或耗时明显不同 "
                    "→ effort 可能有实际影响(需多跑几次确认)"
                )
        elif not none_like.has_reasoning_output and high.has_reasoning_output:
            print("- none 无 reasoning 输出, high 有 → effort 可开关 reasoning 暴露")
        else:
            print("- 对比不明显,建议多跑几次或换更复杂 prompt")
    print(
        "- 文档说明: M3 上 minimal/low/medium/high 启用 reasoning 输出,"
        "但不一定调深度; M2.x 无法关闭 reasoning"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
