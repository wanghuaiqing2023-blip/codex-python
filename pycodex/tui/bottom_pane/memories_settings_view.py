"""Semantic port of codex-rs/tui/src/bottom_pane/memories_settings_view.rs.

The Rust module renders a ratatui popup. This Python port keeps the same
menu state machine, row content, toggle/save/reset semantics, and exposes a
plain text render model instead of framework widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::memories_settings_view",
    source="codex/codex-rs/tui/src/bottom_pane/memories_settings_view.rs",
    status="complete",
)

MEMORIES_DOC_URL = "https://developers.openai.com/codex/memories"
MEMORIES_SETTINGS_HINT = "Press Space to toggle; Enter to save or select"


class MemoriesSetting(str, Enum):
    USE = "use"
    GENERATE = "generate"


class MemoriesAction(str, Enum):
    RESET = "reset"


@dataclass
class MemoriesMenuItem:
    kind: str
    name: str
    description: str
    setting: Optional[MemoriesSetting] = None
    action: Optional[MemoriesAction] = None
    enabled: bool = False

    @classmethod
    def setting_item(
        cls,
        setting: MemoriesSetting,
        name: str,
        description: str,
        enabled: bool,
    ) -> "MemoriesMenuItem":
        return cls(
            kind="setting",
            setting=setting,
            name=name,
            description=description,
            enabled=enabled,
        )

    @classmethod
    def action_item(
        cls,
        action: MemoriesAction,
        name: str,
        description: str,
    ) -> "MemoriesMenuItem":
        return cls(kind="action", action=action, name=name, description=description)


@dataclass(frozen=True)
class RenderedMemoriesSettings:
    title: str
    subtitle: str
    rows: Tuple[str, ...]
    docs_link: Optional[str]
    footer_hint: str
    desired_height: int


class MemoriesSettingsView:
    """State machine for the memories settings popup."""

    def __init__(
        self,
        use_memories: bool,
        generate_memories: bool,
        app_event_tx: Optional[Any] = None,
        keymap: Optional[Any] = None,
    ) -> None:
        self.items = [
            MemoriesMenuItem.setting_item(
                MemoriesSetting.USE,
                "Use memories",
                "Use memories in the following threads. Applied at next thread.",
                use_memories,
            ),
            MemoriesMenuItem.setting_item(
                MemoriesSetting.GENERATE,
                "Generate memories",
                "Generate memories from the following threads. Current thread included.",
                generate_memories,
            ),
            MemoriesMenuItem.action_item(
                MemoriesAction.RESET,
                "Reset all memories",
                "Clear local memory files and summaries. Existing threads stay intact.",
            ),
        ]
        self.state = ScrollState()
        if self.items:
            self.state.selected_idx = 0
        self.reset_confirmation: Optional[ScrollState] = None
        self.complete = False
        self.app_event_tx = app_event_tx
        self.docs_link = MEMORIES_DOC_URL
        self.keymap = keymap
        self.emitted_events: List[dict] = []

    @classmethod
    def new(
        cls,
        use_memories: bool,
        generate_memories: bool,
        app_event_tx: Optional[Any] = None,
        keymap: Optional[Any] = None,
    ) -> "MemoriesSettingsView":
        return cls(use_memories, generate_memories, app_event_tx, keymap)

    def initialize_selection(self) -> None:
        if self.items and self.state.selected_idx is None:
            self.state.selected_idx = 0

    def settings_header(self) -> Tuple[str, str]:
        return (
            "Memories",
            "Choose how Codex uses and creates memories. Changes are saved to config.toml",
        )

    def reset_confirmation_header(self) -> Tuple[str, str]:
        return (
            "Reset all memories?",
            "This clears local memory files and rollout summaries for the current Codex home.",
        )

    def active_state(self) -> ScrollState:
        return self.reset_confirmation if self.reset_confirmation is not None else self.state

    def active_state_mut(self) -> ScrollState:
        return self.active_state()

    def visible_len(self) -> int:
        return 2 if self.reset_confirmation is not None else len(self.items)

    def build_rows(self) -> List[str]:
        if self.reset_confirmation is not None:
            selected = self.reset_confirmation.selected_idx
            return [
                self._row(
                    "Reset all memories",
                    "Delete local memory files and rollout summaries.",
                    selected == 0,
                ),
                self._row("Go back", "Return to memory settings.", selected == 1),
            ]

        selected = self.state.selected_idx
        rows: List[str] = []
        for index, item in enumerate(self.items):
            label = item.name
            if item.kind == "setting":
                label = f"[{'x' if item.enabled else ' '}] {label}"
            rows.append(self._row(label, item.description, selected == index))
        return rows

    def _row(self, label: str, description: str, selected: bool) -> str:
        prefix = "> " if selected else "  "
        return f"{prefix}{label} - {description}"

    def move_up(self) -> None:
        self._move(-1)

    def move_down(self) -> None:
        self._move(1)

    def page_up(self) -> None:
        self._move(-MAX_POPUP_ROWS)

    def page_down(self) -> None:
        self._move(MAX_POPUP_ROWS)

    def jump_top(self) -> None:
        if self.visible_len():
            self.active_state().selected_idx = 0

    def jump_bottom(self) -> None:
        if self.visible_len():
            self.active_state().selected_idx = self.visible_len() - 1

    def _move(self, delta: int) -> None:
        visible = self.visible_len()
        if visible == 0:
            return
        state = self.active_state()
        current = 0 if state.selected_idx is None else state.selected_idx
        state.selected_idx = max(0, min(visible - 1, current + delta))

    def toggle_selected(self) -> None:
        if self.reset_confirmation is not None:
            return
        selected = self.state.selected_idx
        if selected is None or selected >= len(self.items):
            return
        item = self.items[selected]
        if item.kind == "setting":
            item.enabled = not item.enabled

    def rows_width(self, total_width: int) -> int:
        return max(0, total_width - 2)

    def current_setting(self, setting: MemoriesSetting) -> bool:
        for item in self.items:
            if item.kind == "setting" and item.setting == setting:
                return item.enabled
        return False

    def open_reset_confirmation(self) -> None:
        self.reset_confirmation = ScrollState()
        self.reset_confirmation.selected_idx = 0

    def close_reset_confirmation(self) -> None:
        self.reset_confirmation = None
        if self.items:
            self.state.selected_idx = len(self.items) - 1

    def footer_hint(self) -> str:
        if self.reset_confirmation is not None:
            return "Enter to select; Esc to cancel"
        return MEMORIES_SETTINGS_HINT

    def handle_key_event(self, key_event: Any) -> str:
        key = self._normalize_key(key_event)
        if key in {"up", "k"}:
            self.move_up()
        elif key in {"down", "j"}:
            self.move_down()
        elif key in {"pageup", "page_up"}:
            self.page_up()
        elif key in {"pagedown", "page_down"}:
            self.page_down()
        elif key in {"home", "g"}:
            self.jump_top()
        elif key in {"end", "G"}:
            self.jump_bottom()
        elif key in {"space", " "}:
            self.toggle_selected()
        elif key in {"enter", "return"}:
            self.save()
        elif key in {"esc", "escape", "cancel"}:
            self.cancel()
        else:
            return "ignored"
        return "handled"

    def _normalize_key(self, key_event: Any) -> str:
        if isinstance(key_event, str):
            return key_event
        if isinstance(key_event, dict):
            return str(key_event.get("key") or key_event.get("code") or "")
        return str(getattr(key_event, "key", getattr(key_event, "code", key_event)))

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.cancel()
        return "handled"

    def save(self) -> None:
        if self.reset_confirmation is not None:
            selected = self.reset_confirmation.selected_idx
            if selected == 0:
                self._emit({"type": "ResetMemories"})
                self.complete = True
            else:
                self.close_reset_confirmation()
            return

        selected = self.state.selected_idx
        if selected is not None and selected < len(self.items):
            item = self.items[selected]
            if item.kind == "action" and item.action == MemoriesAction.RESET:
                self.open_reset_confirmation()
                return

        self._emit(
            {
                "type": "UpdateMemorySettings",
                "use_memories": self.current_setting(MemoriesSetting.USE),
                "generate_memories": self.current_setting(MemoriesSetting.GENERATE),
            }
        )
        self.complete = True

    def cancel(self) -> None:
        if self.reset_confirmation is not None:
            self.close_reset_confirmation()
        else:
            self.complete = True

    def _emit(self, event: dict) -> None:
        self.emitted_events.append(event)
        sender = self.app_event_tx
        if sender is None:
            return
        if hasattr(sender, "send"):
            sender.send(event)
        elif callable(sender):
            sender(event)

    def render(self, width: int = 80) -> RenderedMemoriesSettings:
        title, subtitle = (
            self.reset_confirmation_header()
            if self.reset_confirmation is not None
            else self.settings_header()
        )
        rows = tuple(self._clip_rows(self.build_rows(), self.rows_width(width)))
        docs_link = None if self.reset_confirmation is not None else self.docs_link
        desired_height_value = 2 + len(rows) + 1 + (1 if docs_link else 0) + 1
        return RenderedMemoriesSettings(
            title=title,
            subtitle=subtitle,
            rows=rows,
            docs_link=docs_link,
            footer_hint=self.footer_hint(),
            desired_height=desired_height_value,
        )

    def desired_height(self, width: int = 80) -> int:
        return self.render(width).desired_height

    def render_lines(self, width: int = 80) -> List[str]:
        rendered = self.render(width)
        lines = [rendered.title, rendered.subtitle, *rendered.rows]
        if rendered.docs_link is not None:
            lines.append(rendered.docs_link)
        lines.append(rendered.footer_hint)
        return lines

    def _clip_rows(self, rows: Iterable[str], width: int) -> Iterable[str]:
        for row in rows:
            yield row if len(row) <= width else row[:width]


def handle_key_event(view: MemoriesSettingsView, key_event: Any) -> str:
    return view.handle_key_event(key_event)


def is_complete(view: MemoriesSettingsView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: MemoriesSettingsView) -> str:
    return view.on_ctrl_c()


def render(view: MemoriesSettingsView, width: int = 80) -> RenderedMemoriesSettings:
    return view.render(width)


def desired_height(view: MemoriesSettingsView, width: int = 80) -> int:
    return view.desired_height(width)


def memories_settings_hint_line() -> str:
    return MEMORIES_SETTINGS_HINT


__all__ = [
    "MEMORIES_DOC_URL",
    "MEMORIES_SETTINGS_HINT",
    "MemoriesAction",
    "MemoriesMenuItem",
    "MemoriesSetting",
    "MemoriesSettingsView",
    "RenderedMemoriesSettings",
    "RUST_MODULE",
    "desired_height",
    "handle_key_event",
    "is_complete",
    "memories_settings_hint_line",
    "on_ctrl_c",
    "render",
]
