"""Custom prompt bottom-pane view.

Python port of Rust ``codex-tui::bottom_pane::custom_prompt_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from .._porting import RustTuiModule
from .bottom_pane_view import BottomPaneViewDefaults, CancellationEvent, ViewCompletion
from .popup_consts import standard_popup_hint_line
from .selection_popup_common import TerminalPopupLine
from .textarea import TextArea, TextAreaState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::custom_prompt_view",
    source="codex/codex-rs/tui/src/bottom_pane/custom_prompt_view.rs",
    status="complete",
)

PromptSubmitted = Callable[[str], None]
GUTTER = "▌ "


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class CustomPromptView(BottomPaneViewDefaults):
    title: str
    placeholder: str
    context_label: Optional[str]
    on_submit: PromptSubmitted
    textarea: TextArea = field(default_factory=TextArea.new)
    textarea_state: TextAreaState = field(default_factory=TextAreaState)
    completion_value: Optional[ViewCompletion] = None

    @classmethod
    def new(
        cls,
        title: str,
        placeholder: str,
        initial_text: str,
        context_label: Optional[str],
        on_submit: PromptSubmitted,
    ) -> "CustomPromptView":
        textarea = TextArea.new()
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

    def completion(self) -> Optional[ViewCompletion]:
        return self.completion_value

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        area = {"width": max(1, int(width)), "height": self.desired_height(width)}
        return [TerminalPopupLine(line.text, line.style in {"title", "selected"}) for line in self.render(area)]

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

    def render(self, area: Any = None, buf: Any = None) -> List[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        lines: List[DisplayLine] = [DisplayLine(f"{gutter()}{self.title}", "title")]
        if self.context_label is not None:
            lines.append(DisplayLine(f"{gutter()}{self.context_label}", "context"))

        input_height = self.input_height(width)
        text_area_height = max(0, input_height - 1)
        lines.extend(DisplayLine(gutter(), "gutter") for _ in range(input_height))
        if text_area_height:
            ranges = self.textarea.wrapped_lines(max(1, width - 2))
            scroll = self.textarea.effective_scroll(text_area_height, ranges, self.textarea_state.scroll)
            self.textarea_state.scroll = scroll
            visible_ranges = ranges[scroll : scroll + text_area_height]
            input_text_start = len(lines) - input_height + 1
            if self.textarea.text():
                for offset, text_range in enumerate(visible_ranges):
                    text = self.textarea.text()[text_range.start : text_range.stop]
                    lines[input_text_start + offset] = DisplayLine(f"{gutter()}{text}")
            else:
                lines[input_text_start] = DisplayLine(f"{gutter()}{self.placeholder}", "placeholder")
        lines.append(DisplayLine(""))
        lines.append(DisplayLine(standard_popup_hint_line(), "hint"))
        return lines[:height]

    def cursor_pos(self, area: Any) -> Optional[Tuple[int, int]]:
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
        return self.textarea.cursor_pos_with_state(
            {
                "x": x + 2,
                "y": y + top_line_count + 1,
                "width": width - 2,
                "height": text_area_height,
            },
            self.textarea_state,
        )


def handle_key_event(view: CustomPromptView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: CustomPromptView) -> CancellationEvent:
    return view.on_ctrl_c()


def is_complete(view: CustomPromptView) -> bool:
    return view.is_complete()


def completion(view: CustomPromptView) -> Optional[ViewCompletion]:
    return view.completion()


def handle_paste(view: CustomPromptView, pasted: str) -> bool:
    return view.handle_paste(pasted)


def desired_height(view: CustomPromptView, width: int) -> int:
    return view.desired_height(width)


def render(view: CustomPromptView, area: Any = None, buf: Any = None) -> List[DisplayLine]:
    return view.render(area, buf)


def cursor_pos(view: CustomPromptView, area: Any) -> Optional[Tuple[int, int]]:
    return view.cursor_pos(area)


def gutter() -> str:
    return GUTTER


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event if len(key_event) == 1 else key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            text = str(value)
            return text if len(text) == 1 else text.lower()
    text = str(key_event)
    return text if len(text) == 1 else text.lower()


def _has_modifier(key_event: Any) -> bool:
    if isinstance(key_event, str):
        return False
    modifiers = getattr(key_event, "modifiers", None)
    if modifiers is None or modifiers is False or modifiers == 0:
        return False
    if isinstance(modifiers, str):
        return modifiers.strip().lower() not in {"", "none", "keymodifiers.none"}
    name = getattr(modifiers, "name", None)
    if isinstance(name, str) and name.lower() == "none":
        return False
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
    "TextArea",
    "TextAreaState",
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
