from __future__ import annotations

from pathlib import Path

from pycodex.tui.chatwidget.tests import (
    CHATWIDGET_TEST_MODULES,
    REEXPORTED_HELPERS,
    SNAPSHOT_NAME_PREFIX,
    chatwidget_snapshot_dir,
    chatwidget_snapshot_path,
    is_chatwidget_test_module,
    make_chatwidget_snapshot_assertion,
)


def test_chatwidget_snapshot_dir_matches_rust_resource_parent() -> None:
    assert chatwidget_snapshot_dir("root") == Path("root/src/chatwidget/snapshots")
    assert chatwidget_snapshot_path("chatwidget_tall", "root") == Path(
        "root/src/chatwidget/snapshots/codex_tui__chatwidget__tests__chatwidget_tall.snap"
    )


def test_snapshot_assertion_models_rust_macro_name_and_directory_binding() -> None:
    assertion = make_chatwidget_snapshot_assertion("status", "value", "@snapshot", "root")

    assert assertion.snapshot_name == f"{SNAPSHOT_NAME_PREFIX}status"
    assert assertion.value == "value"
    assert assertion.inline_snapshot == "@snapshot"
    assert assertion.snapshot_dir == Path("root/src/chatwidget/snapshots")


def test_declared_test_modules_and_reexported_helpers_match_rust_tests_rs() -> None:
    assert "app_server" in CHATWIDGET_TEST_MODULES
    assert "terminal_title" in CHATWIDGET_TEST_MODULES
    assert is_chatwidget_test_module("permissions")
    assert not is_chatwidget_test_module("production")
    assert REEXPORTED_HELPERS == (
        "make_chatwidget_manual_with_sender",
        "set_chatgpt_auth",
        "set_fast_mode_test_catalog",
    )
