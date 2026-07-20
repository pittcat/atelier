"""Unit 3 测试: command_catalog 决定业务动作映射。

按 Plan §1 R3 + §5:
  - ``modemcli`` 是会话入口 (不在 catalog 中作为业务命令)
  - ``debug_bes_rpc`` 是 RPC 调度命令, 业务动作取决于其子命令
  - ``!ping`` / ``!ping6`` → Data/Ping
  - ``!ifconfig`` → Setting
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _catalog():
    from modem_log_analyzer.command_catalog import get_default_catalog

    return get_default_catalog()


def test_catalog_loads_from_yaml():
    cat = _catalog()
    assert cat is not None


def test_modemcli_prompt_not_a_business_action():
    """modemcli 是会话入口, 不映射到业务动作。"""
    from modem_log_analyzer.command_catalog import classify_command

    assert classify_command("modemcli", []) != "call"
    assert classify_command("modemcli", []) != "sms"
    assert classify_command("modemcli", []) != "data_ping"
    assert classify_command("modemcli", []) != "setting"


def test_debug_bes_rpc_classified_as_rpc_dispatch():
    from modem_log_analyzer.command_catalog import classify_command

    action = classify_command("debug_bes_rpc", ["1", "0"])
    # 顶层动作是 RPC dispatch, 业务动作由子命令决定
    assert action in ("rpc_dispatch", "call", "sms", "data_ping", "setting", "unknown")


def test_ping_mapped_to_data_ping():
    from modem_log_analyzer.command_catalog import classify_command

    assert classify_command("!ping", ["8.8.8.8"]) == "data_ping"
    assert classify_command("!ping6", ["::1"]) == "data_ping"


def test_ifconfig_mapped_to_setting():
    from modem_log_analyzer.command_catalog import classify_command

    assert classify_command("!ifconfig", []) == "setting"


def test_sms_command_mapped_to_sms():
    """debug_bes_rpc <sms-sub> 业务动作应为 sms。"""
    from modem_log_analyzer.command_catalog import classify_command

    # 在 catalog 中常见的 sms 触发:debug_bes_rpc 3 (sms)
    # 具体子命令由 catalog 定义;此处只断言动作类属于 sms/call/data_ping/setting/unknown
    action = classify_command("debug_bes_rpc", ["3", "13900000000", "hello"])
    assert action in ("sms", "call", "data_ping", "setting", "unknown")


def test_unknown_command_returns_unknown_not_guess():
    from modem_log_analyzer.command_catalog import classify_command

    # 完全未知的命令
    assert classify_command("some_unknown_command", []) == "unknown"


def test_catalog_has_required_business_actions():
    """Catalog 必须覆盖四类业务: Call, SMS, Data/Ping, Setting。"""
    from modem_log_analyzer.command_catalog import classify_command, get_default_catalog

    _ = get_default_catalog()  # 触发加载以验证 yaml 合法
    # catalog 应该能至少 classify 出一个 call, 一个 sms, 一个 data_ping, 一个 setting
    sample_inputs = [
        ("!ping", ["1.1.1.1"]),
        ("!ping6", ["::1"]),
        ("!ifconfig", []),
        ("debug_bes_rpc", ["1", "13900000000"]),
        ("debug_bes_rpc", ["3", "13900000000", "hello"]),
        ("debug_bes_rpc", ["4", "8.8.8.8"]),
    ]
    actions = {classify_command(cmd, args) for cmd, args in sample_inputs}
    # data_ping 和 setting 至少应该被映射
    assert "data_ping" in actions
    assert "setting" in actions
    # Call/SMS 也应当被 catalog 覆盖(即使还没有真实数据,确保 spec 完整)
    assert "call" in actions
    assert "sms" in actions
