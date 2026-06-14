"""Footer and status-row presentation state for the chat composer.

Port of Rust ``codex-tui::bottom_pane::chat_composer::footer_state``.  The
large footer renderer remains a separate module; this module owns the state
container and the small helper methods defined next to it in Rust.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::footer_state",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/footer_state.rs",
)


@dataclass(frozen=True)
class Span:
    content: str
    style: str = "plain"


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...]

    @classmethod
    def from_text(cls, text: str, style: str = "plain") -> "Line":
        return cls((Span(text, style),))

    @property
    def text(self) -> str:
        return "".join(span.content for span in self.spans)


@dataclass
class FooterFlash:
    line: Line
    expires_at: float


@dataclass
class FooterState:
    quit_shortcut_expires_at: float | None = None
    quit_shortcut_key: Any = None
    esc_backtrack_hint: bool = False
    use_shift_enter_hint: bool = False
    mode: Any = None
    hint_override: list[tuple[str, str]] | None = None
    plan_mode_nudge_visible: bool = False
    flash: FooterFlash | None = None
    context_window_percent: int | None = None
    context_window_used_tokens: int | None = None
    collaboration_mode_indicator: Any | None = None
    goal_status_indicator: Any | None = None
    ide_context_active: bool = False
    status_line_value: Line | str | Any | None = None
    status_line_hyperlink_url: str | None = None
    status_line_enabled: bool = False
    side_conversation_context_label: str | None = None
    active_agent_label: str | None = None
    external_editor_key: Any | None = None
    show_transcript_key: Any | None = None
    insert_newline_key: Any | None = None
    queue_key: Any | None = None
    toggle_shortcuts_key: Any | None = None
    history_search_key: Any | None = None
    reasoning_down_key: Any | None = None
    reasoning_up_key: Any | None = None

    def flash_visible(self, now: float | None = None) -> bool:
        if self.flash is None:
            return False
        current = time.monotonic() if now is None else now
        return current < self.flash.expires_at

    def show_flash(self, line: Line | str, duration: float, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        line_value = line if isinstance(line, Line) else Line.from_text(str(line))
        self.flash = FooterFlash(line=line_value, expires_at=current + duration)

    def status_line_text(self) -> str | None:
        if self.status_line_value is None:
            return None
        if isinstance(self.status_line_value, Line):
            return self.status_line_value.text
        if isinstance(self.status_line_value, str):
            return self.status_line_value
        spans = getattr(self.status_line_value, "spans", None)
        if spans is not None:
            return "".join(_span_content(span) for span in spans)
        return str(self.status_line_value)


def _span_content(span: Any) -> str:
    if isinstance(span, Span):
        return span.content
    content = getattr(span, "content", None)
    if content is not None:
        return str(content)
    return str(span)


__all__ = [
    "FooterFlash",
    "FooterState",
    "Line",
    "RUST_MODULE",
    "Span",
]
