---
title: feat: Add NuttX Modem failure-analysis CLI agent
type: feat
status: active
date: 2026-07-19
origin: docs/brainstorms/2026-07-19-nuttx-modem-loop-failure-analysis-agent-requirements.md
deepened: 2026-07-19
---

# feat: Add NuttX Modem failure-analysis CLI agent

## 1. 功能目标

### 业务目标

- 为嵌入式测试工程师交付一个可安装的 `modem-log-analyzer` CLI。用户只需提供一份已切分到单次执行的 NuttX EVB 日志和输出目录，即可获得中文 `report.md` 与机器可读 `analysis.json`（see origin: `docs/brainstorms/2026-07-19-nuttx-modem-loop-failure-analysis-agent-requirements.md`）。
- 自动理解 `modemcli` 会话内的 `debug_bes_rpc`、`!ping`、`!ping6`、`!ifconfig` 等命令，覆盖 Call、SMS、Data/Ping、Setting 及其混合场景，无需用户逐条描述测试步骤。
- 以可复核证据回答“板端最早在哪里异常、如何传播、属于哪个故障域”；EVB 证据无法解释外部 FAIL 时，交互式请求同次执行的控制脚本日志，或者在用户拒绝/无法提供时诚实降级结论。

### 本次范围

- 新建独立包 `agents/modem-log-analyzer/`，Python import 名为 `modem_log_analyzer`，console script 名为 `modem-log-analyzer`。
- CLI 主契约：`analyze --evb-log <file> --output <dir>`；支持 `--control-log`、`--label`、`--thread` 等可选上下文，但不得要求 loop 编号。
- 输入校验、ANSI 清洗、命令/时间戳/模块提取、稳定证据引用、项目级 ModemCLI 命令知识、四类业务状态语义、结构化诊断、Markdown/JSON 输出。
- 当需要控制日志时，通过 LangGraph interrupt/checkpointer 暂停；CLI 允许用户提供路径后恢复，或选择在证据不足边界下继续生成报告。
- 本地默认 `MemorySaver`，生产使用 `PostgresSaver`；LangSmith trace 默认只记录结构化摘要和指标，不上传原始日志正文或号码、IMSI、ICCID、IMEI 等敏感内容。
- 按仓库生命周期接入 LangGraph Studio、LangSmith evaluator/dataset、gateway 注册与路由、Docker/LangGraph 构建描述、README 与 prompt 变更日志。

### 非目标

- 不接收整批压力测试目录，不自动切分或挑选 loop，不做跨 loop 聚类或失败率统计。
- 不要求成功基线；可选对照最多一份，且不作为第一版主路径。
- 不读取自动化测试源码，不自动操作 EVB，不执行 modem 命令，不复现测试。
- 不进行外部 Web 搜索，不把未知芯片、协议栈或命令语义当成事实。
- 不直接 import 其他 Agent，不提供 `bash`、`git_commit`、`git_push`、通用 `write_file` 等与只读分析无关的 Agent 工具。
- CLI-first 不等于只做脚本：gateway 路由是仓库生命周期要求的接入面，但不替代 CLI 主入口。

### 已知约束和假设

- 必须从 `_templates/agent-template/` 起骨架；每个 Agent 独立成包，只能复用 `libs.common`。
- prompt 必须位于 `prompts.py`，并同步 `docs/PROMPT.md` 变更记录；Skills/MCP 只能来自 `agents/modem-log-analyzer/` 内的项目级来源。
- checkpointer 不得关闭；生产 Postgres 配置缺失必须显式失败，不能静默降级为内存。
- 输出目录由用户明确提供。创建新产物属于该命令的授权范围；若 `report.md` 或 `analysis.json` 已存在，必须先确认或通过显式覆盖选项授权，禁止静默覆盖。
- CLI 的 dotenv/运行环境初始化必须发生在 Agent 模块 import 之前，沿用 `agents/compound-builder/src/compound_builder/cli.py` 的工厂式装配，避免 `docs/solutions/integration-issues/code-writer-cli-502-compound-misconfig.md` 记录的入口差异。
- `analysis.json` 是诊断事实的单一结构化来源；`report.md` 由确定性 renderer 从该结构生成。模型不得直接写任意文件，也不得生成未经 schema/evidence 校验的最终报告。
- 原始日志可能包含电话号码和设备标识；本地报告为了证据复核可保留输入中的原文，但终端摘要、异常消息、LangSmith trace 和 gateway 响应默认不得回显完整敏感值。
- 用户已提供一组本地参考样例：一份 EVB 合并日志、一份同次控制脚本日志和一份 ModemCLI 命令说明。原文件仅作本地研究来源，不以机器绝对路径写入计划或提交仓库；实现时派生为脱敏、最小化、可再分发的 repo fixture，并在写入 expected golden 前由嵌入式测试工程师确认分类、首异常和关键证据。

以下数据流是方向性设计，用于约束组件责任，不是可复制的实现规范：

```text
CLI 输入与授权
  -> 确定性 intake / EVB parser / evidence index
  -> 项目级命令知识与业务状态语义
  -> Agent + diagnostician subagent 生成结构化诊断草案
  -> schema / classification / evidence 引用硬校验
       -> 证据足够：形成最终 AnalysisResult
       -> 需要控制日志：interrupt -> 补充或拒绝 -> 恢复校验
  -> 确定性 renderer
  -> 同组提交 analysis.json + report.md
  -> CLI 脱敏摘要（gateway 复用同一 AnalysisResult 契约）
```

## 2. BDD 行为规格

```gherkin
Feature: 使用 CLI 分析单次 NuttX Modem 失败日志
  作为嵌入式测试工程师
  我希望提交一份单次 EVB 日志并获得可复核的失败分析报告
  从而减少手工还原 Modem 业务状态和定位异常的时间

  Scenario S1: 最小输入生成两种分析产物
    Given 一份可读的单次 EVB 日志和一个可写且无同名产物的输出目录
    And 日志包含可识别的 modemcli 命令及板端异常证据
    When 用户运行 analyze 且不提供 loop 编号、case 描述或控制日志
    Then CLI 应退出成功
    And 输出目录应包含 report.md 与符合契约的 analysis.json
    And 终端只显示简洁诊断摘要和两个产物路径

  Scenario S2: 缺少 loop/case 标识不阻塞分析
    Given EVB 日志正文和文件名均不含 loop 或 case 编号
    When 用户运行 analyze
    Then 分析仍应完成
    And 报告应使用“单次测试执行”作为显示标识

  Scenario S3: 非法输入在调用模型前失败
    Given EVB 路径不存在、不是普通文件、不可读、文件为空或输出路径不可用
    When 用户运行 analyze
    Then CLI 应返回稳定的非零退出状态和可操作错误
    And 不得调用 Agent、创建半成品报告或泄露日志内容

  Scenario S4: 已有产物受到覆盖保护
    Given 输出目录已有 report.md 或 analysis.json
    When 用户未明确确认或授权覆盖而运行 analyze
    Then CLI 不得修改已有产物
    When 用户明确确认或使用显式覆盖选项
    Then 两个产物应作为同一组一致地替换，不留下新旧混合状态

  Scenario S5: 从 modemcli 会话还原业务动作
    Given 日志包含 ANSI 控制符、modemcli 提示符、debug_bes_rpc 命令回显和异步回调
    When 日志被预处理
    Then modemcli 只应被识别为控制 CLI 入口
    And 后续命令应映射为 Call、SMS、Data/Ping 或 Setting 动作
    And 每个动作应保留稳定的原始证据引用

  Scenario S6: 多模块和双时间戳不制造虚假因果
    Given 日志包含 ap、apc1、sensor 等模块且设备时间与采集时间交错
    When Agent 构造时间线和根因链
    Then 时间线应保留来源与时间语义
    And 只有具备命令、状态或时序支持的事件才能进入因果链

  Scenario S7: 确认板端故障
    Given 某个业务步骤具有明确命令、预期状态和板端失败证据
    When Agent 完成诊断
    Then classification 应为 DEVICE_FAILURE_CONFIRMED 或 ENVIRONMENT_FAILURE_INDICATED
    And 报告应指出首个异常步骤、Trigger、Propagation、Terminal Impact 与置信度
    And 所有关键结论应引用正式证据索引中的真实日志行

  Scenario S8: 板端日志无法解释外部 FAIL 时请求控制日志
    Given EVB 日志中的关键状态流看似正常或证据不足
    And 用户未提供控制脚本日志
    When Agent 到达诊断边界
    Then 图应通过 interrupt 请求同次执行的控制脚本日志
    And CLI 应允许用户提供路径恢复或选择不提供

  Scenario S9: 用户不提供控制日志仍获得诚实报告
    Given 分析因证据不足而请求控制日志
    When 用户选择不提供
    Then CLI 应继续生成报告
    And classification 应为 NO_DEVICE_ANOMALY_FOUND、DEVICE_EVIDENCE_INCOMPLETE 或 MULTIPLE_POSSIBLE_CAUSES
    And 报告不得声称已确认自动化误报

  Scenario S10: 控制日志提供直接证据后确认自动化故障
    Given EVB 日志不支持产品故障
    And 同次控制日志明确记录命令执行、断言或超时错误
    When 用户在初始调用或 interrupt 恢复时提供控制日志
    Then classification 可以是 TEST_AUTOMATION_FAILURE_CONFIRMED
    And 报告应区分外部 case_result=FAIL 与板端业务事实

  Scenario S11: 未知命令或缺失状态不会被猜测为成功
    Given 日志包含命令知识表未覆盖的 debug_bes_rpc 参数或缺少最终状态回调
    When Agent 分析该步骤
    Then 未知部分应标记为未识别或证据不足
    And 不得以“未发现 error”推出成功

  Scenario S12: 四类业务与混合场景均遵守同一诊断契约
    Given 分别代表 Call、SMS、Data/Ping、Setting 和通话中短信/Ping 的标注 fixture
    When 对每个 fixture 运行分析
    Then 识别的动作、状态转换、首个异常和分类应与专家标注一致
    And 业务扩展不得改变 CLI 或 analysis.json 的公共契约

  Scenario S13: 同一输入重复运行得到稳定的诊断核心
    Given 相同日志、命令知识版本和模型测试替身
    When 分析执行两次
    Then classification、首个异常步骤、关键证据引用和报告章节顺序应一致

  Scenario S14: 中断状态可恢复且线程隔离
    Given 两个不同 thread 分别暂停等待控制日志
    When 只恢复其中一个 thread
    Then 另一个 thread 的输入、证据和状态不得被读取或修改
    And 本地使用 MemorySaver、生产配置使用 PostgresSaver

  Scenario S15: Gateway 受权调用与 CLI 行为保持契约一致
    Given modem-log-analyzer 已注册到 gateway
    When 未授权客户端调用路由
    Then 请求应被拒绝且 Agent 不运行
    When 授权客户端提交等价输入
    Then 返回的结构化诊断应遵守与 CLI analysis.json 相同的契约

  Scenario S16: Agent 不具备越权工具
    Given Agent 和所有 subagent 已装配
    When 检查其工具注册表和项目级 Skills/MCP 来源
    Then 不得暴露 bash、git_commit、git_push 或通用 write_file
    And 不得读取用户级或全局 Skills/MCP 配置
```

## 3. 验收与测试策略

| Scenario | 验收条件 | 推荐测试层级 | 是否需要 E2E |
|---|---|---|---|
| S1 | CLI 仅凭 EVB 日志和输出目录生成合法 MD/JSON，退出状态与摘要正确 | CLI 集成测试 + schema 契约测试 | 是，1 条离线主路径 |
| S2 | 无标识时使用稳定占位，不要求 loop 参数 | CLI 集成测试 | 否 |
| S3 | 五类非法输入均在模型调用前拒绝且无半成品 | 参数化单元测试 + CLI 集成测试 | 否 |
| S4 | 默认拒绝覆盖；授权后 MD/JSON 原子一致替换 | 文件系统集成测试 + fault injection | 否 |
| S5 | ANSI 清洗、会话识别、命令映射和证据定位正确 | parser 单元测试 + property-based/fuzz test | 否 |
| S6 | 多源时间语义保留，因果关系不由相邻行臆造 | 状态/因果规则单元测试 | 否 |
| S7 | 确认故障具有完整根因链、置信度和真实 evidence refs | 结构化诊断集成测试 + schema 契约测试 | 否 |
| S8 | 证据不足触发 interrupt，CLI 可补日志或拒绝 | LangGraph 集成测试 | 是，1 条中断路径 |
| S9 | 拒绝补日志仍产报告，且不能确认自动化误报 | 集成测试 + golden 报告结构测试 | 否 |
| S10 | 只有直接控制日志证据才能确认自动化故障 | 业务规则单元测试 + 集成测试 | 否 |
| S11 | 未知命令/缺失终态稳定降级，不猜成功 | 参数化单元测试 + fuzz test | 否 |
| S12 | 五组标注 fixture 覆盖四类业务和混合场景 | 状态机测试 + LangSmith evaluator | 是，评测主路径 |
| S13 | 固定替身下诊断核心和报告结构确定 | differential/regression test | 否 |
| S14 | interrupt/resume 正确且 thread 隔离；checkpointer 环境选择正确 | LangGraph 集成测试 + Postgres 契约测试替身 | 否 |
| S15 | gateway 鉴权、注册和结构化输出契约正确 | API 集成/契约测试 | 是，1 条授权 API 主路径 |
| S16 | 禁止工具及全局配置路径均不存在 | 静态结构测试 + 工具注册单元测试 | 否 |

风险驱动测试选择：parser 使用 property-based 与小规模 fuzz；四类业务使用 state-machine test；报告替换使用 fault injection；结构化诊断与 renderer 使用 differential/golden 结构测试；关键分类规则可在稳定后增加 mutation test。真实 LLM E2E 只保留少量 LangSmith evaluator，不把所有 Scenario 推到高成本 E2E。

## 4. 需求—测试追踪矩阵

| 需求 | Scenario | 验收测试 | 单元测试 | 集成/契约测试 | E2E |
|---|---|---|---|---|---|
| R1-R2 | S1-S4 | `agents/modem-log-analyzer/tests/acceptance/test_cli_contract.py` | `agents/modem-log-analyzer/tests/unit/test_intake.py` | `agents/modem-log-analyzer/tests/integration/test_cli_analyze.py` | S1 |
| R3, R6 | S5, S11 | parser fixture 验收 | `agents/modem-log-analyzer/tests/unit/test_log_parser.py`, `agents/modem-log-analyzer/tests/unit/test_command_catalog.py` | preprocessing pipeline | 否 |
| R4-R5 | S7, S11-S12 | 标注场景验收 | `agents/modem-log-analyzer/tests/unit/test_scenario_inference.py` | `agents/modem-log-analyzer/tests/integration/test_agent_diagnosis.py` | S12 |
| R7-R10 | S5-S7, S13 | evidence/causal-chain 验收 | `agents/modem-log-analyzer/tests/unit/test_evidence.py`, `agents/modem-log-analyzer/tests/unit/test_causal_chain.py` | diagnosis schema 契约 | 否 |
| R11 | 可选对照分支 | 单对照/无对照验收 | `agents/modem-log-analyzer/tests/unit/test_baseline_policy.py` | analysis service 集成 | 否 |
| R12-R14, R17 | S7, S9-S13 | 分类与置信度验收 | `agents/modem-log-analyzer/tests/unit/test_classification.py` | Agent 结构化输出契约 | S12 |
| R15-R16 | S8-S10, S14 | interrupt/resume 验收 | `agents/modem-log-analyzer/tests/unit/test_control_log_policy.py` | `agents/modem-log-analyzer/tests/integration/test_interrupt_resume.py` | S8 |
| R18 | S1-S4, S8 | CLI 产物与交互验收 | `agents/modem-log-analyzer/tests/unit/test_cli_options.py` | CLI runner + 原子写入 | S1/S8 |
| R19-R25 | S1, S7, S9-S13 | 报告章节/证据验收 | `agents/modem-log-analyzer/tests/unit/test_report_renderer.py` | MD/JSON differential contract | S1/S12 |
| 仓库硬规矩 1-8 | S14-S16 | layout/smoke 验收 | tools、checkpointer、prompt 静态测试 | Studio/gateway/interrupt 流程 | S15 |

## 5. 严格串行开发单元

> 串行门禁：只能按 Unit 1 → Unit 9 执行。每个 Unit 的验收、Red → Green → Refactor、相关集成测试和受影响回归全部完成后，才允许进入下一 Unit。不得并行开发或把当前 Unit 的失败处理留到后续。

### Unit 1 — 从模板建立独立 Agent 包与公共契约

- **Unit 目标：** 从 `_templates/agent-template/` 生成 `agents/modem-log-analyzer/`，确定 CLI 名、Python 包名、输入契约、`analysis.json` schema、诊断枚举和项目级知识目录；此 Unit 只建立可导入、可打包、可测试的边界。
- **对应 Scenario：** S16，以及 S1/S2 的 CLI 公共入口前置契约（不在本 Unit 宣称分析已完成）。
- **外部可观察结果：** 安装后存在 `modem-log-analyzer --help`，帮助文本只声明真实支持的 `analyze` 输入；包可由 `langgraph.json` 和 Python 正常加载。
- **输入与输出：** 输入为 cookiecutter 参数；输出为 `agents/modem-log-analyzer/` 骨架、公共 Pydantic 契约和空的项目级知识资产位置。
- **可依赖的已完成能力：** `_templates/agent-template/`、根仓库 Python/pytest/ruff/mypy 配置。
- **明确禁止依赖的未来能力：** 不依赖 parser、LLM 诊断、renderer、gateway 或真实日志 fixture。
- **计划文件：** 创建 `agents/modem-log-analyzer/{AGENTS.md,pyproject.toml,Makefile,Dockerfile,langgraph.json,.env.example}`、`agents/modem-log-analyzer/src/modem_log_analyzer/{__init__.py,contracts.py,cli.py,agent.py,state.py,subagents.py,prompts.py,tools.py,checkpointer.py,tracing.py,interrupts.py,skills_loader.py,mcp_servers.py}`、`agents/modem-log-analyzer/docs/{README.md,PROMPT.md,MCP_AND_SKILLS.md,INTERRUPTS.md}`、`agents/modem-log-analyzer/knowledge/modemcli_commands.yaml`、基础测试目录；修改 `tests/test_atelier_layout.py` 增加最小结构断言。
- **验收测试：** `tests/acceptance/test_cli_contract.py` 先断言 console script/help、无强制 loop 参数、诊断枚举和 JSON schema version；顶层 layout 测试先断言新包的必需骨架。
- **需要拆分的单元测试：** schema 接受合法最小输入；拒绝未知 classification；tool registry 不含危险工具；Skills/MCP loader 只接受项目级路径。
- **Red 预期失败原因：** console script、包目录、公共 schema 与项目级知识路径尚不存在。
- **最小实现范围：** 以 `agent_slug=modem_log_analyzer` 渲染合法 Python import，再将生成目录按仓库 Agent slug 约定放置为 `agents/modem-log-analyzer/`；声明 console script 与契约。`analyze` 可明确返回“尚未实现”的稳定状态，不伪造报告。
- **TDD 闭环：** (1) 启用上述验收测试；(2) 确认因入口/契约缺失失败；(3) 将 schema、工具注册和路径规则拆成单测；(4) 对每项 Red → Green → Refactor；(5) 运行包导入/CLI help 集成；(6) 运行顶层 layout 与既有 Agent 回归；(7) 确认无 skip/弱化断言后关闭；(8) 才进入 Unit 2。
- **集成验证：** build backend 能发现 `src/modem_log_analyzer`；`langgraph.json` 指向存在且可导入的入口。
- **回归范围：** `tests/test_atelier_layout.py`、code-writer/compound-builder 既有结构测试、根 `make smoke`。
- **完成标准：** format、lint、mypy、Unit 1 测试和相关回归全绿；骨架来自模板且无跨 Agent import。
- **风险与注意事项：** 模板默认子代理和通用写工具不适合只读日志分析，必须在本 Unit 收紧注册表；不得删除宪法要求的 checkpointer、prompt 文档或项目级 skill 机制。

### Unit 2 — CLI 输入校验、输出授权与原子产物边界

- **Unit 目标：** 完成 `analyze --evb-log --output` 的最小外部契约，所有非法输入在 Agent 调用前失败，并保护已有产物。
- **对应 Scenario：** S1（仅输入边界）、S2、S3、S4。
- **外部可观察结果：** 合法输入进入分析服务接口；缺失/空/不可读 EVB 和无效输出目录得到稳定错误；缺少 loop 不阻塞；未授权不覆盖已有文件。
- **输入与输出：** 文件路径、输出目录、可选 control log/label/thread/overwrite；输出为验证后的 run request 或 CLI 错误，不产生诊断内容。
- **可依赖的已完成能力：** Unit 1 CLI、contracts 和包结构。
- **明确禁止依赖的未来能力：** 不读取命令语义，不调用 LLM，不生成最终报告。
- **计划文件：** 修改 `src/modem_log_analyzer/{cli.py,contracts.py}`；创建 `src/modem_log_analyzer/intake.py`、`tests/unit/{test_cli_options.py,test_intake.py}`、`tests/integration/test_cli_intake.py`。
- **验收测试：** 参数化覆盖不存在、目录冒充文件、空文件、不可读、control log 非法、输出父目录不可用、产物冲突、显式覆盖；使用 CLI runner 验证退出码/stderr/无半成品。
- **需要拆分的单元测试：** 路径规范化与逃逸边界、可选 label、自动显示标识回退、输出冲突决策、临时文件提交/回滚策略。
- **Red 预期失败原因：** CLI 尚未验证输入，也没有成组产物覆盖保护。
- **最小实现范围：** 建立与分析实现解耦的 `AnalysisService` 稳定接口并用 Fake 隔离；输出提交使用同目录临时文件与最终替换策略。
- **TDD 闭环：** (1) 先启用 CLI 非法输入/覆盖验收；(2) 确认错误发生在 Fake service 被调用前；(3) 为每种校验和原子提交拆单测；(4) Red → Green → Refactor；(5) 运行 CLI intake 集成；(6) 回归 Unit 1 与已有 CLI；(7) 无半成品、无静默覆盖后关闭；(8) 进入 Unit 3。
- **集成验证：** 使用临时目录模拟权限/冲突；fault injection 在第二个产物提交失败时验证旧产物保持一致。
- **回归范围：** Unit 1 CLI contract、两套现有 CLI import/帮助测试、顶层 smoke。
- **完成标准：** S2-S4 全部通过；Fake 能证明合法请求只调用一次、非法请求零调用。
- **风险与注意事项：** 不把原始日志内容写入错误信息；不得以 mock 文件系统替代关键原子替换集成验证。

### Unit 3 — 确定性 EVB 日志清洗、命令提取与证据索引

- **Unit 目标：** 将原始单次 EVB 日志转换为稳定的结构化事件流，正确识别 modemcli 会话和实际业务命令，并生成可回指原文的 evidence refs。
- **对应 Scenario：** S5、S6、S11、S13。
- **外部可观察结果：** 对固定 fixture，输出的命令、模块、时间戳、原始行号/位置和 evidence refs 稳定；ANSI 控制符不会污染命令。
- **输入与输出：** 输入 EVB 字节/文本与来源名；输出规范化事件、命令事件、解析警告和证据索引，不含诊断结论。
- **可依赖的已完成能力：** Unit 1 contracts、Unit 2 validated request。
- **明确禁止依赖的未来能力：** 不依赖业务状态机、Agent 推理、控制日志或 renderer。
- **计划文件：** 创建 `src/modem_log_analyzer/{log_parser.py,evidence.py,command_catalog.py}`，充实 `knowledge/modemcli_commands.yaml`；创建 `tests/unit/{test_log_parser.py,test_evidence.py,test_command_catalog.py}` 与脱敏的 `tests/fixtures/evb/`。
- **验收测试：** 从代表性 fixture 提取 `debug_bes_rpc 1 0`、SMS、Call、Ping、ifconfig；证明 modemcli 是会话入口不是业务动作；未知命令保留为 unknown；证据 raw_text 与源位置一致。项目级 command catalog 以用户提供的命令说明为事实来源，经人工校对后固化并保留来源版本说明。
- **需要拆分的单元测试：** ANSI/CRLF/空行、双时间戳、模块标签、命令重复回显、畸形 UTF-8、超长行、缺时间戳、unknown RPC 参数、稳定 evidence-ref 生成。
- **Red 预期失败原因：** 尚无 normalizer、catalog 或 evidence index。
- **最小实现范围：** 单遍确定性 parser + 数据驱动命令 catalog；不把领域结论硬编码进正则。
- **TDD 闭环：** (1) 启用 parser 验收 fixture；(2) 确认缺 parser 而失败；(3) 按 normalizer/line parser/catalog/evidence 拆单测；(4) 每项 Red → Green → Refactor；(5) 运行 preprocessing 集成；(6) 回归 CLI 输入和 schema；(7) 加 property-based/fuzz 后关闭；(8) 进入 Unit 4。
- **集成验证：** 对同一文件重复解析得到相同事件与 evidence refs；随机 ANSI/换行变体不改变命令语义。
- **回归范围：** Unit 1-2；命令表变更必须运行全部 parser fixtures。
- **完成标准：** S5 的所有提取断言通过；fuzz 输入不崩溃、不越界、不伪造位置。
- **风险与注意事项：** 原日志不可改写；清洗文本仅用于匹配，正式证据必须保留原始行；命令知识是项目资产，不从用户全局 skill 加载。

### Unit 4 — 四类业务状态语义与结构化诊断 Agent

- **Unit 目标：** 建立 Call、SMS、Data/Ping、Setting 的最小状态语义，并让主 Agent 委派单一职责 diagnostician subagent，返回受 schema 约束的诊断草案。
- **对应 Scenario：** S6、S7、S11、S12、S13、S16。
- **外部可观察结果：** 标注 fixture 获得正确的业务动作、预期状态、首个异常、分类候选、根因链和置信度；未知/缺失状态降级而非猜测。
- **输入与输出：** 输入 Unit 3 事件包、可选用户目标；输出 `AnalysisResult` 草案，不写文件。
- **可依赖的已完成能力：** Unit 3 结构化事件与 evidence index。
- **明确禁止依赖的未来能力：** 不依赖控制日志补充、最终 renderer、gateway；不得调用通用 shell/文件/Git 工具。
- **计划文件：** 创建 `src/modem_log_analyzer/{domain.py,scenario_inference.py,classification.py,analysis_service.py}`；修改 `agent.py`、`state.py`、`subagents.py`、`prompts.py`、`tools.py` 和 `docs/PROMPT.md`；创建对应 unit/integration 测试及四类业务 fixture。
- **验收测试：** 每类至少一个确认异常与一个证据不足样例；混合场景保持子流程边界；诊断只可引用输入 evidence refs；classification 遵守 R13/R14。
- **需要拆分的单元测试：** 各业务最小状态转换、首异常排序、因果链缺口、置信度规则、分类互斥、非法 evidence ref 拒绝、subagent task 路由和工具数 ≤5。
- **Red 预期失败原因：** 只有语法事件，没有业务状态、Agent graph 或诊断 schema 校验。
- **最小实现范围：** 数据驱动状态语义 + 一个 diagnostician subagent；主 Agent 负责装配与校验，不引入 sub-subagent。默认不做跨轮比较；只有用户显式提供至多一份正常对照时，才通过独立 baseline policy 提取差异，且对照不能覆盖目标执行自身证据。
- **TDD 闭环：** (1) 启用四类结构化诊断验收；(2) 确认因业务语义缺失失败；(3) 按状态/分类/引用/路由拆单测；(4) Red → Green → Refactor；(5) 用固定模型替身运行 Agent 集成；(6) 回归 parser 和公共 schema；(7) 所有分类都有反例后关闭；(8) 进入 Unit 5。
- **集成验证：** 固定模型替身返回缺字段、非法分类、虚假 evidence ref 时，服务必须拒绝并降级/重试到有界失败，不得进入 renderer。
- **回归范围：** Unit 1-3、prompt 静态约束、no-push/no-global-skill 测试。
- **完成标准：** 四类与混合 fixture 的专家标注字段逐项匹配；Agent/subagent 无危险工具；`docs/PROMPT.md` 已记录初版提示词。
- **风险与注意事项：** 不以 LLM 自由文本作为 SSOT；状态模型只覆盖已验证标记，未知平台细节留为 uncertainty。

### Unit 5 — 控制脚本日志按需请求、interrupt 与恢复

- **Unit 目标：** 当 EVB 证据无法解释 FAIL 时暂停并交互请求同次控制日志；支持补充后恢复或拒绝后降级完成。
- **对应 Scenario：** S8、S9、S10、S14。
- **外部可观察结果：** CLI 明确提示为什么需要控制日志；用户提供合法路径后同 thread 恢复；拒绝后仍生成结构化结果；不同 thread 隔离。
- **输入与输出：** 输入 EVB 初诊结果和可选控制日志；输出恢复后的 AnalysisResult 或诚实降级结果。
- **可依赖的已完成能力：** Unit 4 Agent graph、classification 和 validated request。
- **明确禁止依赖的未来能力：** 不依赖 Markdown renderer、gateway 或测试源码。
- **计划文件：** 创建 `src/modem_log_analyzer/{control_log_parser.py,control_log_policy.py}`；修改 `agent.py/state.py/cli.py/checkpointer.py/interrupts.py`；创建 `tests/unit/test_control_log_policy.py`、`tests/integration/test_interrupt_resume.py`。
- **验收测试：** 无控制日志且达到请求阈值触发 interrupt；提供路径恢复；选择继续；错误路径可重试；直接证据才允许 TEST_AUTOMATION_FAILURE_CONFIRMED；thread A 恢复不影响 B。
- **需要拆分的单元测试：** 请求门槛、直接证据判定、非法路径、重复 resume、已提供 control log 不重复请求、本地/生产 checkpointer 选择。
- **Red 预期失败原因：** 图没有 interrupt 节点/恢复协议，CLI 也无法处理暂停状态。
- **最小实现范围：** 一个有类型的“需要控制日志”interrupt；本地 MemorySaver、生产 PostgresSaver 工厂；不构建通用问答系统。
- **TDD 闭环：** (1) 启用 interrupt/resume 验收；(2) 确认图直接结束或状态丢失；(3) 拆 policy/checkpointer/resume 单测；(4) Red → Green → Refactor；(5) 运行双 thread 集成；(6) 回归 Unit 1-4；(7) 恢复/拒绝/错误三路都闭环后关闭；(8) 进入 Unit 6。
- **集成验证：** 使用真实 MemorySaver 跑完整 pause/resume；Postgres 使用接口契约替身，不伪装成真实数据库 E2E。
- **回归范围：** Agent graph、classification、CLI intake、prompt/interrupt 文档。
- **完成标准：** S8-S10/S14 通过且无跳过；生产 URL 设置时绝不静默使用 MemorySaver。
- **风险与注意事项：** MemorySaver 不承诺跨进程恢复；CLI 同进程交互是本地主路径，跨进程/生产恢复依赖 PostgresSaver并需在 README 明示。

### Unit 6 — 确定性 report.md 与 analysis.json 渲染

- **Unit 目标：** 从已校验 AnalysisResult 确定性生成两种一致产物和简洁终端摘要。
- **对应 Scenario：** S1、S7、S9-S13。
- **外部可观察结果：** `report.md` 章节顺序固定、`analysis.json` schema 合法、正文事实可映射到正式证据索引、摘要不泄露完整敏感值。
- **输入与输出：** 输入校验后的 AnalysisResult；输出临时 MD/JSON、提交后的最终产物和终端摘要。
- **可依赖的已完成能力：** Unit 2 原子提交，Unit 4-5 最终结构化结果。
- **明确禁止依赖的未来能力：** 不依赖 gateway、LangSmith evaluator 或真实 LLM 在线可用性。
- **计划文件：** 创建 `src/modem_log_analyzer/report.py`；修改 `analysis_service.py/cli.py/contracts.py`；创建 `tests/unit/test_report_renderer.py`、`tests/integration/test_cli_analyze.py`、`tests/acceptance/test_cli_contract.py` 的完整主路径断言及 `tests/fixtures/reports/`。
- **验收测试：** 六种 classification 均可渲染；有/无标识、有/无根因链、有/无控制日志；缺 evidence ref 时拒绝输出；两个产物一致；终端仅摘要。
- **需要拆分的单元测试：** 章节顺序、表格 escaping、Unicode、证据索引去重、敏感值终端遮蔽、schema version、原子双产物提交。
- **Red 预期失败原因：** 尚无 renderer，CLI 合法路径无法产生最终产物。
- **最小实现范围：** 模板化/程序化 renderer，不让 LLM直接写 Markdown；golden 只锁定公共结构与关键字段，避免脆弱全文 snapshot。
- **TDD 闭环：** (1) 启用 S1 完整验收；(2) 确认缺产物失败；(3) 拆 MD/JSON/summary/atomic 单测；(4) Red → Green → Refactor；(5) 跑离线 CLI 主路径集成；(6) 回归 Unit 1-5；(7) differential consistency 全绿后关闭；(8) 进入 Unit 7。
- **集成验证：** 同一 AnalysisResult 两次渲染核心字段一致；fault injection 不产生 MD/JSON 版本错配。
- **回归范围：** 全部 acceptance、schema、evidence、classification、interrupt。
- **完成标准：** S1/S7/S9-S13 中与产物相关断言全绿；不存在未经校验的正式证据。
- **风险与注意事项：** 原始证据可能含敏感值；报告本地保真与 trace/终端脱敏必须分层处理，不能修改 evidence raw_text 后再声称是原文。

### Unit 7 — 风险驱动测试、LangSmith 数据集与 evaluator

- **Unit 目标：** 用代表性标注数据证明四类业务、混合场景、parser 鲁棒性和核心诊断稳定性，并满足 prompt A/B 前置要求。
- **对应 Scenario：** S5-S7、S11-S13。
- **外部可观察结果：** 离线回归套件和 LangSmith evaluator 给出动作识别、首异常、分类、证据引用完整性等分项结果，而非只评价文风。
- **输入与输出：** 脱敏/合成 fixtures 与专家标注；输出测试结果和 evaluator 指标定义。
- **可依赖的已完成能力：** Unit 3-6 完整分析路径。
- **明确禁止依赖的未来能力：** 不依赖 gateway；不得把真实个人号码/设备标识提交到仓库或 LangSmith。
- **计划文件：** 创建 `agents/modem-log-analyzer/src/modem_log_analyzer/eval/`、`agents/modem-log-analyzer/tests/eval/datasets/`、`agents/modem-log-analyzer/tests/fixtures/reference_case_52/{evb.log,control.log,expected.json}` 以及 property/fuzz/state-machine/differential 测试文件；更新 `agents/modem-log-analyzer/docs/PROMPT.md` A/B 记录与 `agents/modem-log-analyzer/docs/README.md` 评测说明。
- **验收测试：** Call/SMS/Data-Ping/Setting/mixed 各有标注样例；unknown、缺终态、多模块乱序、ANSI 变体；分类和 evidence 引用 exact-match，解释文本只做辅助评价。参考 case fixture 应保留 `auto_case_modem_52`/单次 loop 的数据激活、ifconfig、Ping、SMS 与控制侧 Ping 检查失败这一最小事件关系，但替换电话号码、IP、短信内容及不相关噪声；`expected.json` 的根因分类必须由工程师审核，不能由实现 Agent从控制日志的 `ERROR` 字样直接生成。
- **需要拆分的单元测试：** Hypothesis parser 属性、业务 state-machine 不变量、renderer differential、关键分类 mutation 候选。
- **Red 预期失败原因：** 当前 fixture 覆盖不足或 evaluator 尚不存在，不能量化成功标准。
- **最小实现范围：** 足以覆盖需求矩阵的最小脱敏数据集；不构建批量生产分析功能。本 Unit 只汇总跨场景 evaluator 和补充此前无法单独证明的整体稳定性，不允许把 Unit 3-6 各自必需的 parser、状态机、分类、interrupt 或 renderer 测试债务推迟到这里。
- **TDD 闭环：** (1) 先提交标注与 evaluator 验收；(2) 运行确认暴露真实覆盖缺口；(3) 将缺口拆为最小单测；(4) Red → Green → Refactor，仅修当前行为；(5) 运行 evaluator 集成；(6) 全量回归；(7) 指标/失败样例可追踪后关闭；(8) 进入 Unit 8。
- **集成验证：** 固定模型替身离线必过；真实模型 LangSmith A/B 作为发布前 E2E，失败不得用更新 golden 掩盖。
- **回归范围：** Agent 全包所有测试、根仓库测试、prompt/schema 兼容。
- **完成标准：** 所有计划内标注 fixture 通过；未达到的真实模型指标明确记录为发布阻塞或剩余风险。
- **风险与注意事项：** 测试数据必须脱敏；避免用同一模型生成并评判全部 ground truth。

### Unit 8 — Gateway、Studio、追踪与部署接入

- **Unit 目标：** 完成仓库宪法要求的 gateway/API、LangGraph Studio、LangSmith tracing 和构建接入，同时保持 CLI-first 与 JSON 契约一致。
- **对应 Scenario：** S14、S15、S16。
- **外部可观察结果：** `/agents` 可见新 Agent；授权路由可提交分析并读取状态/恢复中断；未授权拒绝；Studio 可加载图；构建描述有效。
- **输入与输出：** gateway 使用 multipart 上传或等价受管 artifact-id 契约，将文件限定在服务端为该 thread 创建的隔离暂存区；响应遵守 AnalysisResult schema，不返回原始日志全文。禁止客户端提交任意服务器绝对路径。
- **可依赖的已完成能力：** Unit 1-7 的稳定 agent/CLI/contracts。
- **明确禁止依赖的未来能力：** 不做批量 API、跨 Agent import、Web UI 或自动部署生产。
- **计划文件：** 修改 `gateway/api/registry.py`、`gateway/api/routers/__init__.py`、`gateway/api/main.py`（仅若列表行为需要）；创建 `gateway/api/routers/modem_log_analyzer.py` 与 gateway 测试；更新 `langgraph.json`、`tracing.py`、Dockerfile、`.env.example`。
- **验收测试：** registry 懒加载、鉴权拒绝、授权 upload/invoke、路径穿越与跨 thread artifact-id 拒绝、state/history/resume、终态清理、JSON 契约一致、trace payload 无原始日志/敏感标识。
- **需要拆分的单元测试：** gateway request mapping、错误码、lazy import failure、trace sanitizer、Postgres config failure。
- **Red 预期失败原因：** Agent 未注册、router 不存在、trace 与 API 契约未约束。
- **最小实现范围：** 模仿现有 `code_writer`/`compound_builder` router，避免新建通用 gateway abstraction。上传文件仅在 thread 处于运行或中断待恢复时保留；到达终态后按明确的服务端保留策略清理，清理失败必须可观测且不得跨 thread 复用。
- **TDD 闭环：** (1) 启用 API 契约/鉴权验收；(2) 确认 404/未注册；(3) 拆 mapping/sanitizer/import 单测；(4) Red → Green → Refactor；(5) 跑 gateway 集成与 Studio load；(6) 回归 CLI 和既有 routers；(7) build/trace 门禁满足后关闭；(8) 进入 Unit 9。
- **集成验证：** TestClient 或等价测试覆盖授权/未授权；LangGraph Studio 加载图；`langgraph build` 验证镜像描述但不执行生产部署。
- **回归范围：** gateway 既有路由、root tests、所有 Agent import、CLI 主路径。
- **完成标准：** S15/S16 通过；LangSmith trace 无原文泄露；checkpointer 配置符合本地/生产约束。
- **风险与注意事项：** gateway 文件访问/上传方式必须在实现时沿用现有安全边界；若现有 gateway 没有安全文件上传模式，使用明确受限的请求契约并记录后续任务，不得接受任意服务器绝对路径。

### Unit 9 — 文档、顶层回归与发布门禁

- **Unit 目标：** 完成交付文档、全仓结构/安全回归和真实主路径验证，使 Coding Agent 能宣布功能完成而非仅局部测试通过。
- **对应 Scenario：** S1-S16。
- **外部可观察结果：** 工程师可从 README 安装并运行 CLI、理解控制日志交互、分类边界、输出和隐私；仓库所有门禁通过。
- **输入与输出：** 已完成实现与测试；输出最终 docs、smoke/layout 更新、发布验证记录。
- **可依赖的已完成能力：** Unit 1-8 全部关闭。
- **明确禁止依赖的未来能力：** 不把批量分析、Web UI、测试源码分析或生产部署塞入收尾 Unit。
- **计划文件：** 更新 `agents/modem-log-analyzer/docs/{README.md,PROMPT.md,INTERRUPTS.md,MCP_AND_SKILLS.md}`、根 `README.md`、`scripts/smoke.sh`、`tests/test_atelier_layout.py`；必要时补齐部署/运维说明。
- **验收测试：** 文档示例作为 CLI smoke 执行；顶层结构断言 Agent 文件、console script、gateway 注册、无危险工具、仅项目级 Skills/MCP；真实 LangSmith trace 记录一次已脱敏 E2E。
- **需要拆分的单元测试：** 本 Unit 不新增业务规则；若收尾发现行为缺陷，必须回到对应测试层补 Red test 后修复，不能只改文档或 smoke 绕过。
- **Red 预期失败原因：** 顶层 smoke/layout 尚未认识新 Agent，文档使用路径与最终 CLI 可能不一致。
- **最小实现范围：** 文档和全仓接入验证；不顺手重构现有 Agent 或模板。
- **TDD 闭环：** (1) 启用最终 smoke/E2E 验收；(2) 确认因缺注册/文档契约失败；(3) 对发现的真实缺陷补最小测试；(4) Red → Green → Refactor；(5) 运行 Agent/gateway 集成；(6) 运行全仓回归；(7) 所有质量门禁与未验证项记录完毕后关闭；(8) 计划结束。
- **集成验证：** 从干净环境按 README 完成安装、离线 fixture 分析、控制日志 interrupt/resume、产物核验；Studio、gateway 和 build 均验证。
- **回归范围：** 根与三个 Agent 的 format/lint/typecheck/test、gateway tests、smoke、LangSmith evaluator、关键 E2E。
- **完成标准：** 所有 Unit 关闭；没有新增失败/skip；README、PROMPT 变更日志和实际行为一致；可提交 PR。
- **风险与注意事项：** 不自动 push；生产 `langgraph up`、K8s apply 或真实外部发布仍需人工授权和独立部署核验。

## 6. 最终质量门禁

- S1-S16 的计划内 Scenario 全部通过，并能从 Scenario 追踪到验收测试和需求 R1-R25。
- Agent 包、gateway 和顶层所有单元测试通过；无删除、削弱断言、`.only`、无解释 golden/snapshot 更新或新增 skip/xfail。
- parser 的 property-based/fuzz、业务 state-machine、报告 differential、原子写入 fault-injection 等风险驱动测试通过。
- 必要的 Agent/CLI/gateway 集成与契约测试通过；离线 CLI 主路径、interrupt/resume、授权 gateway 和标注业务集为少量关键 E2E。
- `report.md` 与 `analysis.json` 对同一诊断一致；所有关键结论引用真实 evidence refs；未知/缺失证据不被猜测为成功。
- `TEST_AUTOMATION_FAILURE_CONFIRMED` 仅由控制脚本日志直接证据触发；仅 EVB 日志不得确认自动化误报。
- format、ruff lint、mypy typecheck、pytest、root smoke、LangGraph Studio load、LangGraph build 全部通过。
- 本地 MemorySaver、生产 PostgresSaver、interrupt/resume、thread 隔离均验证；checkpointer 不可关闭。
- Agent 和 subagent 不暴露 bash、write_file、git_commit、git_push；输出覆盖需要显式授权；不读取全局 Skills/MCP。
- prompt 改动已同步 `docs/PROMPT.md` 并完成 LangSmith dataset A/B；trace 默认不含原始日志正文与完整敏感标识。
- `agents/modem-log-analyzer/docs/README.md` 覆盖安装、最小命令、可选控制日志、分类解释、产物、覆盖保护、隐私与故障排查。
- 全仓回归证明 code-writer、compound-builder 和既有 gateway 路由未受破坏。
- 所有执行期未知（真实平台新增日志标记、真实 Postgres 部署、真实模型指标波动）均记录为已验证、发布阻塞或明确剩余风险；不得用局部测试通过宣称全部完成。
- 永不 auto-push；PR 描述包含动机、改动概览、测试、风险、回滚和关联 issue。
