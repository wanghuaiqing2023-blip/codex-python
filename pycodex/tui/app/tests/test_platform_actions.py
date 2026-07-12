from __future__ import annotations

from pycodex.tui.app.platform_actions import (
    KeyEvent,
    OpenWorldWritableWarningConfirmation,
    WindowsSandboxState,
    WorldWritableScanPlan,
    send_world_writable_scan_failed,
    side_return_shortcut_matches,
    spawn_world_writable_scan,
)


class Sender:
    def __init__(self) -> None:
        self.events = []

    def send(self, event) -> None:
        self.events.append(event)


def test_windows_sandbox_state_default_matches_rust_default() -> None:
    assert WindowsSandboxState() == WindowsSandboxState(setup_started_at=None, skip_world_writable_scan_once=False)


def test_side_return_shortcuts_match_ctrl_c_and_ctrl_d() -> None:
    assert side_return_shortcut_matches(KeyEvent.char("c", ctrl=True))
    assert side_return_shortcut_matches(KeyEvent.char("C", ctrl=True))
    assert side_return_shortcut_matches(KeyEvent.char("d", ctrl=True))
    assert side_return_shortcut_matches(KeyEvent.char("D", ctrl=True))
    assert side_return_shortcut_matches(
        {"code": "c", "modifiers": ["CONTROL"], "kind": "Press"}
    )
    assert side_return_shortcut_matches(
        {"code": "d", "modifiers": "CONTROL", "kind": "PRESS"}
    )
    assert not side_return_shortcut_matches(KeyEvent(code="esc", modifiers=frozenset(), kind="press"))
    assert not side_return_shortcut_matches(KeyEvent(code="esc", modifiers=frozenset(), kind="release"))
    assert not side_return_shortcut_matches(KeyEvent.char("c", ctrl=True, kind="release"))
    assert not side_return_shortcut_matches(KeyEvent.char("c", ctrl=False))
    assert not side_return_shortcut_matches(KeyEvent.char("x", ctrl=True))


def test_send_world_writable_scan_failed_emits_failed_warning_event() -> None:
    sender = Sender()

    event = send_world_writable_scan_failed(sender)

    assert event == OpenWorldWritableWarningConfirmation(
        preset=None,
        profile_selection=None,
        sample_paths=[],
        extra_count=0,
        failed_scan=True,
    )
    assert sender.events == [event]


def test_spawn_world_writable_scan_plans_noop_or_blocking_scan() -> None:
    assert spawn_world_writable_scan("cwd", {}, "logs", None) == WorldWritableScanPlan(
        "noop_unresolved_permissions"
    )
    assert spawn_world_writable_scan("cwd", {}, "logs", {"valid": False}) == WorldWritableScanPlan(
        "noop_unresolved_permissions"
    )

    sender = Sender()
    assert spawn_world_writable_scan("cwd", {"A": "B"}, "logs", {"valid": True}, sender) == WorldWritableScanPlan(
        "spawn_blocking_world_writable_scan",
        cwd="cwd",
        env_map={"A": "B"},
        logs_base_dir="logs",
        permission_profile={"valid": True},
        tx=sender,
    )
"""Rust source: codex/codex-rs/tui/src/app/platform_actions.rs."""
