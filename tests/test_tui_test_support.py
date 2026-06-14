"""Parity tests for codex-rs/tui/src/test_support.rs."""

from pycodex.protocol import SessionSource
from pycodex.tui.test_support import (
    PathBufExt,
    SkillScope,
    TestPathBuf,
    from_app_server_wire,
    session_source_cli,
    skill_scope_repo,
    skill_scope_user,
    test_path_buf,
    test_path_display,
)


def test_test_path_display_uses_test_path_buf_display_semantics():
    assert test_path_display("/tmp/hooks.json") == "/tmp/hooks.json"
    assert test_path_display("tmp/hooks.json") == "/tmp/hooks.json"
    assert str(test_path_buf("/workspace/project").abs()) == "/workspace/project"


def test_path_buf_ext_abs_accepts_existing_or_plain_paths():
    existing = TestPathBuf("/tmp")

    assert PathBufExt.abs(existing) is existing
    assert PathBufExt.abs("relative/path").display() == "/relative/path"


def test_session_source_cli_round_trips_through_app_server_wire():
    assert session_source_cli() == "cli"
    assert session_source_cli(SessionSource.from_startup_arg) == SessionSource.cli()


def test_skill_scope_helpers_use_app_server_snake_case_wire_values():
    assert skill_scope_user() == "user"
    assert skill_scope_repo() == "repo"
    assert skill_scope_user(SkillScope) == SkillScope.USER
    assert skill_scope_repo(SkillScope) == SkillScope.REPO


def test_from_app_server_wire_normalizes_enums_dataclasses_and_dicts():
    assert from_app_server_wire(SkillScope.ADMIN) == "admin"
    assert from_app_server_wire({"scope": SkillScope.SYSTEM}) == {"scope": "system"}
    assert from_app_server_wire(SessionSource.mcp()) == "appServer"


def test_from_app_server_wire_reports_target_decode_failures():
    def fail(_value):
        raise RuntimeError("nope")

    try:
        from_app_server_wire("cli", fail)
    except ValueError as exc:
        assert "app-server wire value should map to legacy helper type" in str(exc)
    else:
        raise AssertionError("expected ValueError")
