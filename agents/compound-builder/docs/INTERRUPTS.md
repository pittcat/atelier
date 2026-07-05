# Compound Builder — Interrupt 配置

> **继承自仓库 `AGENTS.md` 第 3 条**:`bash` / `write_file` / `edit_file` / `git_commit`
> 必须 `interrupt_on=True`。本文件细化「恢复语义」。

## 默认覆盖范围

`interrupts.py` 导出 `DEFAULT_INTERRUPT_TOOLS = {
    "bash",
    "write_file",
    "edit_file",
    "git_commit",
}`(与 code-writer 完全一致)。

切换开关:`ATELIER_INTERRUPT_DEFAULT`(默认 `true`,即默认开 interrupt)。
设为 `false` 表示全自动(仅供评测流水线使用)。

## 恢复语义(resume value 含义)

每个工具被 interrupt 后,LangGraph 会把 `__interrupt__` 暴露给前端。
人工/上层调用 `Command(resume=<value>)` 时,`<value>` 的语义如下:

| 工具                  | resume value 形态                                 | 含义                                                                                  |
| --------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `bash`                | `{"approved": bool, "command_override": str?}`    | `approved=False` 直接 abort;`approved=True, command_override=<str>` 时改写原命令再执行 |
| `write_file`          | `{"approved": bool, "content_override": str?}`    | 同上;`content_override` 覆盖原内容                                                    |
| `edit_file`           | `{"approved": bool, "new_string_override": str?}` | 同上;`new_string_override` 覆盖 edit 的新内容                                         |
| `git_commit`          | `{"approved": bool, "message_override": str?}`    | `approved=False` 时跳过 commit(`executor` 节点需要把这步反应为「commit 失败 → 修复」) |

`approved=True` 且对应 override 字段为空 → 等价于「按原参数继续执行」。

## 失败语义

- 人工 `approved=False` 后,工具不执行;`executor` / `fixer` 节点必须把该决策
  反映在 `state.unit.last_error`,把单元记为 **blocked**(不消耗 `repair_budget`)。
- `validator` 失败 + 未达 `repair_budget_used == 3` 上限 → fixer 节点继续修。
- `ATELIER_INTERRUPT_DEFAULT=false` 时,所有 4 工具不 interrupt,直接执行;
  `pytest tests/integration/test_state_flow.py` 验证该开关。

## 测试覆盖

- `tests/unit/test_prompts.py` 验证 `interrupt_on={}` 时 `build_agent` 仍然返回图。
- `tests/integration/test_state_flow.py::test_interrupt_resume` 验证 `bash` 被 interrupt
  后通过 `Command(resume={"approved": True})` 正确恢复。
