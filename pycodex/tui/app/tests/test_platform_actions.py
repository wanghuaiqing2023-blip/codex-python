from __future__ import annotations

from pathlib import Path

from pycodex.protocol import PermissionProfile
from pycodex.tui.app_event import AppEvent
from pycodex.tui.app.platform_actions import (
    KeyEvent,
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

    assert event == AppEvent(
        "OpenWorldWritableWarningConfirmation",
        {
            "preset": None,
            "profile_selection": None,
            "sample_paths": [],
            "extra_count": 0,
            "failed_scan": True,
        },
    )
    assert sender.events == [event]


def test_spawn_world_writable_scan_plans_noop_or_blocking_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import pycodex.windows_sandbox as sandbox

    monkeypatch.setattr(
        sandbox,
        "apply_world_writable_scan_and_denies_for_permissions",
        lambda *_args: None,
    )
    assert spawn_world_writable_scan("cwd", {}, "logs", None) == WorldWritableScanPlan(
        "noop_unresolved_permissions"
    )
    assert spawn_world_writable_scan("cwd", {}, "logs", PermissionProfile.disabled()) == WorldWritableScanPlan(
        "noop_unresolved_permissions"
    )

    sender = Sender()
    plan = spawn_world_writable_scan(
        tmp_path,
        {"A": "B"},
        tmp_path,
        PermissionProfile.read_only(),
        sender,
    )
    assert plan == WorldWritableScanPlan(
        "spawn_blocking_world_writable_scan",
        cwd=tmp_path,
        env_map={"A": "B"},
        logs_base_dir=tmp_path,
        permission_profile=PermissionProfile.read_only(),
        tx=sender,
    )
    assert plan.worker is not None
    plan.worker.join(timeout=2)
    assert not plan.worker.is_alive()


def test_spawn_world_writable_scan_executes_windows_sandbox_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import pycodex.windows_sandbox as sandbox

    calls: list[tuple[Path, Path, dict[str, str], object, Path]] = []
    monkeypatch.setattr(
        sandbox,
        "apply_world_writable_scan_and_denies_for_permissions",
        lambda home, cwd, env, permissions, logs: calls.append(
            (Path(home), Path(cwd), dict(env), permissions, Path(logs))
        ),
    )

    plan = spawn_world_writable_scan(
        tmp_path,
        {"A": "B"},
        tmp_path,
        PermissionProfile.read_only(),
        Sender(),
    )
    assert plan.worker is not None
    plan.worker.join(timeout=2)

    assert not plan.worker.is_alive()
    assert len(calls) == 1
    assert calls[0][0:3] == (tmp_path, tmp_path, {"A": "B"})
    assert calls[0][4] == tmp_path
"""Rust source: codex/codex-rs/tui/src/app/platform_actions.rs."""
