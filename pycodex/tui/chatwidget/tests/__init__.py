"""Test-support facade for Rust ``codex-tui::chatwidget::tests``.

The Rust module is a test-only aggregation module: it re-exports many helper
types, declares chatwidget test submodules, defines a snapshot-directory helper,
and provides the ``assert_chatwidget_snapshot!`` macro.  Python keeps this as a
lightweight test-support package instead of treating it as production TUI
behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::tests",
    source="codex/codex-rs/tui/src/chatwidget/tests.rs",
    status="complete",
)

CHATWIDGET_TEST_MODULES: Tuple[str, ...] = (
    "app_server",
    "approval_requests",
    "composer_submission",
    "exec_flow",
    "goal_menu",
    "goal_validation",
    "guardian",
    "helpers",
    "history_replay",
    "mcp_startup",
    "permissions",
    "plan_mode",
    "popups_and_settings",
    "review_mode",
    "side",
    "slash_commands",
    "status_and_layout",
    "status_command_tests",
    "status_surface_previews",
    "terminal_title",
)

REEXPORTED_HELPERS: Tuple[str, ...] = (
    "make_chatwidget_manual_with_sender",
    "set_chatgpt_auth",
    "set_fast_mode_test_catalog",
)

SNAPSHOT_NAME_PREFIX = "codex_tui__chatwidget__tests__"
SNAPSHOT_SENTINEL = "codex_tui__chatwidget__tests__chatwidget_tall.snap"


@dataclass(frozen=True)
class ChatWidgetSnapshotAssertion:
    """Semantic representation of Rust ``assert_chatwidget_snapshot!``."""

    snapshot_name: str
    value: Any
    inline_snapshot: Optional[str] = None
    snapshot_dir: Optional[Path] = None


def chatwidget_snapshot_dir(source_root: Union[str, Path] = "codex/codex-rs/tui") -> Path:
    """Return the snapshot directory used by Rust chatwidget tests."""

    return Path(source_root) / "src" / "chatwidget" / "snapshots"


def chatwidget_snapshot_path(
    name: str,
    source_root: Union[str, Path] = "codex/codex-rs/tui",
) -> Path:
    """Return the expected snapshot file path for a Rust chatwidget snapshot."""

    return chatwidget_snapshot_dir(source_root) / f"{SNAPSHOT_NAME_PREFIX}{name}.snap"


def make_chatwidget_snapshot_assertion(
    name: str,
    value: Any,
    inline_snapshot: Optional[str] = None,
    source_root: Union[str, Path] = "codex/codex-rs/tui",
) -> ChatWidgetSnapshotAssertion:
    """Build the Python equivalent of the Rust snapshot macro inputs."""

    return ChatWidgetSnapshotAssertion(
        snapshot_name=f"{SNAPSHOT_NAME_PREFIX}{name}",
        value=value,
        inline_snapshot=inline_snapshot,
        snapshot_dir=chatwidget_snapshot_dir(source_root),
    )


def is_chatwidget_test_module(name: str) -> bool:
    return name in CHATWIDGET_TEST_MODULES


__all__ = [
    "CHATWIDGET_TEST_MODULES",
    "ChatWidgetSnapshotAssertion",
    "REEXPORTED_HELPERS",
    "RUST_MODULE",
    "SNAPSHOT_NAME_PREFIX",
    "SNAPSHOT_SENTINEL",
    "chatwidget_snapshot_dir",
    "chatwidget_snapshot_path",
    "is_chatwidget_test_module",
    "make_chatwidget_snapshot_assertion",
]
