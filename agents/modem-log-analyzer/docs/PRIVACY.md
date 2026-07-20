# ModemLogAnalyzer —— 隐私与脱敏手册

> Plan §1 R trace privacy + fixture 脱敏规范。

## 1. 三层隐私边界

按敏感度从低到高：

| 层 | 内容 | 出现位置 | 是否脱敏 |
| --- | --- | --- | --- |
| **L1 — 终端摘要** | `classification` + `scenario` + `ref_id` 列表 | `report.render_terminal_summary` → CLI stdout 前半段 | **是**（`_redact_phone_digits`） |
| **L2 — LangSmith trace** | LLM 调用的输入输出摘要 | 默认 `LANGSMITH_TRACING=false`；开启后由 deepagents 框架记录 | **是**（默认不传 raw_text；详见 §3） |
| **L3 — 报告产物** | 完整 `report.md` + `analysis.json`，含 `raw_text` | `atomic_write_artifacts` → 用户指定 `output_dir` | **否**（本地保真，文档要求） |

## 2. L1 终端摘要脱敏规则

`report.py:_redact_phone_digits()` 替换规则（按顺序执行）：

| 模式 | 替换文本 | 示例 |
| --- | --- | --- |
| `460\d{10,}` | `[IMSI]` | `460123456789012` → `[IMSI]` |
| `1[3-9]\d{9}` | `[PHONE]` | `13900001234` → `[PHONE]` |
| `\d{10,}` | `[REDACTED]` | `1234567890` → `[REDACTED]` |

**断言测试**：`tests/integration/test_cli_analyze.py::test_cli_terminal_summary_does_not_leak_phone` 验证摘要不含完整电话号码。

**已知盲区**：
- 国际号码 `+\d{1,3}\d{8,}` 未匹配（建议加）。
- IMEI `352099001761481` 等 14-15 位数字走 `[REDACTED]`。
- IMEISV `3520990017614816` 同上。

## 3. L2 LangSmith Trace 策略

按 Plan §1，trace 默认**只记录结构化摘要和指标**，不上传原始日志正文或号码、IMSI、ICCID、IMEI。

### 3.1 默认行为

- `tracing.init_tracing()` 仅在 `LANGSMITH_TRACING=true` **且** `LANGSMITH_API_KEY` 设置时启用。
- 未启用时 LLM 调用走 `claude-haiku-4-5-20251001` 默认 client，无 trace 副作用。
- deepagents 框架会在 trace 中记录 input/output；本 Agent 的 prompt 模板不显式嵌入 EVB 日志。

### 3.2 真实 LLM 接入时

`AnalysisService.run_analyze` 的 prompts 不直接拼 raw_text（Plan §2 锁定）；LLM 看到的是 `events` + `evidence_refs`（含 raw_text 但仅作为 schema 输入）。建议审查：
- 上线前在 LangSmith UI 抽样 10 个 trace，确认输入不含完整号码。
- 若发现，自动用 `LLM_PROVIDERS.md` 模板加脱敏中间件。

## 4. L3 报告产物设计

`report.md` 与 `analysis.json` **本地保真**，即 `evidence_refs[*].raw_text` 完整保存原日志原文。

**理由**：工程师必须能复核分析结果；脱敏会破坏可复核性（Plan §1 R9 R25）。

**约束**：
- 报告产物**只**写到用户通过 `--output` 显式提供的目录。
- Gateway 模式下写到 `<staging_dir>/<tid>/out/`（服务端隔离）。
- 不会自动上传到云端或外部服务。

### 4.1 Gateway 响应不含 raw_text

`AnalysisSummary` schema 仅暴露 `classification` / `confidence` / `scenario` / `evidence_ref_count` / `interrupt_request`，**不**返回 raw_text。客户端需要原文需显式 `GET /report` 或 `GET /state`。

### 4.2 trace / response 边界

| 通道 | 含 raw_text? |
| --- | --- |
| CLI `stdout`（终端摘要） | 否（脱敏） |
| CLI `stdout`（完整 JSON，第二个 `---` 之后） | **是**（含 raw_text 便于调试） |
| LangSmith trace input | 否（默认不开启 + LLM prompt 不显式拼 raw_text） |
| LangSmith trace output | 不含（LLM 只输出结构化 schema） |
| Gateway `AnalysisSummary` | 否 |
| Gateway `GET /report` | **是**（report.md 全文） |
| `report.md` 本地文件 | **是** |
| `analysis.json` 本地文件 | **是** |

## 5. Fixture 脱敏规范

仓库内的所有 fixture **必须**脱敏。脱敏规则（按顺序）：

| 字段 | 原始示例 | 脱敏后 |
| --- | --- | --- |
| 中国大陆手机号 | `13900001234` | `[PHONE_REDACTED]` |
| IMSI | `460123456789012` | `[IMSI_REDACTED]` |
| ICCID | `8986011785001234567` | `[ICCID_REDACTED]` |
| IMEI / IMEISV | `3520990017614816` | `[IMEI_REDACTED]` |
| 真实 IP | `192.168.1.10` | `[REDACTED]`（内部网 IP 仍可保留） |
| 真实地址 | `北京市朝阳区xx路` | `[ADDRESS_REDACTED]` |

### 5.1 自动化校验

`tests/test_atelier_layout.py::test_modem_log_analyzer_test_datasets_exist` 静态扫描 `reference_case_52/evb.log`，确保不含 `\b1[3-9]\d{9}\b` 或其他可疑长串。

新增 fixture 时，运行：

```bash
# 静态扫描
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src \
  .venv/bin/python -m pytest tests/test_atelier_layout.py -v

# 或手工
grep -E "\b1[3-9][0-9]{9}\b" tests/fixtures/*/evb.log     # 应无匹配
```

### 5.2 不应保留的字段

测试日志里**不应**出现：
- 真实的 SIM 卡 IMSI
- 真实的 IMEI
- 真实的电话号码（即使是开发手机）
- 任何可关联到个人的设备标识

## 6. 第三方模型接入的隐私边界

当模型替换为 OpenAI / 国内三方 / 自部署模型时：
- 默认 trace 由各 Provider 控制；本 Agent 不强制关闭。
- 建议在 `.env.example` 文档化 `LANGSMITH_TRACING=false` 作为部署默认值。

## 7. 数据库 / 文件系统边界

- `_THREAD_STAGING`：进程内字典，进程重启即丢；建议生产用 Redis TTL。
- `analysis.json` / `report.md` 落到本地 FS；服务端**不**额外持久化。
- `git status` 显示 `?? agents/modem-log-analyzer/...` 是因为 `.gitignore` 排除了 `output_dir`；确认 `.gitignore` 不漏：

```gitignore
# 仓库级 .gitignore 应包含:
**/output/
**/out/
**/*.log
```

## 8. 复盘检查清单

部署前由安全 / 隐私 review 跑：

- [ ] 默认 `LANGSMITH_TRACING=false`
- [ ] fixture 全部脱敏（自动化 + 手工）
- [ ] Gateway response 仅含 schema 字段，不含 raw_text
- [ ] CLI 终端摘要脱敏验证通过
- [ ] 报告产物路径由用户显式提供
- [ ] 无文件被自动上传到云端
- [ ] trace 抽样 10 个确认 LLM input 不含号码
- [ ] `.gitignore` 排除本地 output_dir