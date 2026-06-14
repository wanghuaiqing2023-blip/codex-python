from datetime import datetime, timezone
from pathlib import Path

import pytest

from pycodex.tui.status.tests import (
    LineLike,
    SpanLike,
    TestStatusConfig,
    TokenUsage,
    app_server_workspace_write_profile,
    render_lines,
    reset_at_from,
    sanitize_directory,
    set_workspace_cwd,
    status_snapshot_tests,
    test_status_account_display,
    token_info_for,
)


def test_workspace_write_profile_matches_rust_shape() -> None:
    profile = app_server_workspace_write_profile(True)
    assert profile["kind"] == "managed"
    assert profile["network"] == "enabled"
    assert profile["file_system"]["entries"] == [
        {"path": {"special": "root"}, "access": "read"},
        {"path": {"special": "project_roots", "subpath": None}, "access": "write"},
        {"path": {"special": "slash_tmp"}, "access": "write"},
        {"path": {"special": "tmpdir"}, "access": "write"},
    ]
    assert app_server_workspace_write_profile(False)["network"] == "restricted"


def test_set_workspace_cwd_updates_roots_and_permissions() -> None:
    config = TestStatusConfig(codex_home=Path("/tmp/home"), cwd=Path("/tmp/old"))
    set_workspace_cwd(config, Path("/tmp/project"))
    assert config.cwd == Path("/tmp/project")
    assert config.workspace_roots == [Path("/tmp/project")]
    assert config.permissions.workspace_roots == [Path("/tmp/project")]


def test_render_lines_and_sanitize_directory_helpers() -> None:
    assert render_lines([LineLike((SpanLike("he"), SpanLike("llo"))), {"text": "world"}]) == [
        "hello",
        "world",
    ]
    assert sanitize_directory(["│ Directory: C:/secret/project    |"])[0] == "│ Directory: [[workspace]]        |"
    assert sanitize_directory(["no directory"])[0] == "no directory"


def test_reset_at_from_returns_utc_timestamp() -> None:
    captured = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert reset_at_from(captured, 600) == int(datetime(2024, 1, 2, 3, 14, 5, tzinfo=timezone.utc).timestamp())
    with pytest.raises(TypeError):
        reset_at_from("bad", 1)  # type: ignore[arg-type]


def test_token_info_and_account_display_helpers() -> None:
    usage = TokenUsage(input_tokens=1, cached_input_tokens=2, output_tokens=3, reasoning_output_tokens=4, total_tokens=10)
    info = token_info_for("gpt-5.1-codex-max", object(), usage)
    assert info.total_token_usage == usage
    assert info.last_token_usage == usage
    assert info.model_context_window == 272000
    assert test_status_account_display() is None


def test_snapshot_inventory_documents_status_module_ownership() -> None:
    assert "status_snapshot_includes_reasoning_details" in status_snapshot_tests()
    assert "status_context_window_uses_last_usage" in status_snapshot_tests()
