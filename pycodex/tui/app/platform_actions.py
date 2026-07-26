"""Platform action helpers for Rust ``codex-tui::app::platform_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/platform_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread
from typing import Any, FrozenSet, Set

from .._porting import RustTuiModule
from ..app_event import AppEvent

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::platform_actions",
    source="codex/codex-rs/tui/src/app/platform_actions.rs",
    status="complete",
)


@dataclass(eq=True)
class WindowsSandboxState:
    setup_started_at: Any = None
    skip_world_writable_scan_once: bool = False


@dataclass(frozen=True, eq=True)
class KeyEvent:
    code: str
    modifiers: FrozenSet[str] = frozenset()
    kind: str = "press"

    @classmethod
    def char(cls, char: str, *, ctrl: bool = False, kind: str = "press") -> "KeyEvent":
        modifiers = frozenset({"control"}) if ctrl else frozenset()
        return cls(code=char, modifiers=modifiers, kind=kind)


@dataclass(frozen=True, eq=True)
class WorldWritableScanPlan:
    action: str
    cwd: Any = None
    env_map: Any = None
    logs_base_dir: Any = None
    permission_profile: Any = None
    tx: Any = None
    worker: Thread | None = field(default=None, compare=False, repr=False)


def _event_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("code", ""))
    return str(getattr(value, "code", ""))


def _event_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("kind", "press")).lower()
    return str(getattr(value, "kind", "press")).lower()


def _event_modifiers(value: Any) -> Set[str]:
    raw = value.get("modifiers", []) if isinstance(value, dict) else getattr(value, "modifiers", [])
    if isinstance(raw, str):
        return {part.strip().lower() for part in raw.replace("|", ",").split(",") if part.strip()}
    return {str(part).lower() for part in raw}


def send_world_writable_scan_failed(tx: Any = None) -> AppEvent:
    """Build/send the Rust failure event for a failed world-writable scan."""

    event = AppEvent(
        "OpenWorldWritableWarningConfirmation",
        {
            "preset": None,
            "profile_selection": None,
            "sample_paths": [],
            "extra_count": 0,
            "failed_scan": True,
        },
    )
    if tx is not None:
        tx.send(event)
    return event


def side_return_shortcut_matches(key_event: Any) -> bool:
    """Return whether the key event is Press Ctrl-C or Press Ctrl-D."""

    if _event_kind(key_event) != "press":
        return False
    if "control" not in _event_modifiers(key_event) and "ctrl" not in _event_modifiers(key_event):
        return False
    code = _event_code(key_event)
    if len(code) != 1:
        return False
    return code.lower() in {"c", "d"}


def spawn_world_writable_scan(
    cwd: Any,
    env_map: Any,
    logs_base_dir: Any,
    permission_profile: Any,
    tx: Any = None,
) -> WorldWritableScanPlan:
    """Spawn Rust's blocking Windows world-writable scan side effect."""

    from pycodex import windows_sandbox

    cwd_path = Path(cwd)
    logs_path = Path(logs_base_dir)
    try:
        permissions = (
            windows_sandbox.ResolvedWindowsSandboxPermissions
            .try_from_permission_profile_for_cwd(permission_profile, cwd_path)
        )
    except (TypeError, ValueError):
        return WorldWritableScanPlan("noop_unresolved_permissions")

    def run_scan() -> None:
        try:
            windows_sandbox.apply_world_writable_scan_and_denies_for_permissions(
                logs_path,
                cwd_path,
                env_map,
                permissions,
                logs_path,
            )
        except Exception:
            send_world_writable_scan_failed(tx)

    worker = Thread(
        target=run_scan,
        name="pycodex-world-writable-scan",
        daemon=True,
    )
    plan = WorldWritableScanPlan(
        "spawn_blocking_world_writable_scan",
        cwd=cwd_path,
        env_map=env_map,
        logs_base_dir=logs_path,
        permission_profile=permission_profile,
        tx=tx,
        worker=worker,
    )
    worker.start()
    return plan


__all__ = [
    "KeyEvent",
    "RUST_MODULE",
    "WindowsSandboxState",
    "WorldWritableScanPlan",
    "send_world_writable_scan_failed",
    "side_return_shortcut_matches",
    "spawn_world_writable_scan",
]
