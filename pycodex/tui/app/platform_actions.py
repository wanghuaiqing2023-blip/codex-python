"""Platform action helpers for Rust ``codex-tui::app::platform_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/platform_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::platform_actions",
    source="codex/codex-rs/tui/src/app/platform_actions.rs",
)


@dataclass(eq=True)
class WindowsSandboxState:
    setup_started_at: Any | None = None
    skip_world_writable_scan_once: bool = False


@dataclass(frozen=True, eq=True)
class KeyEvent:
    code: str
    modifiers: frozenset[str] = frozenset()
    kind: str = "press"

    @classmethod
    def char(cls, char: str, *, ctrl: bool = False, kind: str = "press") -> "KeyEvent":
        modifiers = frozenset({"control"}) if ctrl else frozenset()
        return cls(code=char, modifiers=modifiers, kind=kind)


@dataclass(frozen=True, eq=True)
class OpenWorldWritableWarningConfirmation:
    preset: Any | None = None
    profile_selection: Any | None = None
    sample_paths: list[str] | None = None
    extra_count: int = 0
    failed_scan: bool = True


def _event_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("code", ""))
    return str(getattr(value, "code", ""))


def _event_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("kind", "press")).lower()
    return str(getattr(value, "kind", "press")).lower()


def _event_modifiers(value: Any) -> set[str]:
    raw = value.get("modifiers", []) if isinstance(value, dict) else getattr(value, "modifiers", [])
    if isinstance(raw, str):
        return {part.strip().lower() for part in raw.replace("|", ",").split(",") if part.strip()}
    return {str(part).lower() for part in raw}


def send_world_writable_scan_failed(tx: Any | None = None) -> OpenWorldWritableWarningConfirmation:
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


def spawn_world_writable_scan(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::platform_actions.spawn_world_writable_scan Windows sandbox side effect is not ported")


__all__ = [
    "KeyEvent",
    "OpenWorldWritableWarningConfirmation",
    "RUST_MODULE",
    "WindowsSandboxState",
    "send_world_writable_scan_failed",
    "side_return_shortcut_matches",
    "spawn_world_writable_scan",
]
