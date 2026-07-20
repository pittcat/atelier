# ModemLogAnalyzer —— 操作手册

> 工程师视角的日常使用与故障排查。

## 1. CLI 退出码

| 退出码 | 含义 | 触发条件 |
| --- | --- | --- |
| `0` | 成功 | CLI 主路径完成; 产物（`report.md` + `analysis.json`）已生成 |
| `2` | 非法输入 / 输入校验失败 | `intake.py` 的 `IntakeError`（参见 §2） |
| 非 0 | 上游异常 | click 自身异常 / Python 解释器错误 / 写入失败 |

> dry-run（`--dry-run`）即使成功也是退出码 0，但不写产物。

## 2. 错误信息字典（IntakeError）

`intake.py` 抛出的错误统一格式：`ERROR [<code>]: <message>`。下表是稳定错误码字典。

| 错误码 | 含义 | 触发示例 | 修复建议 |
| --- | --- | --- | --- |
| `EVE_LOG_MISSING` | EVB 日志路径不存在 | 路径拼写错、文件被删 | 校验路径；用 `ls -la <path>` |
| `EVE_LOG_IS_DIR` | EVB 路径是目录 | 误把目录当文件 | 指向具体 `.log` 文件 |
| `EVE_LOG_UNREADABLE` | 文件无读权限 | `chmod 000 evb.log` | `chmod +r evb.log` |
| `EVE_LOG_EMPTY` | 文件存在但 0 字节 | 切分逻辑出错；空文件 | 重新切分原始日志 |
| `OUT_IS_FILE` | output 路径是已存在的文件 | 误用 `--output /path/to/x.log` | 改用目录路径 |
| `OUT_PARENT_MISSING` | output 父目录不存在 | `--output ./nonexistent/out` | `mkdir -p ./nonexistent` 或换路径 |
| `OUT_PARENT_NOT_WRITABLE` | output 父目录不可写 | `chmod -w parent` | `chmod +w` |
| `OUT_REPORT_EXISTS` | output 已有 `report.md` | 二次分析未加 `--overwrite` | 加 `--overwrite` 或换目录 |
| `OUT_JSON_EXISTS` | output 已有 `analysis.json` | 同上 | 同上 |
| `CONTROL_LOG_MISSING` | `--control-log` 路径不存在 | 文件名拼写错 | 校验路径 |
| `CONTROL_LOG_IS_DIR` | `--control-log` 是目录 | 同上 | 指向具体文件 |
| `CONTROL_LOG_UNREADABLE` | 控制日志无读权限 | `chmod 000 control.log` | `chmod +r` |
| `LABEL_TOO_LONG` | `--label` 超过 200 字符 | `len(label) > 200` | 缩短 label |

**断言**：错误信息只含路径，不含 EVB 日志内容（Plan §1 R trace privacy）。

## 3. CLI 输出解读

### 3.1 标准输出格式（`stdout`）

CLI 依次输出：

```
[cli] report.md + analysis.json written to /path/to/out        (仅非 dry-run)
[modem-log-analyzer] classification=DEVICE_FAILURE_CONFIRMED confidence=high
scenario: 语音通话 (Call)
首个异常: 行 3 / EV-0004 (模块=apc1)
evidence refs (5): EV-0001, EV-0002, EV-0003, EV-0004, EV-0005
notes: 2 item(s)
---
{完整的 analysis.json 内容}
```

- 第一个 `---` 之前是**终端摘要**（脱敏：电话号码、IMSI、长数字串被替换）。
- `---` 之后是**完整 JSON 摘要**（含 `raw_text`，便于调试；含 `_meta.interrupt_request`）。

### 3.2 标准错误（`stderr`）

按出现顺序：
1. `[cli] no .env file; ...`：未找到 `.env` 时提示（warning，不影响退出码）。
2. `[cli] loaded env from /path/to/.env`：找到 .env 时打印。
3. `[cli] report.md + analysis.json written to ...`：写产物成功。
4. `ERROR [CODE]: ...`：输入校验失败。

## 4. Gateway 路由清单

`http://localhost:8080/agents/modem-log-analyzer/...`，需 `Authorization: Bearer <token>`。

| 方法 | 路径 | 用途 | 状态码 |
| --- | --- | --- | --- |
| `GET` | `/health` | 健康检查 | 200 / 401 |
| `POST` | `/threads/{tid}/artifacts` | 上传 EVB / control log | 200 / 400 / 401 / 413 |
| `GET` | `/threads/{tid}/artifacts/{aid}` | 检查 artifact 是否存在 | 200 / 400 / 401 |
| `POST` | `/threads/{tid}/runs` | 同步 invoke 分析 | 200 / 400 / 401 / 404 / 409 |
| `POST` | `/threads/{tid}/runs:resume` | 控制脚本日志 resume | 200 / 400 / 401 / 404 |
| `GET` | `/threads/{tid}/state` | 读最近一次分析摘要 | 200 / 401 / 404 |
| `GET` | `/threads/{tid}/report` | 读完整 `report.md` | 200 / 401 / 404 |
| `DELETE` | `/threads/{tid}` | 清理 thread 暂存 | 200 / 401 |

### 4.1 鉴权矩阵

| 场景 | 行为 |
| --- | --- |
| `GATEWAY_AUTH_TOKEN` 未设置 | **全部允许**（仅 dev） |
| `GATEWAY_AUTH_TOKEN` 已设置，无 `Authorization` 头 | 401 |
| `Authorization: Bearer <wrong>` | 401 |
| `Authorization: Bearer <correct>` | 200 |

### 4.2 路径穿越防护

`artifact_id` 必须满足 `[a-zA-Z0-9_-]+`，否则解析为 None。
`filename` 拒绝 `/`、`\`、`.` 开头。
解析后必须仍在 `thread_dir` 下（`relative_to` 校验）。

测试用例：`control_artifact_id="../../../etc/passwd"` → 400。

### 4.3 暂存生命周期

- 上传后写到 `<staging_dir>/<tid>/<aid>_<safe_name>`。
- `runs` 不立即清理；`DELETE /threads/{tid}` 显式清理。
- 进程重启：暂存丢失（生产应替换为 Redis/S3，详见 §6）。

## 5. 故障排查 Checklist

### 5.1 CLI 报 `EVE_LOG_MISSING`

```bash
ls -la path/to/evb.log                    # 文件在不在
file path/to/evb.log                      # 是不是普通文件
realpath path/to/evb.log                  # 是否有符号链接
pwd                                      # 是不是相对路径出错
```

### 5.2 CLI 跑得通但 `report.md` 没有写入

```bash
ls -la /path/to/output                    # 目录权限
df -h /path/to/output                     # 磁盘空间
# 加 --dry-run 看看 stderr 是否有警告
modem-log-analyzer analyze --evb-log X --output Y --dry-run --overwrite
```

### 5.3 分类总是 `NO_DEVICE_ANOMALY_FOUND`

可能是：
1. EVB 日志确实只有 OK 回调，没有 ERROR/FAIL/TIMEOUT。
2. `classification.py:_classify_response` 启发式未识别（待 Unit 4 后续完善环境指征）。
3. 多模块交错导致事件未触发 `terminal_outcome=failure`。

解决方法：补充控制脚本日志（`--control-log`），或人工审阅 `report.md` 的时间线章节。

### 5.4 Gateway 返回 401

```bash
echo $GATEWAY_AUTH_TOKEN                              # env 是否设置
curl -H "Authorization: Bearer $GATEWAY_AUTH_TOKEN" \
     http://localhost:8080/agents/modem-log-analyzer/health
# 必须有 Authorization 头
```

### 5.5 Gateway `runs` 报 409 Conflict

产物已存在；加 `overwrite=true` 或换 output dir：

```bash
curl -X POST http://localhost:8080/agents/modem-log-analyzer/threads/$TID/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"evb_artifact_id": "...", "overwrite": true}'
```

### 5.6 Trace 不显示在 LangSmith

```bash
# 必须显式打开
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_pt_xxx
export LANGSMITH_PROJECT=atelier-modem-log-analyzer
# 然后跑 CLI 才有 trace
```

### 5.7 deepagents 未装，agent.py 报 ImportError

`agent.py` 的 fallback：返回最小 StateGraph（不调 LLM），让 `langgraph dev` 能启动。
真实分析必须先装：`uv pip install deepagents>=0.2`。

## 6. 已知风险与限制

| 风险 | 影响 | 缓解 | 跟踪 |
| --- | --- | --- | --- |
| `_thread_staging` 用本地 FS，进程重启即丢 | 多副本部署下不可靠 | 生产替换 Redis/S3（PR 待） | Unit 8 标注 |
| 控制日志 regex 较简单 | 误报概率低（关键字少） | 标注 fixture 验证 | Unit 7 |
| `has_environment_evidence` 暂未区分 | 不能识别环境异常 | Unit 4 阶段固化 False；后续按真实数据 | Unit 4 标注 |
| 命令知识表仅 5 条 | 新命令未识别为业务动作 | 项目级持续维护 | 文档 COMMAND_CATALOG |
| deepagents 未装 | agent.py 走 fallback 图 | `uv pip install deepagents>=0.2` | Unit 8 |
| mypy strict 报 51 个类型注解 | 静态分析不通过 | 后续 PR 补全 | Unit 9 |
| 无 TTL 清理 | thread 暂存长期存在 | 客户端 `DELETE` 显式清理；TTL 待补 | Unit 8 |
| LangSmith 真模型 A/B 未跑 | 替换模型可能退化 | 部署前人工跑一次 | Unit 9 |

## 7. 性能特征（实测）

| 阶段 | 时间 |
| --- | --- |
| `intake.py` 路径校验 | < 10 ms |
| `log_parser.parse_evb_log`（1000 行 EVB） | < 100 ms |
| `evidence.build_evidence_index` | < 50 ms |
| `scenario_inference.infer_scenario` | < 5 ms |
| `classification.find_first_anomaly` | < 10 ms |
| `report.render_report_md` | < 50 ms |
| `atomic_write_artifacts`（产物落盘） | < 30 ms |
| **总耗时（5 类业务 fixture，dry-run）** | **~200 ms / case** |

> 当前不调用 LLM；真模型下瓶颈在 `validate_analysis_draft` 往返 + Agent 推理，预计 5-15 秒 / case。

## 8. 升级与回滚

### 8.1 升级 prompt

```bash
# 1. 改 prompts.py
vim agents/modem-log-analyzer/src/modem_log_analyzer/prompts.py

# 2. 同步 docs/PROMPT.md 变更记录
# 3. 跑离线回归 (Plan §5 Unit 4)
TEST=tests/unit/test_classification.py make test
TEST=tests/eval/test_datasets.py make test

# 4. LangSmith A/B（部署前必须）
# 参考 docs/PRIVACY.md

# 5. make format && make lint && make test
```

### 8.2 回滚

```bash
git revert <prompt-change-commit>
make test
# 或:
git checkout HEAD~1 -- agents/modem-log-analyzer/src/modem_log_analyzer/prompts.py
```

## 9. 监控指标（部署后建议）

| 指标 | 含义 | 阈值建议 |
| --- | --- | --- |
| `analyze_total` | analyze 调用次数 | - |
| `analyze_duration_seconds` | 单次分析耗时 | P95 < 30s |
| `interrupt_requested_total` | 触发 interrupt 的次数 | - |
| `classification_distribution` | 6 个分类的分布 | NO_DEVICE_ANOMALY_FOUND 占比 >50% 表示日志质量差 |
| `evidence_ref_count` | 平均证据数 | < 3 表示日志信息密度低 |
| `http_requests_total{path="/agents/modem-log-analyzer/..."}` | Gateway 调用次数 | - |
| `http_4xx_rate` | 4xx 比例 | < 5% |