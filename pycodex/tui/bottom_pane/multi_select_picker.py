"""Multi-select picker behavior for Rust ``codex-tui::bottom_pane::multi_select_picker``.

Python models the picker state machine and visible row DTOs while leaving
ratatui rendering and exhaustive keymap dispatch as renderer/runtime slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable

from .._porting import RustTuiModule, not_ported
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState
from .selection_popup_common import GenericDisplayRow

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::multi_select_picker",
    source="codex/codex-rs/tui/src/bottom_pane/multi_select_picker.rs",
)

ITEM_NAME_TRUNCATE_LEN = 21
SEARCH_PLACEHOLDER = "Type to search"
SEARCH_PROMPT_PREFIX = "> "
SECTION_BREAK_ROW = "  -----------------------"


class Direction(Enum):
    UP = "Up"
    DOWN = "Down"


ChangeCallBack = Callable[[list["MultiSelectItem"], Any], None]
ConfirmCallback = Callable[[list[str], Any], None]
CancelCallback = Callable[[Any], None]
PreviewCallback = Callable[[list["MultiSelectItem"]], Any | None]


@dataclass
class MultiSelectItem:
    id: str = ""
    name: str = ""
    description: str | None = None
    enabled: bool = False
    orderable: bool = True
    section_break_after: bool = False


def default() -> MultiSelectItem:
    return MultiSelectItem()


@dataclass
class BuiltRows:
    rows: list[GenericDisplayRow] = field(default_factory=list)
    state: ScrollState = field(default_factory=ScrollState.new)


@dataclass
class MultiSelectPicker:
    items: list[MultiSelectItem]
    state: ScrollState
    complete: bool
    app_event_tx: Any
    title: str
    subtitle: str | None = None
    footer_hint: str = ""
    search_query: str = ""
    filtered_indices: list[int] = field(default_factory=list)
    ordering_enabled: bool = False
    keymap: Any = None
    preview_builder: PreviewCallback | None = None
    preview_line: Any | None = None
    on_change: ChangeCallBack | None = None
    on_confirm: ConfirmCallback | None = None
    on_cancel: CancelCallback | None = None

    @classmethod
    def builder(cls, title: str, subtitle: str | None, app_event_tx: Any) -> "MultiSelectPickerBuilder":
        return MultiSelectPickerBuilder.new(title, subtitle, app_event_tx)

    def apply_filter(self) -> None:
        previous = self.state.selected_idx
        previous_actual = None
        if previous is not None and 0 <= previous < len(self.filtered_indices):
            previous_actual = self.filtered_indices[previous]

        query = self.search_query.strip()
        if not query:
            self.filtered_indices = list(range(len(self.items)))
        else:
            matches: list[tuple[int, int, str]] = []
            for idx, item in enumerate(self.items):
                result = match_item(query, item.name, item.name)
                if result is not None:
                    _indices, score = result
                    matches.append((idx, score, item.name))
            matches.sort(key=lambda value: (value[1], value[2]))
            self.filtered_indices = [idx for idx, _score, _name in matches]

        length = len(self.filtered_indices)
        selected = None
        if previous_actual is not None and previous_actual in self.filtered_indices:
            selected = self.filtered_indices.index(previous_actual)
        elif length > 0:
            selected = 0
        self.state.selected_idx = selected
        visible = self.max_visible_rows(length)
        self.state.clamp_selection(length)
        self.state.ensure_visible(length, visible)

    def visible_len(self) -> int:
        return len(self.filtered_indices)

    @staticmethod
    def max_visible_rows(length: int) -> int:
        return min(MAX_POPUP_ROWS, max(int(length), 1))

    @staticmethod
    def rows_width(total_width: int) -> int:
        return max(int(total_width) - 2, 0)

    def rows_height(self, rows: BuiltRows) -> int:
        return min(max(len(rows.rows), 1), MAX_POPUP_ROWS)

    def build_rows(self) -> BuiltRows:
        rows: list[GenericDisplayRow] = []
        visible_to_row: list[int] = []
        for visible_idx, actual_idx in enumerate(self.filtered_indices):
            if actual_idx < 0 or actual_idx >= len(self.items):
                continue
            item = self.items[actual_idx]
            visible_to_row.append(len(rows))
            selected = self.state.selected_idx == visible_idx
            prefix = ">" if selected else " "
            marker = "x" if item.enabled else " "
            item_name = truncate_text(item.name, ITEM_NAME_TRUNCATE_LEN)
            rows.append(GenericDisplayRow(name=f"{prefix} [{marker}] {item_name}", description=item.description))

            if item.section_break_after and visible_idx + 1 < len(self.filtered_indices):
                rows.append(GenericDisplayRow(name=SECTION_BREAK_ROW, is_disabled=True))

        selected_idx = None
        if self.state.selected_idx is not None and 0 <= self.state.selected_idx < len(visible_to_row):
            selected_idx = visible_to_row[self.state.selected_idx]
        scroll_top = visible_to_row[self.state.scroll_top] if self.state.scroll_top < len(visible_to_row) else 0
        return BuiltRows(rows=rows, state=ScrollState(selected_idx=selected_idx, scroll_top=scroll_top))

    def move_up(self) -> None:
        length = self.visible_len()
        self.state.move_up_wrap(length)
        self.state.ensure_visible(length, self.max_visible_rows(length))

    def move_down(self) -> None:
        length = self.visible_len()
        self.state.move_down_wrap(length)
        self.state.ensure_visible(length, self.max_visible_rows(length))

    def page_up(self) -> None:
        length = self.visible_len()
        self.state.page_up_clamped(length, self.max_visible_rows(length))

    def page_down(self) -> None:
        length = self.visible_len()
        self.state.page_down_clamped(length, self.max_visible_rows(length))

    def jump_top(self) -> None:
        length = self.visible_len()
        self.state.jump_top(length, self.max_visible_rows(length))

    def jump_bottom(self) -> None:
        length = self.visible_len()
        self.state.jump_bottom(length, self.max_visible_rows(length))

    def toggle_selected(self) -> None:
        actual_idx = self._selected_actual_idx()
        if actual_idx is None:
            return
        self.items[actual_idx].enabled = not self.items[actual_idx].enabled
        self.update_preview_line()
        if self.on_change is not None:
            self.on_change(self.items, self.app_event_tx)

    def confirm_selection(self) -> None:
        if self.complete:
            return
        self.complete = True
        if self.on_confirm is not None:
            self.on_confirm([item.id for item in self.items if item.enabled], self.app_event_tx)

    def move_selected_item(self, direction: Direction) -> None:
        if self.search_query:
            return
        actual_idx = self._selected_actual_idx()
        if actual_idx is None or not self.items:
            return
        if not self.items[actual_idx].orderable:
            return
        if direction is Direction.UP:
            new_idx = actual_idx - 1
        else:
            new_idx = actual_idx + 1
        if new_idx < 0 or new_idx >= len(self.items):
            return
        if not self.items[new_idx].orderable:
            return

        self.items[actual_idx], self.items[new_idx] = self.items[new_idx], self.items[actual_idx]
        self.update_preview_line()
        if self.on_change is not None:
            self.on_change(self.items, self.app_event_tx)
        self.apply_filter()
        if new_idx in self.filtered_indices:
            self.state.selected_idx = self.filtered_indices.index(new_idx)

    def update_preview_line(self) -> None:
        self.preview_line = self.preview_builder(self.items) if self.preview_builder is not None else None

    def close(self) -> None:
        if self.complete:
            return
        self.complete = True
        if self.on_cancel is not None:
            self.on_cancel(self.app_event_tx)

    def _selected_actual_idx(self) -> int | None:
        if self.state.selected_idx is None:
            return None
        if self.state.selected_idx < 0 or self.state.selected_idx >= len(self.filtered_indices):
            return None
        return self.filtered_indices[self.state.selected_idx]

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.close()
        return "Handled"

    def handle_key_event(self, event: Any) -> None:
        """Small semantic key handler for tests and simple callers.

        ``event`` may be a string such as ``"up"``, ``"down"``, ``"left"``,
        ``"right"``, ``"space"``, ``"enter"``, ``"esc"``, ``"backspace"``, or
        any single printable character.
        """

        if event == "left" and self.ordering_enabled:
            self.move_selected_item(Direction.UP)
        elif event == "right" and self.ordering_enabled:
            self.move_selected_item(Direction.DOWN)
        elif event == "up":
            self.move_up()
        elif event == "down":
            self.move_down()
        elif event == "page_up":
            self.page_up()
        elif event == "page_down":
            self.page_down()
        elif event == "home":
            self.jump_top()
        elif event == "end":
            self.jump_bottom()
        elif event == "backspace":
            self.search_query = self.search_query[:-1]
            self.apply_filter()
        elif event == "space":
            self.toggle_selected()
        elif event == "enter":
            self.confirm_selection()
        elif event == "esc":
            self.close()
        elif isinstance(event, str) and len(event) == 1:
            self.search_query += event
            self.apply_filter()


def is_complete(picker: MultiSelectPicker) -> bool:
    return picker.is_complete()


def on_ctrl_c(picker: MultiSelectPicker) -> str:
    return picker.on_ctrl_c()


def handle_key_event(picker: MultiSelectPicker, event: Any) -> None:
    picker.handle_key_event(event)


def desired_height(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "desired_height")


def render(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render")


@dataclass
class MultiSelectPickerBuilder:
    title: str
    subtitle: str | None
    app_event_tx: Any
    builder_items: list[MultiSelectItem] = field(default_factory=list)
    ordering_enabled: bool = False
    keymap: Any = None
    preview_builder: PreviewCallback | None = None
    on_change_callback: ChangeCallBack | None = None
    on_confirm_callback: ConfirmCallback | None = None
    on_cancel_callback: CancelCallback | None = None

    @classmethod
    def new(cls, title: str, subtitle: str | None, app_event_tx: Any) -> "MultiSelectPickerBuilder":
        return cls(title=title, subtitle=subtitle, app_event_tx=app_event_tx)

    def items(self, items: Iterable[MultiSelectItem]) -> "MultiSelectPickerBuilder":
        self.builder_items = list(items)
        return self

    def enable_ordering(self) -> "MultiSelectPickerBuilder":
        self.ordering_enabled = True
        return self

    def list_keymap(self, keymap: Any) -> "MultiSelectPickerBuilder":
        self.keymap = keymap
        return self

    def on_preview(self, callback: PreviewCallback) -> "MultiSelectPickerBuilder":
        self.preview_builder = callback
        return self

    def on_change(self, callback: ChangeCallBack) -> "MultiSelectPickerBuilder":
        self.on_change_callback = callback
        return self

    def on_confirm(self, callback: ConfirmCallback) -> "MultiSelectPickerBuilder":
        self.on_confirm_callback = callback
        return self

    def on_cancel(self, callback: CancelCallback) -> "MultiSelectPickerBuilder":
        self.on_cancel_callback = callback
        return self

    def build(self) -> MultiSelectPicker:
        picker = MultiSelectPicker(
            items=list(self.builder_items),
            state=ScrollState.new(),
            complete=False,
            app_event_tx=self.app_event_tx,
            title=self.title,
            subtitle=self.subtitle,
            footer_hint=self._footer_hint(),
            ordering_enabled=self.ordering_enabled,
            keymap=self.keymap,
            preview_builder=self.preview_builder,
            on_change=self.on_change_callback,
            on_confirm=self.on_confirm_callback,
            on_cancel=self.on_cancel_callback,
        )
        picker.apply_filter()
        picker.update_preview_line()
        return picker

    def _footer_hint(self) -> str:
        parts = ["Press Space to toggle"]
        if self.ordering_enabled:
            parts.append("Left/Right to move")
        parts.append("Enter to confirm and close")
        parts.append("Esc to close")
        return "; ".join(parts)


def match_item(filter: str, display_name: str, name: str) -> tuple[list[int] | None, int] | None:
    display = _subsequence_match_indices(display_name, filter)
    if display is not None:
        return display, _score(display)
    if display_name != name:
        canonical = _subsequence_match_indices(name, filter)
        if canonical is not None:
            return None, _score(canonical)
    return None


def truncate_text(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"[:max_len]
    return text[: max_len - 1] + "…"


def _subsequence_match_indices(candidate: str, query: str) -> list[int] | None:
    if not query:
        return []
    indices: list[int] = []
    start = 0
    lowered = candidate.lower()
    for char in query.lower():
        found = lowered.find(char, start)
        if found < 0:
            return None
        indices.append(found)
        start = found + 1
    return indices


def _score(indices: list[int]) -> int:
    if not indices:
        return 0
    return indices[-1] - indices[0] + len(indices)


def test_picker(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "test_picker")


def item(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "item")


_STUB_NAMES = [
    "non_orderable_items_cannot_move_or_be_crossed",
    "horizontal_list_keys_reorder_orderable_items",
    "section_break_after_item_renders_separator_row",
    "searchable_plain_j_updates_query_instead_of_navigating",
    "page_and_jump_navigation_use_list_keymap",
]

globals().update({name: (lambda *args, _name=name, **kwargs: not_ported(RUST_MODULE, _name)) for name in _STUB_NAMES})

__all__ = [
    "BuiltRows",
    "CancelCallback",
    "ChangeCallBack",
    "ConfirmCallback",
    "Direction",
    "ITEM_NAME_TRUNCATE_LEN",
    "MultiSelectItem",
    "MultiSelectPicker",
    "MultiSelectPickerBuilder",
    "PreviewCallback",
    "RUST_MODULE",
    "SEARCH_PLACEHOLDER",
    "SEARCH_PROMPT_PREFIX",
    "SECTION_BREAK_ROW",
    "default",
    "desired_height",
    "handle_key_event",
    "is_complete",
    "item",
    "match_item",
    "on_ctrl_c",
    "render",
    "test_picker",
    *_STUB_NAMES,
]
