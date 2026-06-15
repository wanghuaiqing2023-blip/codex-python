"""Trust-directory onboarding step.

Upstream source: ``codex/codex-rs/tui/src/onboarding/trust_directory.rs``.

Rust renders this step with ratatui and routes onboarding key bindings.  Python
ports the state transitions and exposes semantic render rows rather than a
terminal buffer snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="onboarding::trust_directory",
    source="codex/codex-rs/tui/src/onboarding/trust_directory.rs",
    status="complete",
)

TRUST_PROMPT = (
    "Do you trust the contents of this directory? Working with untrusted contents comes with "
    "higher risk of prompt injection. Trusting the directory allows project-local config, "
    "hooks, and exec policies to load."
)


class TrustDirectorySelection(Enum):
    Trust = "trust"
    Quit = "quit"


class StepState(Enum):
    InProgress = "in_progress"
    Complete = "complete"


@dataclass(frozen=True)
class TrustDirectoryRenderPlan:
    cwd: str
    trust_target: str
    lines: Tuple[str, ...]
    highlighted: TrustDirectorySelection
    show_git_root_warning: bool
    show_windows_create_sandbox_hint: bool


@dataclass
class TrustDirectoryWidget:
    cwd: Path
    trust_target: Path
    show_windows_create_sandbox_hint: bool = False
    should_quit_value: bool = False
    selection: Optional[TrustDirectorySelection] = None
    highlighted: TrustDirectorySelection = TrustDirectorySelection.Trust
    error: Optional[str] = None

    def render_ref(self, area: Any = None, buf: Any = None) -> TrustDirectoryRenderPlan:
        cwd = _display_path(self.cwd)
        trust_target = _display_path(self.trust_target)
        lines: list[str] = [f"> You are in {cwd}", ""]
        show_git_root_warning = self.cwd != self.trust_target
        if show_git_root_warning:
            lines.append(
                "  Note: You're in a subdirectory of a Git project. Trusting will apply to "
                f"the repository root: {trust_target}"
            )
            lines.append("")
        lines.append(f"  {TRUST_PROMPT}")
        lines.append("")
        lines.append(selection_option_row(0, "Yes, continue", self.highlighted is TrustDirectorySelection.Trust))
        lines.append(selection_option_row(1, "No, quit", self.highlighted is TrustDirectorySelection.Quit))
        lines.append("")
        if self.error is not None:
            lines.append(f"  {self.error}")
            lines.append("")
        suffix = " to continue and create a sandbox..." if self.show_windows_create_sandbox_hint else " to continue"
        lines.append(f"  Press Enter{suffix}")
        return TrustDirectoryRenderPlan(
            cwd=cwd,
            trust_target=trust_target,
            lines=tuple(lines),
            highlighted=self.highlighted,
            show_git_root_warning=show_git_root_warning,
            show_windows_create_sandbox_hint=self.show_windows_create_sandbox_hint,
        )

    def handle_key_event(self, key_event: Any) -> None:
        if _key_kind(key_event) == "release":
            return
        key = _key_name(key_event)
        if key in {"up", "k"}:
            self.highlighted = TrustDirectorySelection.Trust
        elif key in {"down", "j"}:
            self.highlighted = TrustDirectorySelection.Quit
        elif key == "1":
            self.handle_trust()
        elif key in {"2", "q", "esc", "escape"}:
            self.handle_quit()
        elif key in {"enter", "return"}:
            if self.highlighted is TrustDirectorySelection.Trust:
                self.handle_trust()
            else:
                self.handle_quit()

    def get_step_state(self) -> StepState:
        return StepState.Complete if self.selection is not None or self.should_quit_value else StepState.InProgress

    def handle_trust(self) -> None:
        self.highlighted = TrustDirectorySelection.Trust
        self.error = None
        self.selection = TrustDirectorySelection.Trust

    def handle_quit(self) -> None:
        self.highlighted = TrustDirectorySelection.Quit
        self.should_quit_value = True

    def should_quit(self) -> bool:
        return self.should_quit_value


def render_ref(widget: TrustDirectoryWidget, area: Any = None, buf: Any = None) -> TrustDirectoryRenderPlan:
    return widget.render_ref(area, buf)


def handle_key_event(widget: TrustDirectoryWidget, key_event: Any) -> None:
    widget.handle_key_event(key_event)


def get_step_state(widget: TrustDirectoryWidget) -> StepState:
    return widget.get_step_state()


def selection_option_row(idx: int, text: str, highlighted: bool) -> str:
    marker = "›" if highlighted else " "
    return f"{marker} {idx + 1}. {text}"


def _display_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _key_kind(key_event: Any) -> str:
    if isinstance(key_event, Mapping):
        return str(key_event.get("kind", "press")).lower()
    return str(getattr(key_event, "kind", "press")).lower()


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, Mapping):
        value = key_event.get("key", key_event.get("code", key_event.get("char", "")))
    else:
        value = getattr(key_event, "key", getattr(key_event, "code", getattr(key_event, "char", "")))
    return str(value).lower()


__all__ = [
    "RUST_MODULE",
    "StepState",
    "TRUST_PROMPT",
    "TrustDirectoryRenderPlan",
    "TrustDirectorySelection",
    "TrustDirectoryWidget",
    "get_step_state",
    "handle_key_event",
    "render_ref",
    "selection_option_row",
]
