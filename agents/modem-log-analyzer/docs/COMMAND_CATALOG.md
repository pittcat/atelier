# ModemLogAnalyzer —— 命令知识表

> Plan §1 R3：项目级 ModemCLI 命令词典。`modemcli_commands.yaml` 是单一来源。

## 1. 文件位置

```
agents/modem-log-analyzer/knowledge/modemcli_commands.yaml
```

可通过 env 覆盖：`MODEM_LOG_ANALYZER_COMMAND_CATALOG=/abs/path/to/file.yaml`

## 2. 当前内容（v0.1.0）

5 条命令，覆盖 Plan §1 R5 的 4 类业务 + 1 个会话入口：

```yaml
- name: "modemcli"
  kind: "session_entry"
  business_action: "session_entry"
  description: "ModemCLI 控制台提示符; 不是业务命令"

- name: "debug_bes_rpc"
  kind: "rpc_dispatch"
  business_action: "rpc_dispatch"
  known_arg_ranges:
    - range: [1, 1]
      business_action: "call"
    - range: [3, 3]
      business_action: "sms"
    - range: [4, 4]
      business_action: "data_ping"

- name: "!ping"      # builtin → data_ping
- name: "!ping6"     # builtin → data_ping
- name: "!ifconfig"  # builtin → setting
```

## 3. 业务动作枚举

`command_catalog.BUSINESS_ACTIONS`：

| 业务动作 | 含义 | 已知命令 |
| --- | --- | --- |
| `session_entry` | modemcli 提示符（**不是**业务步骤） | `modemcli` |
| `call` | 语音通话 | `debug_bes_rpc 1` |
| `sms` | 短信 | `debug_bes_rpc 3` |
| `data_ping` | 数据 / IPv4-IPv6 Ping | `debug_bes_rpc 4`, `!ping`, `!ping6` |
| `setting` | 状态 / 接口设置 | `!ifconfig` |
| `rpc_dispatch` | 业务动作待子命令决定 | `debug_bes_rpc`（未命中区间时） |
| `unknown` | 不在 catalog 中 / 子命令未知 | 其余 |

## 4. 分类规则（`classify_command`）

| 输入 | 输出 | 理由 |
| --- | --- | --- |
| 不在 catalog 中 | `unknown` | Plan S11：未识别保留 unknown |
| `modemcli` | `session_entry` | Plan R3：modemcli 是会话入口 |
| `debug_bes_rpc 1` | `call` | `args[0]=1` 命中 `[1,1]` 区间 |
| `debug_bes_rpc 3 ...` | `sms` | `args[0]=3` 命中 `[3,3]` |
| `debug_bes_rpc 99` | `unknown` | 不在已知区间 → 不猜 |
| `!ping` | `data_ping` | `builtin` 类直接用 `business_action` |
| `random_command` | `unknown` | 不在 catalog |

**关键**：未识别命令保留为 `unknown`，**不**自动设为 success（Plan S11）。

## 5. 加新命令 / 业务类型

### 5.1 加一个 builtin 命令（如 `!route`）

1. 打开 `knowledge/modemcli_commands.yaml`
2. 加一段：

```yaml
- name: "!route"
  kind: "builtin"
  business_action: "setting"     # 或新动作
  description: "路由表查询/设置"
  notes: "查看或修改系统路由表"
```

3. 跑回归：

```bash
TEST=tests/unit/test_command_catalog.py make test
```

### 5.2 加一个 RPC 子命令

如果 ModemCLI 增加 `debug_bes_rpc 5` 表示新业务：

```yaml
- name: "debug_bes_rpc"
  known_arg_ranges:
    - range: [1, 1]
      business_action: "call"
    - range: [3, 3]
      business_action: "sms"
    - range: [4, 4]
      business_action: "data_ping"
    - range: [5, 5]              # ← 新增
      business_action: "voicemail"  # ← 新增业务动作
      description: "语音留言"
```

注意：新增 `business_action` 时：
1. 在 `BUSINESS_ACTIONS` 常量中加（如 `voicemail`）。
2. 在 `scenario_inference._scenario_name_for_action` 加中文名映射。
3. 加 fixture（见 §6）。

### 5.3 加一个全新业务动作类

例如新增 `voicemail` 业务：

1. `BUSINESS_ACTIONS` 加 `"voicemail"`。
2. yaml 加对应命令。
3. `scenario_inference._scenario_name_for_action` 加 `"voicemail": "语音留言 (Voicemail)"`。
4. 加 fixture（标注 expected classification）。

## 6. 加新业务的端到端验证流程

每个新业务**必须**有 fixture，否则不视为覆盖：

```
tests/fixtures/e2e_cases/<case_name>/
├── evb.log          # 必填; 含真实命令调用
├── control.log      # 可选; 含 AssertionError/TimeoutError
└── expected.json    # 必填; 工程师标注期望
```

示例 `expected.json`：

```json
{
  "classification": "DEVICE_FAILURE_CONFIRMED",
  "scenario_substring": "voicemail",
  "expected_business_actions": ["voicemail"],
  "note": "语音留言提交失败"
}
```

跑回归：

```bash
PYTHONPATH=agents/modem-log-analyzer/src:libs/common/src:gateway/api \
  .venv/bin/python -m pytest agents/modem-log-analyzer/tests/e2e/ -v
```

新增 fixture 必须：
- 脱敏（参见 PRIVACY.md §5）
- 命令名在 catalog 中
- `expected.json` 由工程师手写（**不**由 Agent 从控制日志 ERROR 自动生成——Plan §1 标注）

## 7. 测试命令知识表

`tests/unit/test_command_catalog.py` 锁定以下不变量：

```python
# 四类业务都被 catalog 覆盖
sample_inputs = [
    ("!ping", ["1.1.1.1"]),       # → data_ping
    ("!ping6", ["::1"]),         # → data_ping
    ("!ifconfig", []),           # → setting
    ("debug_bes_rpc", ["1", ...]),  # → call
    ("debug_bes_rpc", ["3", ...]),  # → sms
    ("debug_bes_rpc", ["4", ...]),  # → data_ping
]
```

加新业务时，**必须**扩展这个测试矩阵。

## 8. 已知盲区与未来工作

| 盲区 | 现状 | 未来 |
| --- | --- | --- |
| `!sms` / `!ussd` 等 builtin 未识别 | 落到 unknown | 工程师补 yaml |
| ModemCLI 多语言（中文 / 英文） | 仅英文 | 项目级补充 |
| 多模块并行回调 | `terminal_outcome=unknown` | state-machine 增强（Unit 4 后续） |
| 异步事件跨长时段 | 仅按时间排序 | 引入事件窗与超时 |

## 9. 故障排查

### 9.1 业务动作变成 unknown

```bash
# 检查 catalog 是否加载
PYTHONPATH=agents/modem-log-analyzer/src \
  .venv/bin/python -c "
from modem_log_analyzer.command_catalog import get_default_catalog
import json
cat = get_default_catalog()
print(json.dumps([c.name for c in cat.commands], indent=2))
"
# 应该输出 5 个命令名
```

### 9.2 命令知识表加载失败

`FileNotFoundError: command catalog not found at ...`

修复：
- 检查文件存在：`ls agents/modem-log-analyzer/knowledge/modemcli_commands.yaml`
- 检查 env：`env | grep MODEM_LOG_ANALYZER_COMMAND_CATALOG`
- 检查 yaml 合法：`python3 -c "import yaml; yaml.safe_load(open('agents/modem-log-analyzer/knowledge/modemcli_commands.yaml'))"`

### 9.3 修改 catalog 后测试失败

`test_catalog_loads_from_yaml` 或 `test_catalog_has_required_business_actions` 失败 → 检查 yaml 格式（缩进、特殊字符）。