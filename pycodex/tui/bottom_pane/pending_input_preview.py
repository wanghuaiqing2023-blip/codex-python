"""Pending input preview widget.

Port of Rust ``codex-tui::bottom_pane::pending_input_preview`` using semantic
rendered lines instead of ratatui buffers.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any, List, MutableSequence, Optional

from .._porting import RustTuiModule
from ..key_hint import alt as key_hint_alt
from ..key_hint import plain as key_hint_plain
from ..ratatui_bridge import Rect

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::pending_input_preview",
    source="codex/codex-rs/tui/src/bottom_pane/pending_input_preview.rs",
    status="complete",
)

PREVIEW_LINE_LIMIT = 3
SECTION_PREFIX = "• "
ITEM_PREFIX = "  ↳ "
CONTINUATION_PREFIX = "    "
OVERFLOW_PREFIX = "    …"


@dataclass(frozen=True)
class RenderedLine:
    text: str
    style: str = "plain"


@dataclass
class PendingInputPreview:
    pending_steers: List[str] = field(default_factory=list)
    rejected_steers: List[str] = field(default_factory=list)
    queued_messages: List[str] = field(default_factory=list)
    edit_binding: Optional[Any] = field(default_factory=lambda: key_hint_alt("Up"))
    interrupt_binding: Optional[Any] = field(default_factory=lambda: key_hint_plain("Esc"))

    @classmethod
    def new(cls) -> "PendingInputPreview":
        return cls()

    def set_edit_binding(self, binding: Optional[Any]) -> None:
        self.edit_binding = binding

    def set_interrupt_binding(self, binding: Optional[Any]) -> None:
        self.interrupt_binding = binding

    @staticmethod
    def push_truncated_preview_lines(
        lines: List[RenderedLine],
        wrapped: List[RenderedLine],
        overflow_line: RenderedLine,
    ) -> None:
        wrapped_len = len(wrapped)
        lines.extend(wrapped[:PREVIEW_LINE_LIMIT])
        if wrapped_len > PREVIEW_LINE_LIMIT:
            lines.append(overflow_line)

    @staticmethod
    def push_section_header(lines: List[RenderedLine], width: int, header: str) -> None:
        del width
        lines.append(RenderedLine(SECTION_PREFIX + header, "dim"))

    def as_renderable(self, width: int) -> List[RenderedLine]:
        if (
            not self.pending_steers
            and not self.rejected_steers
            and not self.queued_messages
        ) or width < 4:
            return []

        lines: List[RenderedLine] = []

        if self.pending_steers:
            header = "Messages to be submitted after next tool call"
            if self.interrupt_binding is not None:
                header += f" (press {_binding_text(self.interrupt_binding)} to interrupt and send immediately)"
            self.push_section_header(lines, width, header)
            for steer in self.pending_steers:
                wrapped = _preview_lines(steer, width, italic=False)
                self.push_truncated_preview_lines(lines, wrapped, RenderedLine(OVERFLOW_PREFIX, "dim"))

        if self.rejected_steers:
            if lines:
                lines.append(RenderedLine(""))
            self.push_section_header(lines, width, "Messages to be submitted at end of turn")
            for steer in self.rejected_steers:
                wrapped = _preview_lines(steer, width, italic=False)
                self.push_truncated_preview_lines(lines, wrapped, RenderedLine(OVERFLOW_PREFIX, "dim"))

        if self.queued_messages:
            if lines:
                lines.append(RenderedLine(""))
            self.push_section_header(lines, width, "Queued follow-up inputs")
            for message in self.queued_messages:
                wrapped = _preview_lines(message, width, italic=True)
                self.push_truncated_preview_lines(lines, wrapped, RenderedLine(OVERFLOW_PREFIX, "dim+italic"))

        if self.queued_messages and self.edit_binding is not None:
            lines.append(RenderedLine(f"    {_binding_text(self.edit_binding)} edit last queued message", "dim"))

        return lines

    def render(self, area: Rect, buf: MutableSequence[RenderedLine]) -> None:
        if area.is_empty():
            return
        buf.extend(self.as_renderable(area.width)[: area.height])

    def desired_height(self, width: int) -> int:
        return len(self.as_renderable(width))


def render(preview: PendingInputPreview, area: Rect, buf: MutableSequence[RenderedLine]) -> None:
    preview.render(area, buf)


def desired_height(preview: PendingInputPreview, width: int) -> int:
    return preview.desired_height(width)


def _preview_lines(message: str, width: int, *, italic: bool) -> List[RenderedLine]:
    style = "dim+italic" if italic else "dim"
    out: List[RenderedLine] = []
    first = True
    for raw_line in message.splitlines() or [""]:
        initial = ITEM_PREFIX if first else CONTINUATION_PREFIX
        chunks = _wrap_preview_text(raw_line, width, initial_indent=initial, subsequent_indent=CONTINUATION_PREFIX)
        out.extend(RenderedLine(chunk, style) for chunk in chunks)
        first = False
    return out


def _wrap_preview_text(text: str, width: int, *, initial_indent: str, subsequent_indent: str) -> List[str]:
    width = max(width, 1)
    if _is_url_like_token(text):
        return [initial_indent + text]
    return textwrap.wrap(
        text,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        replace_whitespace=False,
        drop_whitespace=False,
    ) or [initial_indent]


def _wrap_text(text: str, width: int, *, subsequent_indent: str) -> List[str]:
    width = max(width, 1)
    return textwrap.wrap(
        text,
        width=width,
        subsequent_indent=subsequent_indent,
        replace_whitespace=False,
        drop_whitespace=False,
    ) or [""]


def _is_url_like_token(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not any(ch.isspace() for ch in stripped) and (
        "://" in stripped or "/" in stripped or "." in stripped
    )


def _binding_text(binding: Any) -> str:
    display_label = getattr(binding, "display_label", None)
    if callable(display_label):
        return str(display_label())
    return str(binding)


__all__ = [
    "CONTINUATION_PREFIX",
    "ITEM_PREFIX",
    "OVERFLOW_PREFIX",
    "PREVIEW_LINE_LIMIT",
    "PendingInputPreview",
    "RUST_MODULE",
    "Rect",
    "RenderedLine",
    "SECTION_PREFIX",
    "desired_height",
    "render",
]
