"""Platform action helpers for Rust ``codex-tui::app::platform_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/platform_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, FrozenSet, List, Optional, Set

from .._porting import RustTuiModule

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
class OpenWorldWritableWarningConfirmation:
    preset: Any = None
    profile_selection: Any = None
    sample_paths: Optional[List[str]] = None
    extra_count: int = 0
    failed_scan: bool = True


@dataclass(frozen=True, eq=True)
class WorldWritableScanPlan:
    action: str
    cwd: Any = None
    env_map: Any = None
    logs_base_dir: Any = None
    permission_profile: Any = None
    tx: Any = None


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


def send_world_writable_scan_failed(tx: Any = None) -> OpenWorldWritableWarningConfirmation:
    """Build/send the Rust failure event for a failed world-writable scan."""

    event = OpenWorldWritableWarningConfirmation(sample_paths=[])
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
    """Plan the Rust Windows world-writable scan side effect.

    Rust returns early when sandbox permissions cannot be resolved from the
    permission profile; otherwise it spawns a blocking scan task that emits
    ``send_world_writable_scan_failed`` on failure. Python records that exact
    module-local decision without performing filesystem permission scans.
    """

    if not _permission_profile_resolves(permission_profile):
        return WorldWritableScanPlan("noop_unresolved_permissions")
    return WorldWritableScanPlan(
        "spawn_blocking_world_writable_scan",
        cwd=cwd,
        env_map=env_map,
        logs_base_dir=logs_base_dir,
        permission_profile=permission_profile,
        tx=tx,
    )


def _permission_profile_resolves(permission_profile: Any) -> bool:
    if permission_profile is None:
        return False
    if isinstance(permission_profile, dict):
        if permission_profile.get("resolves") is False:
            return False
        if permission_profile.get("valid") is False:
            return False
    if getattr(permission_profile, "resolves", True) is False:
        return False
    if getattr(permission_profile, "valid", True) is False:
        return False
    return True


__all__ = [
    "KeyEvent",
    "OpenWorldWritableWarningConfirmation",
    "RUST_MODULE",
    "WindowsSandboxState",
    "WorldWritableScanPlan",
    "send_world_writable_scan_failed",
    "side_return_shortcut_matches",
    "spawn_world_writable_scan",
]
