"""Semantic slice for Rust ``codex-tui::public_widgets::composer_input``.

Rust wraps the internal ``ChatComposer``.  Python keeps the public wrapper
contract available with a dependency-light text-input model; full ChatComposer
paste-burst heuristics and ratatui buffer rendering remain explicit boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="public_widgets::composer_input", source="codex/codex-rs/tui/src/public_widgets/composer_input.rs")

RECOMMENDED_FLUSH_DELAY_SECONDS = 0.05


@dataclass(frozen=True)
class ComposerAction:
    kind: str
    text: str | None = None

    @classmethod
    def submitted(cls, text: str) -> "ComposerAction":
        return cls("submitted", text)

    @classmethod
    def none(cls) -> "ComposerAction":
        return cls("none")


@dataclass
class ComposerInput:
    text: str = ""
    placeholder: str = "Compose new task"
    enhanced_keys_supported: bool = True
    disable_paste_burst: bool = False
    hint_items: tuple[tuple[str, str], ...] | None = None
    _events: list[Any] = field(default_factory=list)
    _paste_burst_active: bool = False

    @classmethod
    def new(cls) -> "ComposerInput":
        return cls()

    def is_empty(self) -> bool:
        return self.text == ""

    def clear(self) -> None:
        self.text = ""
        self._paste_burst_active = False

    def input(self, key: Any) -> ComposerAction:
        code, modifiers = _event_parts(key)
        action = ComposerAction.none()
        if code == "Enter" and "shift" not in modifiers:
            submitted = self.text
            self.clear()
            action = ComposerAction.submitted(submitted)
        elif code == "Enter" and "shift" in modifiers:
            self.text += "\n"
        elif len(code) == 1 and "control" not in modifiers and "alt" not in modifiers:
            self.text += code
        elif code == "Backspace" and self.text:
            self.text = self.text[:-1]
        self.drain_app_events()
        return action

    def handle_paste(self, pasted: str) -> bool:
        if pasted == "":
            self.drain_app_events()
            return False
        self.text += str(pasted)
        self._paste_burst_active = not self.disable_paste_burst
        self.drain_app_events()
        return True

    def set_hint_items(self, items: Iterable[tuple[Any, Any]]) -> None:
        self.hint_items = tuple((str(key), str(label)) for key, label in items)

    def clear_hint_items(self) -> None:
        self.hint_items = None

    def desired_height(self, width: int) -> int:
        width = max(int(width), 1)
        line_count = 0
        for line in (self.text or self.placeholder).split("\n"):
            line_count += max(1, (len(line) + width - 1) // width)
        footer = 1
        return max(1, line_count + footer)

    def cursor_pos(self, area: Any) -> tuple[int, int] | None:
        x, y, width, height = _rect_parts(area)
        if width <= 0 or height <= 0:
            return None
        before_cursor = self.text.split("\n")[-1]
        row = self.text.count("\n") + len(before_cursor) // max(width, 1)
        col = len(before_cursor) % max(width, 1)
        if row >= height:
            return None
        return (x + col, y + row)

    def render_ref(self, area: Any, buf: Any | None = None) -> dict[str, Any]:
        x, y, width, height = _rect_parts(area)
        visible_text = self.text if self.text else self.placeholder
        lines = visible_text.split("\n")[: max(height, 0)]
        rendered = {"area": (x, y, width, height), "lines": tuple(lines), "hint_items": self.hint_items}
        if isinstance(buf, list):
            buf.append(rendered)
        elif isinstance(buf, dict):
            buf.update(rendered)
        return rendered

    def is_in_paste_burst(self) -> bool:
        return self._paste_burst_active

    def flush_paste_burst_if_due(self) -> bool:
        was_active = self._paste_burst_active
        self._paste_burst_active = False
        self.drain_app_events()
        return was_active

    @staticmethod
    def recommended_flush_delay() -> float:
        return RECOMMENDED_FLUSH_DELAY_SECONDS

    def drain_app_events(self) -> None:
        self._events.clear()


def default() -> ComposerInput:
    return ComposerInput.new()


def _event_parts(key: Any) -> tuple[str, frozenset[str]]:
    if isinstance(key, dict):
        code = str(key.get("code", key.get("key", "")))
        modifiers = key.get("modifiers") or ()
    else:
        code = str(getattr(key, "code", key))
        modifiers = getattr(key, "modifiers", ())
    if code.lower() == "enter":
        code = "Enter"
    elif code.lower() == "backspace":
        code = "Backspace"
    normalized = frozenset(str(modifier).lower().replace("ctrl", "control") for modifier in modifiers)
    return code, normalized


def _rect_parts(area: Any) -> tuple[int, int, int, int]:
    if isinstance(area, dict):
        return (int(area.get("x", 0)), int(area.get("y", 0)), int(area.get("width", 0)), int(area.get("height", 0)))
    if isinstance(area, (tuple, list)) and len(area) >= 4:
        return (int(area[0]), int(area[1]), int(area[2]), int(area[3]))
    return (int(getattr(area, "x", 0)), int(getattr(area, "y", 0)), int(getattr(area, "width", 0)), int(getattr(area, "height", 0)))


__all__ = [
    "ComposerAction",
    "ComposerInput",
    "RECOMMENDED_FLUSH_DELAY_SECONDS",
    "RUST_MODULE",
    "default",
]
