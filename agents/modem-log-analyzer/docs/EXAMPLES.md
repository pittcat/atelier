# ModemLogAnalyzer —— 用例与命令速查

> 5 个 e2e fixture 的输入/输出对比 + 完整命令参考。

## 1. E2E Fixture 速查

5 个 fixture 位于 `tests/fixtures/e2e_cases/`：

### 1.1 case_call_failure —— Call 业务失败

**输入**（`evb.log`）：
```
[2026-07-19 09:00:00.000][2026-07-19T01:00:00.000Z][ap] modemcli> debug_bes_rpc 1 [PHONE_REDACTED]
[2026-07-19 09:00:01.000][2026-07-19T01:00:01.000Z][apc1] OK dial request
[2026-07-19 09:00:05.000][2026-07-19T01:00:05.000Z][apc1] ERROR: dial failed SIP timeout
[2026-07-19 09:00:06.000][2026-07-19T01:00:06.000Z][apc1] FAIL case_result=FAIL
```

**期望**：
```json
{"classification": "DEVICE_FAILURE_CONFIRMED", "scenario_substring": "Call"}
```

**运行**：
```bash
modem-log-analyzer analyze \
  --evb-log tests/fixtures/e2e_cases/case_call_failure/evb.log \
  --output /tmp/out
```

**报告关键内容**：
- 场景：语音通话 (Call)，置信度 high
- 首异常：行 3 / EV-0004, `ERROR: dial failed SIP timeout`
- 业务动作：Call
- 根因链：trigger=dial failed → propagation=缺口 → terminal_impact=外部 FAIL

### 1.2 case_sms_failure —— SMS 业务失败

**输入**：`debug_bes_rpc 3 [PHONE] hello` + 板端 ERROR
**期望**：`DEVICE_FAILURE_CONFIRMED`, scenario=`短信 (SMS)`

**关键**：catalog 把 `debug_bes_rpc 3` 子命令映射为 `sms` 业务动作。

### 1.3 case_data_ping_failure —— Data/Ping 业务失败

**输入**：`!ifconfig` + `!ping 8.8.8.8` + `TIMEOUT no response`
**期望**：`DEVICE_FAILURE_CONFIRMED`, scenario=`数据/Ping (Data/Ping)`

**关键**：catalog 把 `!ping` 直接映射为 `data_ping` 业务动作。

### 1.4 case_setting_success —— Setting 业务成功

**输入**：两次 `!ifconfig` + `eth0 [REDACTED] up`
**期望**：`NO_DEVICE_ANOMALY_FOUND`, scenario=`未知场景`

**关键**：
- 板端无异常 → 自动触发 `interrupt_request`（建议用户补控制日志）
- 置信度 high（`NO_DEVICE_ANOMALY_FOUND` 是硬事实）

### 1.5 case_mixed_call_sms_ping —— 混合 + 控制侧误报

**输入 EVB**：
```
modemcli> debug_bes_rpc 1 [PHONE]   # 通话
modemcli> debug_bes_rpc 3 [PHONE] hi  # 通话中短信
!ping 8.8.8.8                         # 通话中 ping
hangup OK
!ping 8.8.4.4                         # 通话后 ping
```

**输入 control**：
```
[13:00:00] starting case mixed_loop_99
[13:01:31] AssertionError: expected latency < 20ms but got 14ms
[13:01:32] case_result FAIL
```

**期望**：`TEST_AUTOMATION_FAILURE_CONFIRMED`, scenario=`混合场景: call + data_ping/sms`

**关键**：
- 板端业务 OK，控制日志有 `AssertionError` → 直接证据 → TEST_AUTOMATION_FAILURE_CONFIRMED
- 业务动作：Call, Data/Ping, SMS（三种都被识别）

## 2. CLI 命令速查

### 2.1 最小调用
```bash
modem-log-analyzer analyze \
  --evb-log evb.log \
  --output out/
```

### 2.2 带控制日志 + label
```bash
modem-log-analyzer analyze \
  --evb-log evb.log \
  --control-log control.log \
  --output out/ \
  --label "loop_52"
```

### 2.3 覆盖已有产物
```bash
modem-log-analyzer analyze \
  --evb-log evb.log \
  --output out/ \
  --overwrite
```

### 2.4 只校验不写产物
```bash
modem-log-analyzer analyze \
  --evb-log evb.log \
  --output out/ \
  --dry-run
# stdout 仍输出 JSON 摘要; 不写 report.md / analysis.json
```

### 2.5 指定 thread id（与 checkpointer 关联）
```bash
modem-log-analyzer analyze \
  --evb-log evb.log \
  --output out/ \
  --thread "adversarial-test-1"
```

### 2.6 安静模式（stderr 抑制进度）
```bash
MODEM_LOG_ANALYZER_QUIET=true modem-log-analyzer analyze \
  --evb-log evb.log \
  --output out/
```

## 3. Gateway 调用速查

### 3.1 上传 EVB
```bash
TID=adversarial-test-1
TOKEN=$GATEWAY_AUTH_TOKEN

curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -F "artifact=@evb.log"
# 返回: {"artifact_id": "f8b5fba3...", "size": 679, "filename": "evb.log"}
```

### 3.2 触发 invoke（无 control）
```bash
EID=$(curl -s -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -F "artifact=@evb.log" | jq -r .artifact_id)

curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"evb_artifact_id\": \"$EID\", \"label\": \"case_52\"}"
# 返回:
# {
#   "schema_version": "0.1.0",
#   "classification": "NO_DEVICE_ANOMALY_FOUND",
#   "interrupt_request": {"type": "REQUEST_CONTROL_LOG", "why": "..."}
# }
```

### 3.3 上传 control + resume
```bash
CID=$(curl -s -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/artifacts" \
  -H "Authorization: Bearer $TOKEN" \
  -F "artifact=@control.log" | jq -r .artifact_id)

curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/runs:resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"control_artifact_id\": \"$CID\", \"evb_artifact_id\": \"$EID\"}"
# 返回:
# {
#   "classification": "TEST_AUTOMATION_FAILURE_CONFIRMED",
#   ...
# }
```

### 3.4 读取完整报告
```bash
curl "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/report" \
  -H "Authorization: Bearer $TOKEN" | jq -r .report_md | head -30
```

### 3.5 读取 state
```bash
curl "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/state" \
  -H "Authorization: Bearer $TOKEN"
# {"thread_id": "...", "state": {"classification": "...", "scenario": "...", ...}}
```

### 3.6 清理 thread
```bash
curl -X DELETE "http://localhost:8080/agents/modem-log-analyzer/threads/$TID" \
  -H "Authorization: Bearer $TOKEN"
# {"thread_id": "...", "status": "cleaned"}
```

### 3.7 健康检查
```bash
curl "http://localhost:8080/agents/modem-log-analyzer/health" \
  -H "Authorization: Bearer $TOKEN"
# {"status": "ok", "agent": "modem-log-analyzer"}
```

## 4. 报告样本（case_call_failure 完整 report.md）

```markdown
## 失败概览

- **运行标识**: case_call_failure
- **外部测试结果**: `FAIL`
- **推断场景**: 语音通话 (Call) (置信度: high)
- **诊断分类**: `DEVICE_FAILURE_CONFIRMED`
- **根因置信度**: `high`

## 推断的测试场景与基线
...

## 核心诊断
- **首个异常步骤**: 行 3 / EV-0004 (模块=apc1)
- **最可能原因**: ERROR: dial failed SIP timeout

## 根因链
- **trigger**: ERROR: dial failed SIP timeout
- **propagation**: 异常传播过程 (缺口)
- **terminal_impact**: 最终外部 FAIL

## 失败时间线
- `09:00:00.000` [ap] 命令 debug_bes_rpc 1 (业务=call)
- `09:00:05.000` [apc1] 板端回调 (outcome=failure)

## 正式证据索引
| EV-0001 | evb.log | 1 | ap    | 09:00:00.000 |
| EV-0004 | evb.log | 3 | apc1  | 09:00:05.000 |
```

## 5. Pytest 速查

### 5.1 跑全部测试
```bash
cd /Users/pittcat/Dev/Python/atelier
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/ tests/ -q
# 187 passed
```

### 5.2 跑单个测试
```bash
TEST=tests/unit/test_contracts.py make test    # Makefile 方式
PYTHONPATH=... .venv/bin/python -m pytest \
  agents/modem-log-analyzer/tests/unit/test_log_parser.py -v
```

### 5.3 跑 e2e
```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/e2e/ -v
# 10 passed (5 cases × CLI + Gateway)
```

### 5.4 跑独立 e2e 脚本
```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python scripts/e2e_modem_log_analyzer.py
```

## 6. dev / prod 切换

### 6.1 dev：MemorySaver + LangGraph Studio
```bash
cd agents/modem-log-analyzer
uv sync
cp .env.example .env  # 填 LLM Provider Key
make dev               # Studio: http://localhost:2024
```

### 6.2 prod：PostgresSaver + gateway
```bash
# 1. 启动 Postgres
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=xxx postgres:15

# 2. 配 env
export ATELIER_CHECKPOINTER_URL=postgresql://postgres:xxx@localhost:5432/atelier
export GATEWAY_AUTH_TOKEN=$(openssl rand -hex 32)

# 3. 启 gateway
make gateway
# 4. 启 Agent
make build AGENT=modem-log-analyzer
make up AGENT=modem-log-analyzer
```

### 6.3 切换 checkpointer
- **默认（无 ATELIER_CHECKPOINTER_URL）**：`MemorySaver`
- **设置 ATELIER_CHECKPOINTER_URL**：自动 `PostgresSaver`
- **langgraph-api 进程**（`LANGSMITH_LANGGRAPH_API_VARIANT`）：返回 None，让平台托管

⚠️ 不要关闭 checkpointer（AGENTS.md 硬规矩 4）。