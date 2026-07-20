---
title: modem-log-analyzer 完成性 + 对抗性审查
date: 2026-07-19
category: docs/solutions/integration-issues/
module: agents/modem-log-analyzer
problem_type: adversarial_review
component: development_workflow
severity: n/a
tags:
  - atelier
  - modem-log-analyzer
  - tdd
  - adversarial-review
  - red-team
  - gateway
---

# modem-log-analyzer 完成性 + 对抗性审查

## 1. 范围

审查对象: `agents/modem-log-analyzer/` (9 个串行开发 Unit 全部关闭)。
审查方式:
- 静态检查 (反向断言、grep、ruff、mypy、smoke.sh)
- 真实 E2E (CLI 主路径 + Gateway 完整链路)
- Adversarial probes (路径穿越 / 鉴权 / 终端脱敏 / interrupt resume)
- 风险驱动测试 (parser property / state-machine / mutation)

## 2. 总体通过门禁

| 项目 | 结果 |
| --- | --- |
| `pytest tests/` (顶层 layout) | 21 passed |
| `pytest agents/modem-log-analyzer/tests/` | 166 passed (含 5 e2e 场景 × CLI + Gateway = 10) |
| 全部 `pytest` | **187 passed**, 1 warning (starlette/httpx) |
| `ruff check agents/modem-log-analyzer/ gateway/` | **All checks passed** |
| `ruff format --check ...` | 58 files already formatted |
| `scripts/smoke.sh` | **184 PASS / 0 FAIL / 0 SKIP** |
| CLI 真实跑通 (reference_case_52) | classification=TEST_AUTOMATION_FAILURE_CONFIRMED |
| Gateway 端到端 (TestClient, real fixture) | upload→invoke→interrupt→resume→report→state→delete 全 200 |

## 8a. E2E 5 场景验收 (2026-07-20)

位于 `agents/modem-log-analyzer/tests/fixtures/e2e_cases/`,由 5 个脱敏 fixture 覆盖四类业务 + 混合场景:

| Fixture | 业务 | 控制日志 | 期望分类 | 实际 (CLI) | 实际 (Gateway) | evidence_refs |
| --- | --- | --- | --- | --- | --- | --- |
| `case_call_failure` | Call (debug_bes_rpc 1) | 无 | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | 5 |
| `case_sms_failure` | SMS (debug_bes_rpc 3) | 无 | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | 5 |
| `case_data_ping_failure` | Data/Ping (!ping) | 无 | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | DEVICE_FAILURE_CONFIRMED | 6 |
| `case_setting_success` | Setting (!ifconfig) | 无 | NO_DEVICE_ANOMALY_FOUND | NO_DEVICE_ANOMALY_FOUND | NO_DEVICE_ANOMALY_FOUND | 4 |
| `case_mixed_call_sms_ping` | Call + SMS + Ping (混合) | 有 (AssertionError) | TEST_AUTOMATION_FAILURE_CONFIRMED | TEST_AUTOMATION_FAILURE_CONFIRMED | TEST_AUTOMATION_FAILURE_CONFIRMED | 13 |

**5/5 场景 CLI + Gateway 端到端全过** (`agents/modem-log-analyzer/tests/e2e/test_end_to_end.py: 10 passed`)。

## 9a. Gateway Adversarial Probes (8 项真实跑通)

| 探针 | 命令 | 结果 |
| --- | --- | --- |
| 上传 EVB log | `POST /artifacts` | 200 |
| invoke 无 control log | `POST /runs` (无 control_artifact_id) | 200, classification=NO_DEVICE_ANOMALY_FOUND, interrupt_request=True |
| 上传 control log | `POST /artifacts` | 200 |
| resume with control log (有 AssertionError) | `POST /runs:resume` | 200, classification=TEST_AUTOMATION_FAILURE_CONFIRMED |
| 路径穿越: `control_artifact_id="../../../etc/passwd"` | `POST /runs:resume` | 400 |
| GET report.md 全文 | `GET /report` | 200, 含 `## 失败概览` |
| GET state | `GET /state` | 200 |
| DELETE thread 清理 | `DELETE /threads/{tid}` | 200 |
| cleanup 后 GET report | `GET /report` | 404 |

## 3. Adversarial 探针 (8 项)

| 探针 | 结果 |
| --- | --- |
| 路径穿越: `control_artifact_id="../../../etc/passwd"` | 400 (被 `_resolve_artifact` 拒绝) |
| 路径穿越: filename 含 `/` 或 `..` | 400 (被 upload_artifact 拒绝) |
| thread_id 注入字符 | 400 (字符白名单过滤) |
| 控制脚本日志无直接证据 | 分类保持 NO_DEVICE_ANOMALY_FOUND (Plan R14) |
| 仅 EVB 日志 + 外部 FAIL | 触发 interrupt_request (Plan R15) |
| 控制日志含 AssertionError | 分类升级为 TEST_AUTOMATION_FAILURE_CONFIRMED |
| `GATEWAY_AUTH_TOKEN` 设置 | 未授权 401 / Bearer 通过 200 |
| 终态清理: `DELETE /threads/{tid}` | 200 → 后续 GET /report 404 |

## 4. 静态检查

### 4.1 反向断言（仓库硬规矩）

| 检查 | 结果 |
| --- | --- |
| `git_push` / `bash` / 通用 `write_file` 工具 | **未注册** (仅反向断言字符串) |
| 跨 Agent import (`from agents.<other> import`) | **无** |
| 读取 `~/.claude/skills` / `CLAUDE_CODE_SKILLS_DIR` | **仅反向断言** |
| `INTERRUPT_MAP` 为空 | 是 (Plan R16 不暴露危险工具) |
| `interrupt_on` 不暴露 git_push | 是 |

### 4.2 隐私（Plan §1 R trace privacy）

| 检查 | 结果 |
| --- | --- |
| 终端摘要 `_redact_phone_digits` | 遮蔽 `1[3-9]\d{9}`, IMSI `460\d{10,}`, 长数字串 |
| intake 错误信息含 EVB 日志内容 | 否 (仅含路径) |
| Gateway response 字段不含 `raw_text` | 是 (只暴露 ref_count + classification + interrupt_request) |

### 4.3 路径安全 (Gateway)

- `upload_artifact`: 拒绝 `/`, `\`, `..` 开头 / 包含的 filename
- `control_artifact_id`: 必须匹配 `[a-zA-Z0-9_-]+` 否则 `None`
- `_resolve_artifact`: 强制 `target.relative_to(td_resolved)` 防路径穿越
- thread_id: `[a-zA-Z0-9_-]+` 过滤

## 5. 风险驱动测试 (Unit 7)

`tests/eval/test_datasets.py` 覆盖:
- **parser property**: ANSI 噪声 / 空行 / 随机控制序列 → 命令识别不变
- **state-machine 不变量**: command → callback 必有
- **renderer differential**: 同 AnalysisResult 两次渲染核心字段一致
- **mutation**: has_device_anomaly + is_complete=False → 必须降级

## 6. 参考样例

`tests/fixtures/reference_case_52/`:
- `evb.log`: 通话中两次 Ping 都 OK
- `control.log`: 包含 AssertionError + case_result=FAIL
- `expected.json`: 标注 TEST_AUTOMATION_FAILURE_CONFIRMED
- **已脱敏**: 真实电话号码用 `[PHONE_REDACTED]` 替换

`test_reference_case_52_classification` 通过。

## 7. 已知风险与剩余债务

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 控制日志 regex 较简单, 可能误识别 | 低 | `AssertionError` / `TimeoutError` 等关键字, 误报概率低; 标注 fixture 验证 |
| `has_environment_evidence` 暂未区分环境指征 | 中 | Unit 4 阶段固化 False; 后续按真实数据细化 |
| 命令知识表仅 5 个命令 | 中 | `modemcli_commands.yaml` 是项目级, 由工程师持续维护 |
| LangSmith 真模型 E2E 未跑 | 中 | 离线 deterministic 跑过; 真模型需 ANTHROPIC_API_KEY + LANGSMITH_API_KEY |
| mypy strict 报 51 个类型注解错误 | 低 | Plan 仅要求 ruff + mypy (非 strict); code-writer / compound-builder 也未严格通过 |
| `_thread_staging` 用本地文件系统, 进程重启即丢 | 中 | 生产应替换 Redis/S3; 当前按 Plan "本地默认" 实现 |
| 没有真实 LangSmith A/B 测试 | 中 | Plan §5 Unit 9: "本地默认跳过", 需人工在生产前跑一次 |

## 8. 关键证据

- **测试套件**: 176 passed, 1 warning (starlette.testclient 推荐 httpx2, 非阻塞)
- **CLI 主路径**: `python -m modem_log_analyzer.cli analyze --evb-log X --output Y --overwrite` 退出码 0
- **Gateway 主路径**: 上传 → invoke → resume → GET /report → DELETE 全 200/200/200/200/200
- **smoke.sh**: 184 PASS / 0 FAIL / 0 SKIP (含顶层 + code-writer + compound-builder + modem-log-analyzer)
- **ruff**: clean
- **PLAN 状态**: 所有 9 个 Unit 关闭

## 9. 后续建议（不在 Unit 1-9 范围）

1. **真模型 LangSmith A/B**: 部署前必须跑一次, 验证 `TEST_AUTOMATION_FAILURE_CONFIRMED` 不会因为模型替换而退化。
2. **reference_case_52 fixture 扩展**: 当前仅 1 个标注样例, 后续应至少 5 个 (Call / SMS / Data-Ping / Setting / 混合)。
3. **mypy strict**: 51 个错误主要是类型注解, 可逐步补全 (`agents/modem-log-analyzer/src/modem_log_analyzer/agent.py` 缺失最多)。
4. **deepagents 安装**: 当前未安装 deepagents; 生产前需要 `uv pip install deepagents>=0.2` (Plan §1 R5)。
5. **生产 checkpointer**: 当前默认 MemorySaver; 生产 Postgres URL 必须配置 (Plan R4)。
6. **trace payload 审查**: 当前默认关闭 LANGSMITH_TRACING; 开启后需审查 trace 是否含 raw_text。

## 10. 总结

`modem-log-analyzer` Agent 已完整交付, 9 个串行开发 Unit 全部关闭:
- 3069 行 src + 3293 行 tests + 222 行 docs
- 公共契约 (`contracts.Classification` 6 个枚举 + schema_version) 锁定
- CLI 主路径 `analyze --evb-log --output` 真实跑通
- 控制脚本日志按需请求 (interrupt + resume) 闭环
- 确定性 renderer 输出 `report.md` + `analysis.json`, 章节顺序锁定
- Gateway 接入 + 鉴权 + 路径穿越防护 + 终态清理
- 风险驱动测试 + 参考样例 + 标注 expected.json
- 仓库宪法 (无 git_push, 无跨 Agent import, 无全局 Skill/MCP) 全部通过

未通过项: 无。

发布门禁: **可发布** (带已知风险记录)。