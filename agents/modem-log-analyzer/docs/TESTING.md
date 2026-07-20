# ModemLogAnalyzer —— 测试与开发流程

> TDD Red→Green→Refactor 闭环 + 测试分层 + 风险驱动测试。

## 1. 测试分层

```
tests/
├── unit/              # 单个模块/函数的纯逻辑测试
│   ├── test_contracts.py
│   ├── test_tool_registry.py
│   ├── test_skills_loader.py
│   ├── test_log_parser.py
│   ├── test_command_catalog.py
│   ├── test_intake.py
│   ├── test_classification.py
│   ├── test_control_log_policy.py
│   └── test_report_renderer.py
├── integration/       # 跨模块/服务的集成测试
│   ├── test_cli_intake.py        # CLI intake + service
│   ├── test_agent_diagnosis.py   # 端到端诊断流程
│   ├── test_interrupt_resume.py  # interrupt / resume
│   ├── test_cli_analyze.py       # CLI 主路径 + 产物
│   └── test_gateway.py           # Gateway 全链路
├── acceptance/        # 公共契约 / CLI 公开接口
│   └── test_cli_contract.py
├── eval/              # 风险驱动测试 + 标注 fixture
│   └── test_datasets.py
└── e2e/               # 真实 CLI + Gateway 端到端 (5 fixture × 2 路径)
    └── test_end_to_end.py
```

| 层级 | 跑时 | 数量 | 角色 |
| --- | --- | --- | --- |
| unit | 每次 PR | 多个 | 锁定函数行为 |
| integration | 每次 PR | 多个 | 验证跨模块契约 |
| acceptance | 每次 PR | 多个 | 锁定 CLI 公共契约 |
| eval | 每次 PR | 多个 | 风险驱动 + 标注 ground truth |
| e2e | 每次 PR + 部署前 | 5 × 2 = 10 | 真实 CLI + Gateway |

总计：**187 个测试**（Unit 9 后）。

## 2. 跑测试

### 2.1 跑全部

```bash
cd /Users/pittcat/Dev/Python/atelier
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/ tests/ -q
# 187 passed
```

### 2.2 跑单个文件

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src \
  .venv/bin/python -m pytest \
  agents/modem-log-analyzer/tests/unit/test_log_parser.py -v
```

### 2.3 跑指定测试

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src \
  .venv/bin/python -m pytest \
  agents/modem-log-analyzer/tests/unit/test_log_parser.py::test_parser_strips_ansi_escape_codes -v
```

### 2.4 Makefile 方式

```bash
cd agents/modem-log-analyzer
TEST=tests/unit/test_contracts.py make test
```

### 2.5 跑 e2e

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/e2e/ -v
# 10 passed
```

### 2.6 跑独立 e2e 脚本（合成 5 cases）

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python scripts/e2e_modem_log_analyzer.py
```

### 2.7 真实日志端到端（必跑）

验收「真实可用」时必须用 `tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/`：

- `merge.log` — 多串口按时间合并的 EVB
- `control_script.log` — 同次控制脚本
- `modemcli_commands.md` — ModemCLI 命令参考（项目知识来源）

```bash
# 仓库根
.venv/bin/python scripts/e2e_modem_log_analyzer_real.py
```

合成 `e2e_cases` **不能**替代本组真实样本。

> Plan §5 U6: 本脚本必须真实调用 ``agent_runner.run_agent_analyze`` (CLI 默认主路径);
> 在无 LLM key 的环境下, 脚本会显式 ``WARN`` + skip, **不**伪造 PASS。
> 有 key 时 exit 0 且 ``analysis.json`` 通过 schema 校验。

#### 2.7.1 Agent key 隔离矩阵

| 环境 | ``e2e_modem_log_analyzer_real.py`` | ``tests/e2e/test_end_to_end.py`` | ``tests/integration/test_*`` |
| --- | --- | --- | --- |
| 有真实 LLM key | 真实 Agent path; exit 0 + 双产物 | 真实 Agent path | monkeypatch runner / 使用 force-rules |
| 无 key (CI 默认) | 显式 skip + stderr 提示; exit ≠ 0 警告 | ``MODEM_LOG_ANALYZER_CLI_FORCE_RULES=1`` 退回确定性规则 | 同上 |
| 本地开发 | 推荐用真实 key 跑一次 | 任意 | 任意 |

> 注: 默认 CI 不打真实 LLM; 真实样本 E2E 仅在有 key 时跑,
>     且必须显式标 ``@pytest.mark.llm`` 或独立脚本。

## 3. TDD 流程（Plan §5 串行门禁）

每个 Unit 严格走 Red → Green → Refactor 闭环：

### 3.1 Red：先写失败测试

```python
# agents/modem-log-analyzer/tests/unit/test_X.py
def test_X_should_do_Y():
    # 给定输入 ...
    # 期望输出 ...
    assert ...  # 必然失败 (X 还没实现)
```

跑一次确认 Red：

```bash
PYTHONPATH=... .venv/bin/python -m pytest tests/unit/test_X.py -v
# FAILED - 因为模块 X 还没建
```

### 3.2 Green：写最小实现

在 `src/modem_log_analyzer/X.py` 写最小代码让测试通过。**不**做防御性 / 优化 / 重构。

### 3.3 Refactor

测试通过后，重构：
- 提取公共函数
- 改善命名
- 删冗余

每改一次跑一次：

```bash
PYTHONPATH=... .venv/bin/python -m pytest tests/ -q
# 仍 187 passed
```

### 3.4 锁门：跑质量门禁

```bash
.venv/bin/ruff check agents/modem-log-analyzer/ gateway/
.venv/bin/ruff format --check agents/modem-log-analyzer/ gateway/
bash scripts/smoke.sh
```

通过后才能进入下一个 Unit。

## 4. 加新功能的标准流程

举例：加"识别 IMSI 子命令"。

### 4.1 Step 1 — 写失败测试

```python
# tests/unit/test_log_parser.py
def test_parser_extracts_imsi_subcommand():
    raw = "[2026-07-19 10:00:00.000][ap] modemcli> debug_bes_rpc 7 [IMSI_REDACTED]\n"
    events = parse_evb_log(raw)
    cmd = next(e for e in events if e["kind"] == "command")
    assert cmd["business_action"] == "imsi_query"
```

### 4.2 Step 2 — 跑确认 Red

```bash
$ .venv/bin/python -m pytest tests/unit/test_log_parser.py::test_parser_extracts_imsi_subcommand
# FAILED: assert ... == 'imsi_query'  ← KeyError or wrong value
```

### 4.3 Step 3 — 改 catalog + parser 最小实现

```yaml
# knowledge/modemcli_commands.yaml 加:
- name: "debug_bes_rpc"
  known_arg_ranges:
    ...
    - range: [7, 7]
      business_action: "imsi_query"
```

parser 不用改（catalog 已支持）。

### 4.4 Step 4 — 跑确认 Green

```bash
$ .venv/bin/python -m pytest tests/unit/test_log_parser.py::test_parser_extracts_imsi_subcommand
# PASSED
```

### 4.5 Step 5 — 加 fixture

```
tests/fixtures/e2e_cases/case_imsi_query_success/
├── evb.log         # 含 debug_bes_rpc 7 ...
├── control.log     # 可选
└── expected.json   # {"classification": "NO_DEVICE_ANOMALY_FOUND", "scenario_substring": "imsi"}
```

### 4.6 Step 6 — 更新 docs

- `docs/COMMAND_CATALOG.md` 加新条目
- `docs/PROMPT.md` 变更记录加一行
- `docs/EXAMPLES.md` 加用例

### 4.7 Step 7 — 跑全部质量门禁

```bash
.venv/bin/python -m pytest tests/ -q              # 188 passed
.venv/bin/ruff check .                            # clean
.venv/bin/ruff format --check .                   # formatted
bash scripts/smoke.sh                             # 185 PASS
```

### 4.8 Step 8 — Commit

```bash
git add agents/modem-log-analyzer/{src,tests,docs,knowledge}
git commit -m "feat(modem-log-analyzer): add IMSI query subcommand"
```

## 5. 风险驱动测试（eval/）

`tests/eval/test_datasets.py` 锁定 4 类风险：

### 5.1 parser property-based

随机生成 ANSI / 空行 / 控制序列不改变命令语义：

```python
def test_random_ansi_invariance():
    raw = "modemcli> debug_bes_rpc 1 13900000000\n"
    for ansi in ["\x1b[0m", "\x1b[31m", ...]:
        noisy = ansi + raw + ansi
        events = parse_evb_log(noisy)
        cmds = [e for e in events if e["kind"] == "command"]
        assert len(cmds) == 1
        assert cmds[0]["command_name"] == "debug_bes_rpc"
```

### 5.2 业务 state-machine

```python
def test_command_followed_by_callback():
    # 时间线必含 command + callback
    kinds = [ev.get("event", "") for ev in result["timeline"]]
    assert any("命令" in k for k in kinds)
    assert any("回调" in k for k in kinds)
```

### 5.3 renderer differential

```python
def test_renderer_differential_consistency():
    md1 = render_report_md(result)
    md2 = render_report_md(result)
    # 章节位置一致
    pos1 = [md1.index(s) for s in sections]
    pos2 = [md2.index(s) for s in sections]
    assert pos1 == pos2
```

### 5.4 关键分类 mutation

```python
def test_classification_mutation_device_failure_to_evidence_incomplete():
    # is_complete 改 False → 必降级
    cls = decide_classification(
        has_device_anomaly=True, ..., is_complete=False
    )
    assert cls == DEVICE_EVIDENCE_INCOMPLETE
```

### 5.5 参考样例

`tests/fixtures/reference_case_52/` + `tests/fixtures/e2e_cases/*/`。

`expected.json` 由工程师手写（**不**由 Agent 自动生成）。

## 6. 调试技巧

### 6.1 跑失败的测试并查看 traceback

```bash
PYTHONPATH=... .venv/bin/python -m pytest tests/unit/test_X.py::test_Y -vv --tb=long
```

### 6.2 在 REPL 里手动触发

```python
import sys
sys.path.insert(0, "agents/modem-log-analyzer/src")
sys.path.insert(0, "libs/common/src")

from modem_log_analyzer.log_parser import parse_evb_log
events = parse_evb_log(open("evb.log").read())
for ev in events:
    print(ev)
```

### 6.3 集成 CLI 调试

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src \
  .venv/bin/python -m modem_log_analyzer.cli analyze \
  --evb-log evb.log --output out --dry-run --overwrite
# 看 stderr + stdout, 不写产物
```

### 6.4 覆盖率（可选）

```bash
TMPDIR=/tmp/atelier-tmp uv pip install --python .venv/bin/python pytest-cov
PYTHONPATH=... .venv/bin/python -m pytest \
  agents/modem-log-analyzer/tests/ --cov=modem_log_analyzer --cov-report=term-missing
```

## 7. 性能测试（基准）

参考 `OPERATIONS.md §7`：

| 用例 | 期望耗时 |
| --- | --- |
| 1000 行 EVB, dry-run | < 1s |
| 1000 行 EVB + 写产物 | < 1s |
| Gateway 完整流程 | < 2s |

## 8. CI 集成建议

`.github/workflows/test.yml` 示例：

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install uv
      - run: uv sync
      - run: uv run pytest tests/ -v
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: bash scripts/smoke.sh
```

## 9. 标注 fixture 编写规则

```
tests/fixtures/e2e_cases/<name>/
├── evb.log          # 必填
├── control.log      # 可选
└── expected.json    # 必填
```

`expected.json` schema：

```json
{
  "description": "一句话描述这个 case",
  "classification": "DEVICE_FAILURE_CONFIRMED | ... (6 选 1)",
  "scenario_substring": "call | sms | ... | 混合场景",
  "expected_business_actions": ["call", ...],
  "expected_first_anomaly_module": "apc1" | null,
  "expected_evidence_ref_count_min": 3,
  "expected_scenario_confidence": "high | medium | low",
  "note": "工程师批注 (含脱敏说明)"
}
```

**硬要求**：
- `expected.classification` **必须**工程师手写（不依赖 Agent 输出）
- `expected.json` 必须由 git blame 留痕，便于审计
- 数据已脱敏（参见 PRIVACY.md §5）

## 10. 不应做的反模式

| 反模式 | 后果 |
| --- | --- |
| 直接断言 len(tools) >= 1 而不校验内容 | 漏掉 git_push 工具 |
| 用 mock 模拟 LLM 而不是固定模型替身 | 真实模型替换后回归 |
| 删除 `.skip` / `pytest.skip` 让"失败"测试通过 | Plan §6 反向断言 |
| 用更宽的 `assertAny` 代替精确断言 | 漏掉边界 |
| `expected.json` 由 Agent 生成 | 锁定 ground truth 失效 |
| 把真实电话号码放进 fixture | 隐私违规 |