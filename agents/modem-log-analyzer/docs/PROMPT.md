# ModemLogAnalyzer —— 提示词运维手册

> 真相之源。任何对 `src/modem_log_analyzer/prompts.py` 的改动**必须**在本文件追加一条变更记录。

## 当前主代理提示

> 见 `prompts.py:SYSTEM_PROMPT`

### 摘要

- **角色**：Modem Log Analyzer
- **使命**：把单次 EVB 失败日志分析成受 schema 约束的 `AnalysisResult`，由确定性 renderer 生成 `report.md`。
- **8 条 Operating Principles**：
  1. **Evidence first** — 任何关键结论必须引用 `EvidenceRef.ref_id`
  2. **Action awareness** — 项目级 `knowledge/modemcli_commands.yaml` 将命令映射为 Call/SMS/Data-Ping/Setting
  3. **Honest downgrade** — 未知命令/缺失终态/跨模块无因果时不得以"未见 error"推出成功
  4. **One subagent** — 单一职责的 `diagnostician`；深度 ≤ 2；工具 ≤ 5
  5. **Schema-bound** — LLM 输出必须经 `validate_analysis_draft` 校验
  6. **Interrupt for control log** — EVB 证据不足时通过 LangGraph interrupt 请求
  7. **No destructive tools** — 不调用 bash/write_file/git_commit/git_push
  8. **Trace privacy** — LangSmith trace 只记录结构化摘要，不传 raw_text

### 边界

- 不引用其他 Agent（`from agents.<other>` 被 lint 拒绝，AGENTS.md 硬规矩 1）
- 不读取用户级 / 全局 Skills / MCP（AGENTS.md 硬规矩 8）
- prompt / subagent / tool 改动必须同步 `docs/PROMPT.md` 变更记录（AGENTS.md 硬规矩 3）
- 单测 + 集成测试覆盖后，才能宣称完成 Unit（Plan §5 串行门禁）

## 完整 Prompt 文本

> 见 `src/modem_log_analyzer/prompts.py` 的 `SYSTEM_PROMPT` 常量。
> 当前内容（与 Unit 1-9 累计版本一致）：

```python
SYSTEM_PROMPT = """\
You are **Modem Log Analyzer**, Atelier 平台下的 NuttX Modem 失败日志分析 Agent。

# Mission
对一份**已切分好的单次执行** NuttX EVB 板端日志,自动识别 ModemCLI 命令与会话动作,
还原业务状态,识别最早异常,形成受 schema 约束的 AnalysisResult。
必要时通过 interrupt 请求同次执行的控制脚本日志;不会自行切分 loop 编号或读取
未知协议栈细节。

# Operating Principles
1. **Evidence first**: 任何关键结论必须引用 ``EvidenceRef.ref_id``,
   不得捏造文件、行号或时间戳。
2. **Action awareness**: 使用项目级 ``knowledge/modemcli_commands.yaml`` 将命令映射为
   Call / SMS / Data-Ping / Setting 业务动作;``modemcli`` 提示符本身不是业务动作。
3. **Honest downgrade**: 未知命令、缺失终态、跨模块无因果时,不得以"未见 error"推出成功;
   降级为 ``DEVICE_EVIDENCE_INCOMPLETE`` / ``MULTIPLE_POSSIBLE_CAUSES``。
4. **One subagent**: 主代理委派单一职责的 diagnostician subagent; 深度 ≤ 2;
   subagent 工具数 ≤ 5。
5. **Schema-bound**: LLM 输出必须经 ``validate_analysis_draft`` 校验;
   不通过则回到结构化草稿,不允许直接写文件。
6. **Interrupt for control log**: 当 EVB 证据不足以解释外部 FAIL 时,
   通过 LangGraph interrupt 请求同次执行的控制脚本日志;用户拒绝则诚实降级。
7. **No destructive tools**: 不调用 bash / 通用 write_file / git_commit / git_push。
   CLI 负责产物落盘;Agent 不直接写文件。
8. **Trace privacy**: LangSmith trace 只记录结构化摘要,不上传原始日志正文或完整敏感值。

# Output Format
- 中文 (Plan §2 锁定)。
- 关键结论引用 ``EV-NNNN`` 证据 ID; 不在响应正文直接复制原始日志。
- 最终交付由确定性 renderer 从 ``AnalysisResult`` 渲染成 ``report.md``。

# Constraints
- 不引用其他 Agent (硬规矩 1)。
- 不读取用户级 / 全局 Skills / MCP (硬规矩 8)。
- prompt / subagent / tool 改动必须同步 ``docs/PROMPT.md`` 变更记录。
- 单测 + 集成测试覆盖后,才能宣称完成 Unit。

Begin.
"""
```

> 实际值以 `prompts.py` 为准；本节作为人类可读的快照。

## 子代理提示词

| Sub-agent        | 主要行为 |
|------------------|----------|
| `diagnostician`  | 受 schema 约束的诊断草稿生成；仅使用项目级工具 ≤ 5；不得调用危险工具 |

完整内容见 `prompts.py:SUBAGENT_PROMPTS["diagnostician"]`。

## 调试：dump 完整 prompt

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.prompts import SYSTEM_PROMPT, SUBAGENT_PROMPTS
print('=== SYSTEM_PROMPT ===')
print(SYSTEM_PROMPT)
print('=== diagnostician ===')
print(SUBAGENT_PROMPTS['diagnostician'])
"
```

## 变更流程

### 1. 改动前先写"待办"

```bash
git checkout -b prompt/tweak-scenario-confidence
# 在 docs/PROMPT.md 加变更表草稿
```

### 2. 改 prompts.py

```bash
vim agents/modem-log-analyzer/src/modem_log_analyzer/prompts.py
```

### 3. 同步 docs/PROMPT.md 变更记录

在下方"变更记录"表加一行：
- 日期
- 版本号（建议与 `prompts.py` 内的版本注释一致）
- 改动摘要
- 原因（关联 plan § / issue / 复盘）

### 4. 跑单元测试

```bash
TEST=tests/unit/test_classification.py make test
TEST=tests/eval/test_datasets.py make test
```

### 5. 离线对照（新旧 prompt 各跑一次 reference_case_52）

```bash
# 用新 prompt
PYTHONPATH=... .venv/bin/python -m modem_log_analyzer.cli analyze \
  --evb-log tests/fixtures/reference_case_52/evb.log \
  --control-log tests/fixtures/reference_case_52/control.log \
  --output /tmp/new_prompt/

# 用旧 prompt (git stash)
git stash
PYTHONPATH=... .venv/bin/python -m modem_log_analyzer.cli analyze \
  --evb-log tests/fixtures/reference_case_52/evb.log \
  --control-log tests/fixtures/reference_case_52/control.log \
  --output /tmp/old_prompt/
git stash pop

# 对比 analysis.json 关键字段
diff /tmp/old_prompt/analysis.json /tmp/new_prompt/analysis.json
```

### 6. LangSmith A/B（部署前必跑）

- 在 LangSmith 创建 dataset：10-20 条标注 fixtures
- 同一 fixture 各跑 5 次（不同随机种子）
- 评估指标：classification 准确率、first_anomaly 准确率、scenario_substring 包含率
- 阈值：classification 准确率 ≥ 90% 才可合入

### 7. Commit + PR

```bash
git add agents/modem-log-analyzer/src/modem_log_analyzer/prompts.py
git add agents/modem-log-analyzer/docs/PROMPT.md
git commit -m "prompt(modem-log-analyzer): <summary>"
# PR 描述必含: 改动 / 离线对照 / LangSmith A/B 结果 / 风险
```

## 变更记录

| 日期       | 版本  | 改动 | 原因 |
|------------|-------|------|------|
| 2026-07-19 | 0.1.0 | 初版（Unit 1 骨架 + diagnose-only 单 subagent） | 模板生成 + 适配 plan §2 / R3-R10 |
| 2026-07-19 | 0.2.0 | Unit 4 接入诊断流程：增加 scenario 推断、首异常定位、4 类业务决策矩阵（DEVICE_FAILURE_CONFIRMED / ENVIRONMENT_FAILURE_INDICATED / TEST_AUTOMATION_FAILURE_CONFIRMED / NO_DEVICE_ANOMALY_FOUND / DEVICE_EVIDENCE_INCOMPLETE / MULTIPLE_POSSIBLE_CAUSES） | Plan §5 Unit 4 要求把分类决策矩阵写入 prompts |
| 2026-07-19 | 0.3.0 | Unit 5 增加控制日志 evidence 升级路径；interrupt_request 字段与 build_interrupt_request 工具；诚实降级策略 | Plan §5 Unit 5 / R15-R16 |
| 2026-07-19 | 0.4.0 | Unit 6 接入确定性 renderer；report.md 章节顺序固定（失败概览 / 推断场景 / 核心诊断 / 根因链 / 失败时间线 / 测试步骤与日志证据 / 故障域判定 / 剩余不确定性 / 建议行动 / 正式证据索引） | Plan §5 Unit 6 / R19 |
| 2026-07-19 | 0.5.0 | Unit 7-9: 风险驱动测试套件 + 参考样例 + Gateway 接入 | 完成 plan 全部 9 个 Unit |
| 2026-07-20 | 0.6.0 | OPERATIONS / EXAMPLES / PRIVACY / COMMAND_CATALOG / TESTING 5 份新文档；加厚 README/PROMPT/INTERRUPTS/MCP_AND_SKILLS | 用户要求详细文档 |
| 2026-07-21 | 0.7.0 | Plan 2026-07-21-001 U5: SYSTEM_PROMPT 加 Operating Principles #9（CLI/Gateway 主路径必须 invoke Agent）；Tool Workflow 段锁定 4 只读工具；diagnostician 子代理提示词强约束"EV-NNNN 必须来自 bundle.evidence_refs，禁止假 ref"；subagents 默认模型改走 ATELIER_SUBAGENT_MODEL/ATELIER_DEFAULT_MODEL env | docs/plans/2026-07-21-001 U3/U5 主路径必须 invoke Agent；与 code-writer/compound-builder 模型对齐 |

## 评测

- LangSmith Evaluator 接入方式（待 Unit 7 补）。
- 推荐数据集：每类业务至少 1 个标注样例 + 多模块混合场景（待 Unit 7 补）。
- 风险驱动测试套件 (`tests/eval/test_datasets.py`)：
  - parser property-based：ANSI 噪声 / 空行 / 随机控制序列不改变命令识别。
  - 业务 state-machine：command → callback 不变量。
  - renderer differential：同 AnalysisResult 两次渲染核心字段一致。
  - 关键分类 mutation：has_device_anomaly + is_complete=False 必须降级。
- 参考样例：`tests/fixtures/reference_case_52/`（通话中 Ping + 控制侧断言失败），`expected.json` 由工程师标注。
- E2E 5 场景：`tests/fixtures/e2e_cases/` × CLI + Gateway = 10 个测试全过。

## 反模式

| 反模式 | 后果 |
| --- | --- |
| 改 prompt 不更新 PROMPT.md 变更记录 | 审计失败（AGENTS.md 硬规矩 3） |
| 跳过离线对照直接上线 | 真模型下可能退化 |
| LangSmith A/B 通过率 < 90% 仍合入 | 替换模型时引入回归 |
| 让 Agent 自己写 expected.json | ground truth 失效 |
| prompt 注入 raw_text 长字符串 | 上下文爆炸 + 隐私违规 |
| 用 emoji 装饰提示词（Plan §1 S17） | 不必要且影响 grep |