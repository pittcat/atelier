# ModemLogAnalyzer —— 触发中断的工具与流程

> Plan §1 R15-R16 + §5 Unit 5：控制脚本日志按需请求的 interrupt 协议。

## 1. 工具 / 流程矩阵

按 `interrupts.py` 与 AGENTS.md 第三节：

| 工具 / 流程          | 允许的人工决策               | 原因 |
|---------------------|----------------------------|------|
| `bash`              | **不暴露**                  | 只读分析 Agent 无 shell 权限 |
| `write_file` / `edit_file` | **不暴露**             | 报告产物由 CLI 直接生成 |
| `git_commit`        | **不暴露**                  | 分析任务不提交代码 |
| `git_push`          | **不暴露**                  | 永远人工，且不在 Agent 工具集 |
| 控制脚本日志请求    | approve / 拒绝              | Unit 5 接入的 LangGraph interrupt |

**INTERRUPT_MAP 当前为空**（`src/modem_log_analyzer/interrupts.py`），因为本 Agent 不暴露任何工具。控制日志请求走 `LangGraph interrupt()` 函数式协议，不通过 `interrupt_on` 工具列表。

## 2. 控制脚本日志请求协议（Unit 5 锁定）

### 2.1 触发条件

```python
# control_log_policy.should_request_control_log(
#     first_anomaly=...,
#     classification=...,
#     has_control_log=...,
# )
```

返回 `True`（应该请求）的条件：

| first_anomaly | classification | has_control_log | 返回 |
| --- | --- | --- | --- |
| None | NO_DEVICE_ANOMALY_FOUND | False | **True** |
| None | DEVICE_EVIDENCE_INCOMPLETE | False | True |
| not None | - | - | False |
| - | DEVICE_FAILURE_CONFIRMED | - | False |
| - | - | True | False |

### 2.2 Interrupt Payload

由 `build_interrupt_request(reason)` 构造：

```python
{
    "type": "REQUEST_CONTROL_LOG",
    "why": "板端状态流看似正常或证据不足以解释外部 FAIL; 请提供同次执行的控制脚本日志, 或选择不提供 (诚实降级)。",
    "options": {
        "approve": "提供控制脚本日志路径",
        "reject": "不提供 (诚实降级)",
    },
}
```

### 2.3 Resume Payload

由 `build_resume_payload(control_log_path)` 构造：

```python
# 提供日志:
{"control_log_path": "/path/to/control.log"}

# 拒绝:
{"control_log_path": None}
```

### 2.4 升级路径

仅当用户 **提供** 控制脚本日志 **且** `has_direct_automation_evidence(control_events) == True` 时，分类升级为 `TEST_AUTOMATION_FAILURE_CONFIRMED`。

`has_direct_automation_evidence` 识别以下模式（regex）：

| 模式 | 说明 |
| --- | --- |
| `AssertionError` | 断言错误 |
| `TimeoutError` | 超时 |
| `assertion failed` | 断言失败（不区分大小写） |
| `expected ... got ...` | 期望值不匹配 |
| `case_result = FAIL` / `case_result: FAIL` | 显式 case 失败 |
| `Traceback` | Python traceback |
| `EXCEPTION` | 异常标记 |

否则保持原分类。

## 3. CLI 主路径中的 interrupt 集成

### 3.1 阶段 1：invoke 无 control log

```bash
modem-log-analyzer analyze --evb-log clean.log --output out/
```

`AnalysisService` 检测到需要 control log，**不抛错**——继续完成分析并写产物，`analysis.json._meta.interrupt_request` 含请求。

```json
{
  "classification": "NO_DEVICE_ANOMALY_FOUND",
  "_meta": {
    "interrupt_request": {
      "type": "REQUEST_CONTROL_LOG",
      "why": "..."
    }
  }
}
```

### 3.2 阶段 2：CLI 提示用户

> 当前 CLI 是**单进程同步调用**，interrupt 集成在后续 LangGraph Studio 工作流中。
> Plan §5 Unit 5 锁定：在 LangGraph Studio 中，interrupt 通过 `Command(resume=...)` 协议恢复。

未来 CLI 设计（待 Unit 5 后续）：

```
$ modem-log-analyzer analyze --evb-log clean.log
[cli] 检测到需要控制脚本日志; 板端正常无法解释外部 FAIL
[cli] 请选择:
  [a] 提供控制脚本日志路径
  [r] 不提供 (诚实降级)
> a /path/to/control.log
```

### 3.3 阶段 3：resume

```bash
# 走 LangGraph Studio 时:
python -c "
from modem_log_analyzer.agent import build_agent
agent = build_agent()
config = {'configurable': {'thread_id': 'adversarial-1'}}
result = agent.invoke(None, config=config)  # 触发 interrupt
# ...
result = agent.invoke(Command(resume={'control_log_path': '/path/to/control.log'}), config=config)
"
```

## 4. Gateway 中的 interrupt 集成

### 4.1 POST /runs（无 control log）

```bash
EID="..."
curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"evb_artifact_id\": \"$EID\"}"
```

返回：

```json
{
  "schema_version": "0.1.0",
  "classification": "NO_DEVICE_ANOMALY_FOUND",
  "root_cause_confidence": "high",
  "interrupt_request": {
    "type": "REQUEST_CONTROL_LOG",
    "why": "..."
  }
}
```

### 4.2 POST /runs:resume

```bash
curl -X POST "http://localhost:8080/agents/modem-log-analyzer/threads/$TID/runs:resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"control_artifact_id": "..."}'
```

返回：

```json
{
  "classification": "TEST_AUTOMATION_FAILURE_CONFIRMED",  // 或原分类
  "root_cause_confidence": "...",
  "interrupt_request": null
}
```

### 4.3 thread 隔离

每个 `thread_id` 的 interrupt 状态独立。`runs:resume` 只影响指定 thread。

## 5. 调试：手动触发 interrupt

### 5.1 直接调用 policy

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.control_log_policy import (
    should_request_control_log,
    build_interrupt_request,
    build_resume_payload,
)
print(should_request_control_log(
    first_anomaly=None,
    classification='NO_DEVICE_ANOMALY_FOUND',
    has_control_log=False,
))
# True

print(build_interrupt_request('test reason'))
print(build_resume_payload('/tmp/x.log'))
"
```

### 5.2 检查 interrupt_map

```bash
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.interrupts import INTERRUPT_MAP
print(INTERRUPT_MAP)
# {}
"
```

## 6. 调整规则

新增工具前确认：

1. **是否必须？** 能用现有工具代替就别加。
2. **是否会让 Agent 越界？** 只读工具优先；写产物只在 CLI 内部。
3. **是否要在 `git` 系列里开 push？** 开就要有审计日志，且必须人工。

新增 interrupt 触发条件时：

1. **是否在 `should_request_control_log` 范围内？** Plan R15 锁定边界。
2. **是否对每个分类公平？** `NO_DEVICE_ANOMALY_FOUND` 和 `DEVICE_FAILURE_CONFIRMED` 不应请求；其它情形需要人工 review。
3. **是否有 E2E fixture 覆盖？** 新场景必须加到 `tests/fixtures/e2e_cases/`。

## 7. 反模式

| 反模式 | 后果 |
| --- | --- |
| Agent 自动"猜"控制日志路径 | 用户没机会拒绝；隐私违规 |
| 多个 interrupt 并发（同一 thread） | state 错乱 |
| 中断返回后不写入产物 | 后续 GET /report 看到旧版本 |
| 升级分类时不校验 `has_direct_evidence` | 仅路径存在就升级，违反 Plan R16 |