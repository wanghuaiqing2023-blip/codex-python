"""Custom prompt bottom-pane view.

Python port of Rust ``codex-tui::bottom_pane::custom_prompt_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .._porting import RustTuiModule
from .popup_consts import standard_popup_hint_line

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::custom_prompt_view",
    source="codex/codex-rs/tui/src/bottom_pane/custom_prompt_view.rs",
)

PromptSubmitted = Callable[[str], None]
GUTTER = "▌"


class ViewCompletion(Enum):
    ACCEPTED = "Accepted"
    CANCELLED = "Cancelled"


class CancellationEvent(Enum):
    HANDLED = "Handled"


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class SimpleTextArea:
    text_value: str = ""
    cursor: int = 0

    @classmethod
    def new(cls) -> "SimpleTextArea":
        return cls()

    def set_text_clearing_elements(self, text: str) -> None:
        self.text_value = str(text)
        self.cursor = min(self.cursor, len(self.text_value))

    def set_cursor(self, cursor: int) -> None:
        self.cursor = max(0, min(int(cursor), len(self.text_value)))

    def text(self) -> str:
        return self.text_value

    def insert_str(self, text: str) -> None:
        text = str(text)
        self.text_value = self.text_value[: self.cursor] + text + self.text_value[self.cursor :]
        self.cursor += len(text)

    def input(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if key == "enter":
            self.insert_str("\n")
        elif key == "backspace":
            if self.cursor > 0:
                self.text_value = self.text_value[: self.cursor - 1] + self.text_value[self.cursor :]
                self.cursor -= 1
        elif len(key) == 1:
            self.insert_str(key)

    def desired_height(self, width: int) -> int:
        width = max(1, int(width))
        if self.text_value == "":
            return 1
        total = 0
        for line in self.text_value.split("\n"):
            total += max(1, (len(line) + width - 1) // width)
        return total

    def cursor_pos_with_rect(self, x: int, y: int, width: int, height: int) -> tuple[int, int] | None:
        if width <= 0 or height <= 0:
            return None
        before = self.text_value[: self.cursor]
        row = 0
        col = 0
        for ch in before:
            if ch == "\n":
                row += 1
                col = 0
            else:
                col += 1
                if col >= width:
                    row += 1
                    col = 0
        if row >= height:
            row = height - 1
        return (x + col, y + row)


@dataclass
class CustomPromptView:
    title: str
    placeholder: str
    context_label: str | None
    on_submit: PromptSubmitted
    textarea: SimpleTextArea = field(default_factory=SimpleTextArea.new)
    completion_value: ViewCompletion | None = None

    @classmethod
    def new(
        cls,
        title: str,
        placeholder: str,
        initial_text: str,
        context_label: str | None,
        on_submit: PromptSubmitted,
    ) -> "CustomPromptView":
        textarea = SimpleTextArea.new()
        if initial_text:
            textarea.set_text_clearing_elements(initial_text)
            textarea.set_cursor(len(initial_text))
        return cls(
            title=str(title),
            placeholder=str(placeholder),
            context_label=context_label,
            on_submit=on_submit,
            textarea=textarea,
        )

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if key == "esc":
            self.on_ctrl_c()
        elif key == "enter" and not _has_modifier(key_event):
            text = self.textarea.text().strip()
            if text:
                self.on_submit(text)
                self.completion_value = ViewCompletion.ACCEPTED
        else:
            self.textarea.input(key_event)

    def on_ctrl_c(self) -> CancellationEvent:
        self.completion_value = ViewCompletion.CANCELLED
        return CancellationEvent.HANDLED

    def is_complete(self) -> bool:
        return self.completion_value is not None

    def completion(self) -> ViewCompletion | None:
        return self.completion_value

    def handle_paste(self, pasted: str) -> bool:
        if pasted == "":
            return False
        self.textarea.insert_str(pasted)
        return True

    def desired_height(self, width: int) -> int:
        extra_top = 1 if self.context_label is not None else 0
        return 1 + extra_top + self.input_height(width) + 3

    def input_height(self, width: int) -> int:
        usable_width = max(0, int(width) - 2)
        text_height = min(8, max(1, self.textarea.desired_height(usable_width)))
        return min(9, text_height + 1)

    def render(self, area: Any = None, buf: Any = None) -> list[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        lines: list[DisplayLine] = [DisplayLine(f"{gutter()}{self.title}", "title")]
        if self.context_label is not None:
            lines.append(DisplayLine(f"{gutter()}{self.context_label}", "context"))
        lines.append(DisplayLine(gutter(), "gutter"))
        text = self.textarea.text()
        if text:
            for line in text.split("\n"):
                lines.append(DisplayLine(line))
        else:
            lines.append(DisplayLine(self.placeholder, "placeholder"))
        lines.append(DisplayLine(""))
        lines.append(DisplayLine(standard_popup_hint_line(), "hint"))
        return lines[:height]

    def cursor_pos(self, area: Any) -> tuple[int, int] | None:
        width = _area_width(area)
        height = _area_height(area)
        x = _area_x(area)
        y = _area_y(area)
        if height < 2 or width <= 2:
            return None
        text_area_height = self.input_height(width) - 1
        if text_area_height == 0:
            return None
        extra_offset = 1 if self.context_label is not None else 0
        top_line_count = 1 + extra_offset
        return self.textarea.cursor_pos_with_rect(
            x + 2,
            y + top_line_count + 1,
            width - 2,
            text_area_height,
        )


def handle_key_event(view: CustomPromptView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: CustomPromptView) -> CancellationEvent:
    return view.on_ctrl_c()


def is_complete(view: CustomPromptView) -> bool:
    return view.is_complete()


def completion(view: CustomPromptView) -> ViewCompletion | None:
    return view.completion()


def handle_paste(view: CustomPromptView, pasted: str) -> bool:
    return view.handle_paste(pasted)


def desired_height(view: CustomPromptView, width: int) -> int:
    return view.desired_height(width)


def render(view: CustomPromptView, area: Any = None, buf: Any = None) -> list[DisplayLine]:
    return view.render(area, buf)


def cursor_pos(view: CustomPromptView, area: Any) -> tuple[int, int] | None:
    return view.cursor_pos(area)


def gutter() -> str:
    return GUTTER


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            return str(value).lower()
    return str(key_event).lower()


def _has_modifier(key_event: Any) -> bool:
    if isinstance(key_event, str):
        return False
    modifiers = getattr(key_event, "modifiers", None)
    return bool(modifiers)


def _area_x(area: Any) -> int:
    if isinstance(area, dict):
        return int(area.get("x", 0))
    if isinstance(area, tuple) and len(area) >= 1:
        return int(area[0])
    return int(getattr(area, "x", 0))


def _area_y(area: Any) -> int:
    if isinstance(area, dict):
        return int(area.get("y", 0))
    if isinstance(area, tuple) and len(area) >= 2:
        return int(area[1])
    return int(getattr(area, "y", 0))


def _area_width(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("width", 0))
    if isinstance(area, tuple) and len(area) >= 3:
        return int(area[2])
    return int(getattr(area, "width", 0))


def _area_height(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("height", 0))
    if isinstance(area, tuple) and len(area) >= 4:
        return int(area[3])
    return int(getattr(area, "height", 0))


__all__ = [
    "CancellationEvent",
    "CustomPromptView",
    "DisplayLine",
    "GUTTER",
    "PromptSubmitted",
    "RUST_MODULE",
    "SimpleTextArea",
    "ViewCompletion",
    "completion",
    "cursor_pos",
    "desired_height",
    "gutter",
    "handle_key_event",
    "handle_paste",
    "is_complete",
    "on_ctrl_c",
    "render",
]
