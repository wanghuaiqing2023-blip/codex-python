"""Rust-derived tests for ``codex-state/src/bin/logs_client.rs``."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from pycodex.state import LogRow


def test_logs_client_inline_modules_have_contiguous_python_owners() -> None:
    client = importlib.import_module("pycodex.state.bin.logs_client")
    formatter = importlib.import_module("pycodex.state.bin.logs_client.formatter")
    matcher = importlib.import_module("pycodex.state.bin.logs_client.matcher")

    assert client.__name__ == "pycodex.state.bin.logs_client"
    assert formatter.__name__ == "pycodex.state.bin.logs_client.formatter"
    assert matcher.__name__ == "pycodex.state.bin.logs_client.matcher"


def test_log_level_threshold_matches_rust_value_enum() -> None:
    from pycodex.state.bin.logs_client import LogLevelThreshold, parse_args

    assert LogLevelThreshold.WARN.levels_upper() == ("WARN", "ERROR")
    assert LogLevelThreshold.TRACE.levels_upper() == (
        "TRACE",
        "DEBUG",
        "INFO",
        "WARN",
        "ERROR",
    )
    assert parse_args(["--level", "WARN"]).level is LogLevelThreshold.WARN
    with pytest.raises(SystemExit):
        parse_args(["--level", "warning"])


def test_logs_client_builds_rust_log_query() -> None:
    from pycodex.state.bin.logs_client import build_filter, parse_args, to_log_query

    args = parse_args(
        [
            "--db",
            "logs.sqlite",
            "--level",
            "info",
            "--from",
            "42",
            "--module",
            "core",
            "--module",
            "",
            "--thread-id",
            "thread-1",
            "--threadless",
        ]
    )
    query = to_log_query(build_filter(args), limit=12, after_id=7, descending=True)

    assert query.levels_upper == ("INFO", "WARN", "ERROR")
    assert query.from_ts == 42
    assert query.module_like == ("core",)
    assert query.thread_ids == ("thread-1",)
    assert query.include_threadless is True
    assert query.limit == 12
    assert query.after_id == 7
    assert query.descending is True


def test_logs_client_formatter_and_matcher_follow_inline_modules() -> None:
    from pycodex.state.bin.logs_client import format_row
    from pycodex.state.bin.logs_client import formatter, matcher

    assert matcher.apply_patch("ToolCall: apply_patch\n+added")
    assert not matcher.apply_patch("ordinary message")
    assert formatter.ts(0, 0, compact=True) == "00:00:00"
    assert "warn " in formatter.level("warn")
    assert "+added" in formatter.apply_patch("+added")

    row = LogRow(
        id=1,
        ts=0,
        ts_nanos=0,
        level="INFO",
        target="codex_core",
        message="hello",
        thread_id="thread-1",
    )
    rendered = format_row(row, compact=False)
    assert "1970-01-01T00:00:00.000Z" in rendered
    assert "thread-1" in rendered
    assert "codex_core" in rendered
    assert "hello" in rendered


def test_state_runtime_is_owned_by_runtime_package() -> None:
    runtime = importlib.import_module("pycodex.state.runtime")
    assert runtime.StateRuntime.__module__ == "pycodex.state.runtime.state_runtime"
    assert not Path("pycodex/state/state_runtime.py").exists()
