# ModemLogAnalyzer — README

> Atelier 平台下的 NuttX Modem 单轮失败日志分析 Agent。
> CLI 首要交付入口，同步输出 `report.md` + `analysis.json`。
> 6 个诊断分类严格匹配需求 R13。

## 这是什么

`modem-log-analyzer` 是嵌入式测试工程师的单轮失败日志分析工具：

- 输入：一份已切分好的单次 NuttX EVB 日志（必需）+ 同次执行的控制脚本日志（可选）
- 输出：中文 Markdown 失败分析报告 + 机器可读的 `analysis.json`
- 6 个分类：`DEVICE_FAILURE_CONFIRMED` / `ENVIRONMENT_FAILURE_INDICATED` / `TEST_AUTOMATION_FAILURE_CONFIRMED` / `NO_DEVICE_ANOMALY_FOUND` / `DEVICE_EVIDENCE_INCOMPLETE` / `MULTIPLE_POSSIBLE_CAUSES`

适合：
- EVB 日志含多模块噪声、异步回调、双时间戳，需要结构化整理
- 想要回答"板端最早在哪里异常、如何传播、属于哪个故障域"
- 当 EVB 证据不足以解释外部 FAIL 时，能交互请求控制脚本日志
- 离线 deterministic 分析（不依赖外部 LLM 即可跑通管线）

## 启动

```bash
cd agents/modem-log-analyzer
uv sync
cp .env.example .env  # 填好 ANTHROPIC_API_KEY / LANGSMITH_API_KEY
make dev              # LangGraph Studio: http://localhost:2024
```

或者直接 CLI：

```bash
modem-log-analyzer analyze --evb-log evb.log --output out/
```

## 快速开始（最常用 5 条命令）

```bash
# 1. 最小：只给 EVB 日志
modem-log-analyzer analyze --evb-log evb.log --output out/

# 2. 带控制日志
modem-log-analyzer analyze \
  --evb-log evb.log --control-log control.log \
  --output out/ --label "loop_52"

# 3. dry-run（仅校验 + 输出 JSON，不写产物）
modem-log-analyzer analyze --evb-log evb.log --output out/ --dry-run

# 4. 覆盖已有产物
modem-log-analyzer analyze --evb-log evb.log --output out/ --overwrite

# 5. Gateway 调用
curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -F "artifact=@evb.log"
```

更多命令速查见 [`docs/EXAMPLES.md`](./EXAMPLES.md)。

## 设计目标

1. **CLI-first**：嵌入式测试工程师日常工具，不需要 LLM 在线即可离线 deterministic 跑管线。
2. **可复核证据**：报告中的每个关键结论都引用真实日志原文（`evidence_refs[*].raw_text`），工程师可一键回溯。
3. **诚实降级**：证据不足时不强求结论，使用较弱分类。
4. **不越界**：不暴露 `bash` / `write_file` / `git_commit` / `git_push`，绝不读取全局 `~/.claude/skills`。
5. **架构兼容**：遵循仓库 AGENTS.md 硬规矩（checkpointer 必开、不读全局 Skill/MCP、prompt 同步 `docs/PROMPT.md` 等）。

## CLI 主入口

```bash
# 最小用法：仅 EVB 日志和输出目录
modem-log-analyzer analyze --evb-log path/to/evb.log --output path/to/out

# 可选：同时提供控制脚本日志 + 自定义标识
modem-log-analyzer analyze \
  --evb-log path/to/evb.log \
  --control-log path/to/control.log \
  --output path/to/out \
  --label "loop_52"

# dry-run：仅做输入校验
modem-log_analyzer analyze --evb-log evb.log --output out --dry-run

# 显式授权覆盖已有产物
modem-log-analyzer analyze --evb-log evb.log --output out --overwrite
```

CLI **不要求** loop / case 编号；缺标识时使用"单次测试执行"作为显示名。

### 参数详解

| 参数 | 必需 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--evb-log` | 是 | - | 单次 EVB 日志路径（必需） |
| `--output` | 是 | - | 报告输出目录（必需） |
| `--control-log` | 否 | None | 同次执行的控制脚本日志路径 |
| `--label` | 否 | None | 自定义标识（loop/case 等），最长 200 字符 |
| `--thread` | 否 | UUID | LangGraph thread id |
| `--overwrite` | 否 | False | 允许覆盖已有 `report.md` / `analysis.json` |
| `--dry-run` | 否 | False | 仅做输入校验，不调用 LLM / 不写文件 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `2` | 输入校验失败（`IntakeError`，见 [`OPERATIONS.md §2`](./OPERATIONS.md)） |

## 诊断分类（6 个）

按 Plan R13 严格匹配：

| 分类 | 何时使用 |
| --- | --- |
| `DEVICE_FAILURE_CONFIRMED` | 板端业务异常明确（ERROR/FAIL/TIMEOUT 等），证据完整 |
| `ENVIRONMENT_FAILURE_INDICATED` | 板端无异常 + 环境/网络异常指征明确 |
| `TEST_AUTOMATION_FAILURE_CONFIRMED` | 控制脚本日志含 **直接证据**（`AssertionError` / `TimeoutError` / `case_result=FAIL`） |
| `NO_DEVICE_ANOMALY_FOUND` | 板端 OK + 无证据反驳；**不等于**自动化误报 |
| `DEVICE_EVIDENCE_INCOMPLETE` | 板端异常，但缺终态或回调 |
| `MULTIPLE_POSSIBLE_CAUSES` | 多种业务异常并存，或设备+环境异常并存 |

**关键边界**（Plan R14）：
- 仅 EVB 日志 + 板端正常 → `NO_DEVICE_ANOMALY_FOUND`，**不得**宣称自动化误报。
- 必须有控制日志直接证据 → 才可升级为 `TEST_AUTOMATION_FAILURE_CONFIRMED`。

## 报告章节（10 章节，顺序固定）

`report.md` 由确定性 renderer 生成，章节顺序锁定：

1. 失败概览（运行标识、外部 FAIL、推断场景、诊断分类、根因置信度）
2. 推断的测试场景与基线
3. 核心诊断（首个异常 / 已验证状态）
4. 根因链（trigger → propagation → terminal_impact，含缺口）
5. 失败时间线（每条事件附 EV-NNNN 证据）
6. 测试步骤与日志证据（完整原文）
7. 故障域判定与推理（外部 FAIL 与 Agent 分类分离）
8. 剩余不确定性
9. 建议行动
10. 正式证据索引（表格）

每条关键结论都有 `EV-NNNN` 引用；`## 正式证据索引` 是这些 ID 的真相之源。

## 子代理

| 名字              | 职责 |
|-------------------|------|
| `diagnostician`   | 受 schema 约束的结构化诊断草稿；单职责、深度 ≤ 2、工具 ≤ 5 |

## 工具

只读日志分析 Agent 主代理只暴露两个工具：

| 工具                      | 用途 |
|---------------------------|------|
| `read_control_log`        | 读控制脚本日志（仅在 CLI 提供 `--control-log` 时可用） |
| `validate_analysis_draft` | 校验 `AnalysisResult` 草稿是否符合 Pydantic schema |

> ⛔ 严格不暴露 `bash`、`write_file`、`git_commit`、`git_push`（AGENTS.md 硬规矩 + Plan §1 R16）。

## 测试

```bash
make test                              # 全套
TEST=tests/unit/test_contracts.py make test
TEST=tests/eval/test_datasets.py make test    # 风险驱动 + 标注样例
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/e2e/ -v   # 合成 e2e (5 cases)
```

### 真实日志端到端（必跑）

发布前 / 验收「能不能真的分析」时，**必须**用下面这组真实单次 loop 样本，而不是只跑合成 `e2e_cases`：

| 文件 | 路径 |
| --- | --- |
| 多串口合并 EVB | `tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/merge.log` |
| 同次控制脚本 | `tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/control_script.log` |
| ModemCLI 命令表 | `tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/modemcli_commands.md` |

```bash
# 仓库根目录
.venv/bin/python scripts/e2e_modem_log_analyzer_real.py

# 或手动 CLI
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src \
  .venv/bin/python -m modem_log_analyzer.cli analyze \
  --evb-log agents/modem-log-analyzer/tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/merge.log \
  --control-log agents/modem-log-analyzer/tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/control_script.log \
  --output /tmp/modem-la-real-52 \
  --label auto_case_modem_52_loop75 \
  --overwrite
```

更多测试细节见 [`docs/TESTING.md`](./TESTING.md)。

## 评测与参考样例

- 风险驱动测试位于 `tests/eval/test_datasets.py`：parser property-based、业务 state-machine、renderer differential、关键分类 mutation。
- 标注 fixture：
  - `tests/fixtures/e2e_real_samples/auto_case_modem_52_loop75/` — **真实** merge + control + ModemCLI 表（端到端主样本）
  - `tests/fixtures/reference_case_52/` — 脱敏合成对照（Unit 7）
  - `tests/fixtures/e2e_cases/` — 5 个合成端到端场景（Call/SMS/Data-Ping/Setting/混合）
- 真实 LangSmith Evaluator 接入（部署前必跑）需 `LANGSMITH_API_KEY`。

## 部署

```bash
make build          # 构建 atelier/modem-log-analyzer 镜像
make up             # 启动服务
make gateway        # 启 gateway/api（统一网关）
```

生产部署需要：
- `ATELIER_CHECKPOINTER_URL=postgresql://...`（Plan R4 硬规矩）
- `GATEWAY_AUTH_TOKEN=$(openssl rand -hex 32)`
- `LANGSMITH_TRACING=true`（如需 trace）

## 文档索引

| 文档 | 用途 |
| --- | --- |
| [`README.md`](./README.md) | 本文件 — 启动 + 快速开始 |
| [`EXAMPLES.md`](./EXAMPLES.md) | 5 个 e2e fixture 输入/输出 + 命令速查 + Gateway curl |
| [`OPERATIONS.md`](./OPERATIONS.md) | 退出码、错误信息字典、Gateway 路由清单、故障排查、监控指标 |
| [`PRIVACY.md`](./PRIVACY.md) | 三层隐私边界、终端脱敏规则、trace 策略、fixture 脱敏规范 |
| [`COMMAND_CATALOG.md`](./COMMAND_CATALOG.md) | 命令知识表 + 加新命令/业务类型流程 |
| [`TESTING.md`](./TESTING.md) | 测试分层、TDD Red→Green→Refactor 流程、加新功能 SOP |
| [`PROMPT.md`](./PROMPT.md) | 提示词运维手册（含变更记录） |
| [`INTERRUPTS.md`](./INTERRUPTS.md) | 中断工具与控制脚本日志请求 |
| [`MCP_AND_SKILLS.md`](./MCP_AND_SKILLS.md) | MCP 与 Skills 配置 |

## 仓库文档参考

- [`../../../AGENTS.md`](../../../../AGENTS.md) — 仓库宪法（硬规矩 1-8）
- [`../../../CLAUDE.md`](../../../../CLAUDE.md) — Claude Code 操作指南
- [`../../../docs/plans/2026-07-19-001-feat-modem-log-analyzer-cli-plan.md`](../../../docs/plans/2026-07-19-001-feat-modem-log-analyzer-cli-plan.md) — 9 个开发 Unit 的原始 plan
- [`../../../docs/solutions/integration-issues/modem-log-analyzer-adversarial-review-2026-07-19.md`](../../../docs/solutions/integration-issues/modem-log-analyzer-adversarial-review-2026-07-19.md) — 完成性 + 对抗性审查报告

---

> 改任何代码前先读 `docs/PRIVACY.md` 和 `COMMAND_CATALOG.md`。
> 出问题时先看 `OPERATIONS.md §5 故障排查 Checklist`。
> 部署前必须跑 `tests/e2e/` + 真实 LangSmith A/B。