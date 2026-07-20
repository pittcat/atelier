"""Unit 2 单元测试: intake 模块负责路径校验与覆盖保护。

intake.py 提供纯函数 ``validate_run_request(req: RunRequest) -> ValidatedRequest``:
  - 检查 evb_log_path 存在、可读、非空、非目录。
  - 检查 output_dir 父目录可达、output_dir 本身不存在或将被覆盖。
  - 检查 control_log_path (可选) 存在。
  - 不抛出系统异常; 抛出自定义 ``IntakeError`` (含错误码与人类可读 message)。

validate_run_request 返回的对象供 service 与 CLI 共用。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _import_intake():
    from modem_log_analyzer import intake

    return intake


# ============================================================
# 路径校验
# ============================================================


def test_validate_minimal_legal_request(tmp_path):
    """最小合法请求应通过校验。"""
    evb = tmp_path / "evb.log"
    evb.write_text("modemcli> debug_bes_rpc 1 0\nOK\n", encoding="utf-8")
    out = tmp_path / "out"
    intake = _import_intake()
    validated = intake.validate_run_request(
        intake.RunRequestProxy(
            evb_log_path=str(evb),
            output_dir=str(out),
            control_log_path=None,
            label=None,
            thread_id=None,
            overwrite=False,
        )
    )
    assert validated.evb_log_path == str(evb)
    assert validated.output_dir == str(out)


def test_missing_evb_log_raises_intake_error(tmp_path):
    intake = _import_intake()
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(tmp_path / "no.log"),
                output_dir=str(tmp_path / "out"),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "EVE_LOG_MISSING"


def test_evb_log_is_directory_raises(tmp_path):
    intake = _import_intake()
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(tmp_path),
                output_dir=str(tmp_path / "out"),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code in {"EVE_LOG_IS_DIR", "EVE_LOG_MISSING"}


def test_empty_evb_log_raises(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "empty.log"
    evb.write_text("", encoding="utf-8")
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(tmp_path / "out"),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "EVE_LOG_EMPTY"


def test_unreadable_evb_log_raises(tmp_path):
    import platform

    if platform.system() == "Windows":
        pytest.skip("POSIX permissions semantics")
    intake = _import_intake()
    evb = tmp_path / "no_read.log"
    evb.write_text("x", encoding="utf-8")
    evb.chmod(0o000)
    try:
        with pytest.raises(intake.IntakeError) as exc:
            intake.validate_run_request(
                intake.RunRequestProxy(
                    evb_log_path=str(evb),
                    output_dir=str(tmp_path / "out"),
                    control_log_path=None,
                    label=None,
                    thread_id=None,
                    overwrite=False,
                )
            )
        assert exc.value.code == "EVE_LOG_UNREADABLE"
    finally:
        evb.chmod(0o644)


def test_output_dir_parent_unavailable(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(tmp_path / "no_such_parent" / "out"),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "OUT_PARENT_MISSING"


def test_control_log_must_exist_when_provided(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(out),
                control_log_path=str(tmp_path / "missing_control.log"),
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "CONTROL_LOG_MISSING"


def test_control_log_none_is_legal(tmp_path):
    """S2: control-log 缺失应合法, 走默认路径。"""
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    validated = intake.validate_run_request(
        intake.RunRequestProxy(
            evb_log_path=str(evb),
            output_dir=str(out),
            control_log_path=None,
            label=None,
            thread_id=None,
            overwrite=False,
        )
    )
    assert validated.control_log_path is None


# ============================================================
# 覆盖保护
# ============================================================


def test_existing_report_blocks_without_overwrite(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.md").write_text("old", encoding="utf-8")
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(out),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "OUT_REPORT_EXISTS"


def test_existing_json_blocks_without_overwrite(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "analysis.json").write_text("{}", encoding="utf-8")
    with pytest.raises(intake.IntakeError) as exc:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(out),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    assert exc.value.code == "OUT_JSON_EXISTS"


def test_existing_artifacts_allowed_with_overwrite(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.md").write_text("old", encoding="utf-8")
    validated = intake.validate_run_request(
        intake.RunRequestProxy(
            evb_log_path=str(evb),
            output_dir=str(out),
            control_log_path=None,
            label=None,
            thread_id=None,
            overwrite=True,
        )
    )
    assert validated.overwrite is True


# ============================================================
# 错误信息不泄露日志内容
# ============================================================


def test_intake_error_does_not_include_evb_content(tmp_path):
    intake = _import_intake()
    secret = "VERY_SECRET_13900000000_IMSI_46000"
    evb = tmp_path / "evb.log"
    evb.write_text(secret, encoding="utf-8")
    try:
        intake.validate_run_request(
            intake.RunRequestProxy(
                evb_log_path=str(evb),
                output_dir=str(tmp_path / "no_parent" / "out"),
                control_log_path=None,
                label=None,
                thread_id=None,
                overwrite=False,
            )
        )
    except intake.IntakeError as exc:
        # 错误 message 可包含路径但**不**包含文件内容
        assert secret not in str(exc)


# ============================================================
# 路径规范化
# ============================================================


def test_paths_normalized_to_absolute(tmp_path):
    intake = _import_intake()
    evb = tmp_path / "evb.log"
    evb.write_text("x", encoding="utf-8")
    cwd = tmp_path
    validated = intake.validate_run_request(
        intake.RunRequestProxy(
            evb_log_path="evb.log",
            output_dir="out",
            control_log_path=None,
            label=None,
            thread_id=None,
            overwrite=False,
            base_dir=str(cwd),
        )
    )
    # 相对路径应被规范化为绝对路径
    assert Path(validated.evb_log_path).is_absolute()
    assert Path(validated.output_dir).is_absolute()
