"""Experimental feature toggle view.

Python port of Rust ``codex-tui::bottom_pane::experimental_features_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::experimental_features_view",
    source="codex/codex-rs/tui/src/bottom_pane/experimental_features_view.rs",
    status="complete",
)


@dataclass
class ExperimentalFeatureItem:
    feature: Any
    name: str
    description: str
    enabled: bool


@dataclass(frozen=True)
class DisplayRow:
    name: str
    description: Optional[str] = None
    selected: bool = False


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class ExperimentalFeaturesView:
    features: List[ExperimentalFeatureItem]
    app_event_tx: Any = None
    keymap: Any = None
    selected_idx: Optional[int] = None
    scroll_top: int = 0
    complete: bool = False
    header: Tuple[str, str] = (
        "Experimental features",
        "Toggle experimental features. Changes are saved to config.toml.",
    )
    footer_hint: str = field(default_factory=lambda: experimental_popup_hint_line())

    @classmethod
    def new(
        cls,
        features: Iterable[ExperimentalFeatureItem],
        app_event_tx: Any = None,
        keymap: Any = None,
    ) -> "ExperimentalFeaturesView":
        view = cls(list(features), app_event_tx=app_event_tx, keymap=keymap)
        view.initialize_selection()
        return view

    def initialize_selection(self) -> None:
        if self.visible_len() == 0:
            self.selected_idx = None
        elif self.selected_idx is None:
            self.selected_idx = 0

    def visible_len(self) -> int:
        return len(self.features)

    def build_rows(self) -> List[DisplayRow]:
        rows = []
        for idx, item in enumerate(self.features):
            prefix = "›" if self.selected_idx == idx else " "
            marker = "x" if item.enabled else " "
            rows.append(
                DisplayRow(
                    name="{} [{}] {}".format(prefix, marker, item.name),
                    description=item.description,
                    selected=self.selected_idx == idx,
                )
            )
        return rows

    def move_up(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current - 1) % length
        self._ensure_visible(length)

    def move_down(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current + 1) % length
        self._ensure_visible(length)

    def page_up(self) -> None:
        length = self.visible_len()
        visible = min(MAX_POPUP_ROWS, length)
        if length == 0 or visible == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = max(0, current - visible)
        self._ensure_visible(length)

    def page_down(self) -> None:
        length = self.visible_len()
        visible = min(MAX_POPUP_ROWS, length)
        if length == 0 or visible == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = min(length - 1, current + visible)
        self._ensure_visible(length)

    def jump_top(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        self.selected_idx = 0
        self._ensure_visible(length)

    def jump_bottom(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        self.selected_idx = length - 1
        self._ensure_visible(length)

    def toggle_selected(self) -> None:
        if self.selected_idx is None:
            return
        if 0 <= self.selected_idx < len(self.features):
            self.features[self.selected_idx].enabled = not self.features[self.selected_idx].enabled

    @staticmethod
    def rows_width(total_width: int) -> int:
        return max(0, int(total_width) - 2)

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if _keymap_pressed(self.keymap, "move_up", key_event, key) or key in {"up", "k"}:
            self.move_up()
        elif _keymap_pressed(self.keymap, "move_down", key_event, key) or key in {"down", "j"}:
            self.move_down()
        elif _keymap_pressed(self.keymap, "page_up", key_event, key) or key in {"pageup", "page_up"}:
            self.page_up()
        elif _keymap_pressed(self.keymap, "page_down", key_event, key) or key in {"pagedown", "page_down"}:
            self.page_down()
        elif _keymap_pressed(self.keymap, "jump_top", key_event, key) or key in {"home", "g"}:
            self.jump_top()
        elif _keymap_pressed(self.keymap, "jump_bottom", key_event, key) or key in {"end", "shift+g"}:
            self.jump_bottom()
        elif key == " ":
            self.toggle_selected()
        elif _keymap_pressed(self.keymap, "accept", key_event, key) or _keymap_pressed(
            self.keymap, "cancel", key_event, key
        ) or key in {"enter", "esc"}:
            self.on_ctrl_c()

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        if self.features:
            _send(
                self.app_event_tx,
                {
                    "type": "UpdateFeatureFlags",
                    "updates": [(item.feature, item.enabled) for item in self.features],
                },
            )
        self.complete = True
        return "Handled"

    def desired_height(self, width: int) -> int:
        del width
        rows_height = min(MAX_POPUP_ROWS, len(self.build_rows()))
        if not self.features:
            rows_height = 1
        header_height = len(self.header)
        return header_height + rows_height + 4

    def render(self, area: Any = None, buf: Any = None) -> List[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        lines = [
            DisplayLine(self.header[0], "title"),
            DisplayLine(self.header[1], "dim"),
            DisplayLine(""),
        ]
        rows = self.build_rows()
        if rows:
            for row in rows[self.scroll_top : self.scroll_top + MAX_POPUP_ROWS]:
                lines.append(DisplayLine(row.name, "selected" if row.selected else "plain"))
                if row.description:
                    lines.append(DisplayLine(row.description, "description"))
        else:
            lines.append(DisplayLine("  No experimental features available for now", "empty"))
        lines.append(DisplayLine(self.footer_hint, "hint"))
        rendered = lines[:height]
        if buf is not None and hasattr(buf, "extend"):
            buf.extend(rendered)
        return rendered

    def _ensure_visible(self, length: int) -> None:
        if self.selected_idx is None:
            self.scroll_top = 0
            return
        visible = min(MAX_POPUP_ROWS, length)
        if visible == 0:
            self.scroll_top = 0
            return
        if self.selected_idx < self.scroll_top:
            self.scroll_top = self.selected_idx
        elif self.selected_idx >= self.scroll_top + visible:
            self.scroll_top = self.selected_idx + 1 - visible
        self.scroll_top = max(0, min(self.scroll_top, max(0, length - visible)))


def handle_key_event(view: ExperimentalFeaturesView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: ExperimentalFeaturesView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: ExperimentalFeaturesView) -> str:
    return view.on_ctrl_c()


def render(view: ExperimentalFeaturesView, area: Any = None, buf: Any = None) -> List[DisplayLine]:
    return view.render(area, buf)


def desired_height(view: ExperimentalFeaturesView, width: int) -> int:
    return view.desired_height(width)


def experimental_popup_hint_line() -> str:
    return "Press Space to select or Enter to save for next conversation"


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event if key_event == " " else key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            text = str(value)
            return text if text == " " else text.lower()
    text = str(key_event)
    return text if text == " " else text.lower()


def _send(target: Any, event: Dict[str, Any]) -> None:
    if target is None:
        return
    if hasattr(target, "send"):
        target.send(event)
    elif hasattr(target, "append"):
        target.append(event)
    elif callable(target):
        target(event)
    elif hasattr(target, "events"):
        target.events.append(event)


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


def _keymap_pressed(keymap: Any, binding_name: str, key_event: Any, key: str) -> bool:
    if keymap is None:
        return False
    binding = getattr(keymap, binding_name, None)
    if binding is None and isinstance(keymap, dict):
        binding = keymap.get(binding_name)
    if binding is None:
        return False
    if hasattr(binding, "is_pressed"):
        return bool(binding.is_pressed(key_event))
    if callable(binding):
        return bool(binding(key_event))
    if isinstance(binding, (set, list, tuple)):
        return key in {str(item).lower() for item in binding}
    return key == str(binding).lower()


__all__ = [
    "DisplayLine",
    "DisplayRow",
    "ExperimentalFeatureItem",
    "ExperimentalFeaturesView",
    "RUST_MODULE",
    "desired_height",
    "experimental_popup_hint_line",
    "handle_key_event",
    "is_complete",
    "on_ctrl_c",
    "render",
]
