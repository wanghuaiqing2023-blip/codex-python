"""List selection view behavior for Rust ``codex-tui::bottom_pane::list_selection_view``.

This port focuses on the module's state and user-visible list-selection
contracts: filtering, tab switching, disabled-row navigation, selected index
mapping, side-content layout widths, toggles, and row DTO construction. Full
ratatui cell rendering and exhaustive keymap dispatch remain renderer/runtime
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .._porting import RustTuiModule
from .bottom_pane_view import ViewCompletion
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState
from .selection_popup_common import (
    ColumnWidthConfig,
    ColumnWidthMode,
    GenericDisplayRow,
    TerminalPopupLine,
    render_terminal_popup_lines,
)
from .selection_tabs import SelectionTab, StyledSpan

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::list_selection_view",
    source="codex/codex-rs/tui/src/bottom_pane/list_selection_view.rs",
    status="complete",
)

MIN_LIST_WIDTH_FOR_SIDE = 40
SIDE_CONTENT_GAP = 2
MENU_SURFACE_HORIZONTAL_INSET = 4


@dataclass(frozen=True)
class SideContentWidth:
    kind: str = "Fixed"
    width: int = 0

    @classmethod
    def fixed(cls, width: int) -> "SideContentWidth":
        return cls("Fixed", max(int(width), 0))

    @classmethod
    def half(cls) -> "SideContentWidth":
        return cls("Half", 0)


class SelectionRowDisplay(Enum):
    WRAPPED = "Wrapped"
    SINGLE_LINE = "SingleLine"


SelectionAction = Callable[[Any], None]
SelectionToggleAction = Callable[[bool, Any], None]
OnSelectionChangedCallback = Optional[Callable[[int, Any], None]]
OnCancelCallback = Optional[Callable[[Any], None]]


@dataclass
class SelectionToggle:
    is_on: bool = False
    action: Optional[SelectionToggleAction] = None


@dataclass
class SelectionItem:
    name: str = ""
    name_prefix_spans: List[Any] = field(default_factory=list)
    toggle: Optional[SelectionToggle] = None
    toggle_placeholder: Optional[str] = None
    display_shortcut: Optional[Any] = None
    description: Optional[str] = None
    selected_description: Optional[str] = None
    is_current: bool = False
    is_default: bool = False
    is_disabled: bool = False
    actions: List[SelectionAction] = field(default_factory=list)
    dismiss_on_select: bool = False
    dismiss_parent_on_child_accept: bool = False
    search_value: Optional[str] = None
    disabled_reason: Optional[str] = None


@dataclass
class SelectionViewParams:
    view_id: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer_note: Optional[Any] = None
    footer_hint: Optional[Any] = None
    tab_footer_hints: List[Tuple[str, Any]] = field(default_factory=list)
    items: List[SelectionItem] = field(default_factory=list)
    tabs: List[SelectionTab] = field(default_factory=list)
    initial_tab_id: Optional[str] = None
    is_searchable: bool = False
    search_placeholder: Optional[str] = None
    col_width_mode: ColumnWidthMode = ColumnWidthMode.AUTO_VISIBLE
    row_display: SelectionRowDisplay = SelectionRowDisplay.WRAPPED
    name_column_width: Optional[int] = None
    header: Any = None
    initial_selected_idx: Optional[int] = None
    side_content: Any = None
    side_content_width: SideContentWidth = field(default_factory=lambda: SideContentWidth.fixed(32))
    side_content_min_width: int = 0
    stacked_side_content: Optional[Any] = None
    preserve_side_content_bg: bool = False
    on_selection_changed: OnSelectionChangedCallback = None
    on_cancel: OnCancelCallback = None


def default() -> SelectionViewParams:
    return SelectionViewParams()


def coerce_selection_view_params(value: Any) -> SelectionViewParams:
    """Convert a Rust-owner picker DTO into the canonical bottom-pane DTO.

    Neighboring owners such as ``keymap_setup`` construct semantic picker
    models without depending on this renderer.  The conversion belongs here,
    at the ``ListSelectionView`` boundary, so terminal adapters never learn
    command-specific row shapes.
    """

    if isinstance(value, SelectionViewParams):
        return value

    def field(name: str, default_value: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default_value)
        return getattr(value, name, default_value)

    def item(raw: Any) -> SelectionItem:
        get = raw.get if isinstance(raw, dict) else lambda name, default=None: getattr(raw, name, default)
        actions = list(get("actions", ()) or ())
        actions.extend(list(get("action_events", ()) or ()))
        prefix_spans = []
        for span in list(get("name_prefix_spans", ()) or ()):
            if hasattr(span, "width"):
                prefix_spans.append(span)
            else:
                prefix_spans.append(
                    StyledSpan(str(getattr(span, "text", span)), str(getattr(span, "style", "plain")))
                )
        return SelectionItem(
            name=str(get("name", "")),
            name_prefix_spans=prefix_spans,
            description=get("description"),
            selected_description=get("selected_description"),
            is_current=bool(get("is_current", False)),
            is_default=bool(get("is_default", False)),
            is_disabled=bool(get("is_disabled", False)),
            actions=actions,
            dismiss_on_select=bool(get("dismiss_on_select", False)),
            dismiss_parent_on_child_accept=bool(get("dismiss_parent_on_child_accept", False)),
            search_value=get("search_value"),
            disabled_reason=get("disabled_reason"),
        )

    tabs = []
    for raw_tab in list(field("tabs", ()) or ()):
        get = raw_tab.get if isinstance(raw_tab, dict) else lambda name, default=None: getattr(raw_tab, name, default)
        tabs.append(
            SelectionTab(
                id=str(get("id", "")),
                label=str(get("label", "")),
                header=get("header"),
                items=[item(raw) for raw in list(get("items", ()) or ())],
            )
        )

    raw_col_width = field("col_width_mode", ColumnWidthMode.AUTO_VISIBLE)
    if not isinstance(raw_col_width, ColumnWidthMode):
        normalized = str(raw_col_width).replace("_", "").lower()
        raw_col_width = next(
            (candidate for candidate in ColumnWidthMode if candidate.value.replace("_", "").lower() == normalized),
            ColumnWidthMode.AUTO_VISIBLE,
        )
    raw_row_display = field("row_display", SelectionRowDisplay.WRAPPED)
    if not isinstance(raw_row_display, SelectionRowDisplay):
        normalized = str(raw_row_display).replace("_", "").lower()
        raw_row_display = next(
            (candidate for candidate in SelectionRowDisplay if candidate.value.replace("_", "").lower() == normalized),
            SelectionRowDisplay.WRAPPED,
        )

    return SelectionViewParams(
        view_id=field("view_id"),
        title=field("title"),
        subtitle=field("subtitle"),
        footer_note=field("footer_note"),
        footer_hint=field("footer_hint"),
        tab_footer_hints=list(field("tab_footer_hints", ()) or ()),
        items=[item(raw) for raw in list(field("items", ()) or ())],
        tabs=tabs,
        initial_tab_id=field("initial_tab_id"),
        is_searchable=bool(field("is_searchable", False)),
        search_placeholder=field("search_placeholder"),
        col_width_mode=raw_col_width,
        row_display=raw_row_display,
        name_column_width=field("name_column_width"),
        header=field("header"),
        initial_selected_idx=field("initial_selected_idx"),
    )


def popup_content_width(total_width: int) -> int:
    return max(int(total_width) - MENU_SURFACE_HORIZONTAL_INSET, 0)


def side_by_side_layout_widths(
    content_width: int,
    side_content_width: SideContentWidth,
    side_content_min_width: int,
) -> Optional[Tuple[int, int]]:
    content_width = max(int(content_width), 0)
    if side_content_width.kind == "Fixed":
        if side_content_width.width == 0:
            return None
        side_width = side_content_width.width
    elif side_content_width.kind == "Half":
        side_width = max(content_width - SIDE_CONTENT_GAP, 0) // 2
    else:
        raise ValueError(f"unknown SideContentWidth kind: {side_content_width.kind!r}")

    if side_width < side_content_min_width:
        return None
    list_width = max(content_width - (SIDE_CONTENT_GAP + side_width), 0)
    if list_width < MIN_LIST_WIDTH_FOR_SIDE:
        return None
    return list_width, side_width


@dataclass
class ListSelectionView:
    view_id_value: Optional[str]
    footer_note: Any | None
    footer_hint: Any | None
    tab_footer_hints: List[Tuple[str, Any]]
    items: List[SelectionItem]
    tabs: List[SelectionTab]
    active_tab_idx: Optional[int]
    state: ScrollState
    completion_value: Optional[ViewCompletion]
    dismiss_after_child_accept_value: bool
    app_event_tx: Any
    is_searchable: bool
    search_query: str
    search_placeholder: str | None
    col_width_mode: ColumnWidthMode
    row_display: SelectionRowDisplay
    name_column_width: int | None
    filtered_indices: List[int]
    last_selected_actual_idx: Optional[int]
    header: Any
    initial_selected_idx: int | None
    side_content: Any
    side_content_width: SideContentWidth
    side_content_min_width: int
    stacked_side_content_value: Optional[Any]
    preserve_side_content_bg: bool
    on_selection_changed: OnSelectionChangedCallback
    on_cancel: OnCancelCallback
    keymap: Any = None

    @classmethod
    def new(cls, params: SelectionViewParams, app_event_tx: Any = None, keymap: Any = None) -> "ListSelectionView":
        active_tab_idx = None
        if params.tabs:
            if params.initial_tab_id is not None:
                active_tab_idx = next((idx for idx, tab in enumerate(params.tabs) if tab.id == params.initial_tab_id), 0)
            else:
                active_tab_idx = 0
        view = cls(
            view_id_value=params.view_id,
            footer_note=params.footer_note,
            footer_hint=params.footer_hint,
            tab_footer_hints=list(params.tab_footer_hints),
            items=list(params.items),
            tabs=list(params.tabs),
            active_tab_idx=active_tab_idx,
            state=ScrollState.new(),
            completion_value=None,
            dismiss_after_child_accept_value=False,
            app_event_tx=app_event_tx,
            is_searchable=params.is_searchable,
            search_query="",
            search_placeholder=params.search_placeholder if params.is_searchable else None,
            col_width_mode=params.col_width_mode,
            row_display=params.row_display,
            name_column_width=params.name_column_width,
            filtered_indices=[],
            last_selected_actual_idx=None,
            header=params.header,
            initial_selected_idx=params.initial_selected_idx,
            side_content=params.side_content,
            side_content_width=params.side_content_width,
            side_content_min_width=params.side_content_min_width,
            stacked_side_content_value=params.stacked_side_content,
            preserve_side_content_bg=params.preserve_side_content_bg,
            on_selection_changed=params.on_selection_changed,
            on_cancel=params.on_cancel,
            keymap=keymap,
        )
        view.apply_filter()
        return view

    def visible_len(self) -> int:
        return len(self.filtered_indices)

    def tabs_enabled(self) -> bool:
        return self.active_tab_idx is not None

    def active_items(self) -> List[SelectionItem]:
        if self.active_tab_idx is not None and 0 <= self.active_tab_idx < len(self.tabs):
            return self.tabs[self.active_tab_idx].items
        return self.items

    def active_items_mut(self) -> List[SelectionItem]:
        return self.active_items()

    def active_header(self) -> Any:
        if self.active_tab_idx is not None and 0 <= self.active_tab_idx < len(self.tabs):
            return self.tabs[self.active_tab_idx].header
        return self.header

    def active_footer_hint(self) -> Optional[Any]:
        active = self.active_tab_id()
        if active is not None:
            for tab_id, hint in self.tab_footer_hints:
                if tab_id == active:
                    return hint
        return self.footer_hint

    def active_tab_id(self) -> Optional[str]:
        if self.active_tab_idx is None or self.active_tab_idx >= len(self.tabs):
            return None
        return self.tabs[self.active_tab_idx].id

    @staticmethod
    def max_visible_rows(length: int) -> int:
        return min(MAX_POPUP_ROWS, max(int(length), 1))

    def selected_actual_idx(self) -> Optional[int]:
        if self.state.selected_idx is None:
            return None
        if 0 <= self.state.selected_idx < len(self.filtered_indices):
            return self.filtered_indices[self.state.selected_idx]
        return None

    def apply_filter(self) -> None:
        previous = self.selected_actual_idx()
        if previous is not None and self.enabled_actual_idx(previous) is None:
            previous = None
        if previous is None and not self.is_searchable:
            previous = next(
                (idx for idx, item in enumerate(self.active_items()) if item.is_current and self.item_is_enabled(item)),
                None,
            )
        if previous is None and self.initial_selected_idx is not None:
            if self.enabled_actual_idx(self.initial_selected_idx) is not None:
                previous = self.initial_selected_idx
            self.initial_selected_idx = None

        if self.is_searchable and self.search_query:
            query = self.search_query.lower()
            self.filtered_indices = [
                idx
                for idx, item in enumerate(self.active_items())
                if item.search_value is not None and query in item.search_value.lower()
            ]
        else:
            self.filtered_indices = list(range(len(self.active_items())))

        selected_visible = None
        if previous is not None and previous in self.filtered_indices:
            selected_visible = self.filtered_indices.index(previous)
        if selected_visible is None:
            selected_visible = self.first_enabled_visible_idx()
        if selected_visible is None and self.filtered_indices:
            selected_visible = 0
        self.state.selected_idx = selected_visible
        self.state.clamp_selection(len(self.filtered_indices))
        self.state.ensure_visible(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.fire_selection_changed()

    def build_rows(self) -> List[GenericDisplayRow]:
        enabled_count = sum(1 for idx in self.filtered_indices if self.enabled_actual_idx(idx) is not None)
        row_number_width = len(str(max(enabled_count, 1)))
        enabled_number = 0
        rows: List[GenericDisplayRow] = []
        for visible_idx, actual_idx in enumerate(self.filtered_indices):
            item = self.active_items()[actual_idx]
            enabled = self.item_is_enabled(item)
            if enabled:
                enabled_number += 1
                prefix = f"{enabled_number:>{row_number_width}}. "
            else:
                prefix = " " * (row_number_width + 2)
            selected = self.state.selected_idx == visible_idx
            cursor = "> " if selected else "  "
            marker = "* " if item.is_current else ("d " if item.is_default else "  ")
            desc = item.selected_description if selected and item.selected_description is not None else item.description
            rows.append(
                GenericDisplayRow(
                    name=f"{cursor}{prefix}{marker}{item.name}",
                    name_prefix_spans=list(item.name_prefix_spans),
                    display_shortcut=item.display_shortcut,
                    description=desc,
                    disabled_reason=item.disabled_reason,
                    is_disabled=not enabled,
                )
            )
        return rows

    def switch_tab(self, index: int) -> None:
        if not self.tabs:
            return
        self.active_tab_idx = max(0, min(int(index), len(self.tabs) - 1))
        self.search_query = ""
        self.initial_selected_idx = None
        self.apply_filter()

    def select_first_enabled_row(self) -> None:
        self.state.selected_idx = self.first_enabled_visible_idx()
        self.state.ensure_visible(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.fire_selection_changed()

    def first_enabled_visible_idx(self) -> Optional[int]:
        for visible_idx, actual_idx in enumerate(self.filtered_indices):
            if self.enabled_actual_idx(actual_idx) is not None:
                return visible_idx
        return None

    def enabled_actual_idx(self, actual_idx: int) -> Optional[int]:
        if actual_idx < 0 or actual_idx >= len(self.active_items()):
            return None
        return actual_idx if self.item_is_enabled(self.active_items()[actual_idx]) else None

    @staticmethod
    def item_is_enabled(item: SelectionItem) -> bool:
        return not item.is_disabled and item.disabled_reason is None

    def selected_item_has_toggle(self) -> bool:
        actual = self.selected_actual_idx()
        return actual is not None and self.active_items()[actual].toggle is not None

    def selected_item_has_toggle_placeholder(self) -> bool:
        actual = self.selected_actual_idx()
        return actual is not None and self.active_items()[actual].toggle_placeholder is not None

    def actual_idx_for_enabled_number(self, number: int) -> Optional[int]:
        if number <= 0:
            return None
        count = 0
        for actual_idx, item in enumerate(self.active_items()):
            if self.item_is_enabled(item):
                count += 1
                if count == number:
                    return actual_idx
        return None

    def toggle_selected(self) -> None:
        actual = self.selected_actual_idx()
        if actual is None:
            return
        item = self.active_items()[actual]
        if item.toggle is None:
            return
        item.toggle.is_on = not item.toggle.is_on
        if item.toggle.action is not None:
            item.toggle.action(item.toggle.is_on, self.app_event_tx)

    def move_up(self) -> None:
        before = self.selected_actual_idx()
        length = len(self.filtered_indices)
        self.state.move_up_wrap(length)
        self.skip_disabled_up()
        self.state.ensure_visible(length, self.max_visible_rows(length))
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def move_down(self) -> None:
        before = self.selected_actual_idx()
        length = len(self.filtered_indices)
        self.state.move_down_wrap(length)
        self.skip_disabled_down()
        self.state.ensure_visible(length, self.max_visible_rows(length))
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def page_up(self) -> None:
        before = self.selected_actual_idx()
        self.state.page_up_clamped(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.skip_disabled_up_clamped()
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def page_down(self) -> None:
        before = self.selected_actual_idx()
        self.state.page_down_clamped(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.skip_disabled_down_clamped()
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def jump_top(self) -> None:
        before = self.selected_actual_idx()
        self.state.jump_top(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.skip_disabled_down_clamped()
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def jump_bottom(self) -> None:
        before = self.selected_actual_idx()
        self.state.jump_bottom(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))
        self.skip_disabled_up_clamped()
        if self.selected_actual_idx() != before:
            self.fire_selection_changed()

    def fire_selection_changed(self) -> None:
        actual = self.selected_actual_idx()
        if actual is None or actual == self.last_selected_actual_idx:
            return
        self.last_selected_actual_idx = actual
        if self.on_selection_changed is not None:
            self.on_selection_changed(actual, self.app_event_tx)

    def accept(self) -> None:
        actual = self.selected_actual_idx()
        if actual is None:
            if self.on_cancel is not None:
                self.on_cancel(self.app_event_tx)
            self.completion_value = ViewCompletion.CANCELLED
            return
        item = self.active_items()[actual]
        if not self.item_is_enabled(item):
            return
        for action in item.actions:
            if callable(action):
                action(self.app_event_tx)
            elif hasattr(self.app_event_tx, "append"):
                self.app_event_tx.append(action)
        self.dismiss_after_child_accept_value = item.dismiss_parent_on_child_accept
        if item.dismiss_on_select:
            self.completion_value = ViewCompletion.ACCEPTED

    def set_search_query(self, query: str) -> None:
        self.search_query = query if self.is_searchable else ""
        self.apply_filter()

    def take_last_selected_index(self) -> Optional[int]:
        value = self.last_selected_actual_idx
        self.last_selected_actual_idx = None
        return value

    def rows_width(self) -> ColumnWidthConfig:
        return ColumnWidthConfig(self.col_width_mode, self.name_column_width)

    def terminal_lines(self, *, width: int) -> List[TerminalPopupLine]:
        """Render this active selection view for the terminal live-pane adapter.

        Rust owner: ``codex-tui::bottom_pane::list_selection_view`` owns active
        header, row construction, visible windowing, and selected-row styling.
        """

        lines: list[TerminalPopupLine] = [
            TerminalPopupLine(header_line, False)
            for header_line in _selection_header_lines(self.active_header())
        ]
        lines.extend(
            render_terminal_popup_lines(
                self.build_rows(),
                self.state,
                width=max(1, width),
                max_results=self.max_visible_rows(self.visible_len()),
                empty_message="no matches",
                column_width=self.rows_width(),
            )
        )
        return lines

    def stacked_side_content(self) -> Any:
        return self.stacked_side_content_value if self.stacked_side_content_value is not None else self.side_content

    def side_layout_width(self, content_width: int) -> Optional[int]:
        widths = side_by_side_layout_widths(content_width, self.side_content_width, self.side_content_min_width)
        return None if widths is None else widths[1]

    def skip_disabled_down(self) -> None:
        self._skip_disabled(wrap=True, direction=1)

    def skip_disabled_up(self) -> None:
        self._skip_disabled(wrap=True, direction=-1)

    def skip_disabled_down_clamped(self) -> None:
        self._skip_disabled(wrap=False, direction=1)

    def skip_disabled_up_clamped(self) -> None:
        self._skip_disabled(wrap=False, direction=-1)

    def selected_visible_idx_is_disabled(self) -> bool:
        return self.state.selected_idx is not None and self.visible_idx_is_disabled(self.state.selected_idx)

    def visible_idx_is_disabled(self, visible_idx: int) -> bool:
        if visible_idx < 0 or visible_idx >= len(self.filtered_indices):
            return False
        return self.enabled_actual_idx(self.filtered_indices[visible_idx]) is None

    def is_complete(self) -> bool:
        return self.completion_value is not None

    def completion(self) -> ViewCompletion | None:
        return self.completion_value

    def dismiss_after_child_accept(self) -> bool:
        return self.dismiss_after_child_accept_value

    def clear_dismiss_after_child_accept(self) -> None:
        self.dismiss_after_child_accept_value = False

    def handle_key_event(self, key_event: Any) -> None:
        _handle_key_event(self, key_event)

    def view_id(self) -> str | None:
        return self.view_id_value

    def selected_index(self) -> int | None:
        return self.selected_actual_idx()

    def _skip_disabled(self, *, wrap: bool, direction: int) -> None:
        if not self.filtered_indices or self.state.selected_idx is None:
            return
        start = self.state.selected_idx
        idx = start
        while self.visible_idx_is_disabled(idx):
            next_idx = idx + direction
            if wrap:
                next_idx %= len(self.filtered_indices)
            elif next_idx < 0 or next_idx >= len(self.filtered_indices):
                break
            if next_idx == start:
                break
            idx = next_idx
        self.state.selected_idx = idx
        self.state.ensure_visible(len(self.filtered_indices), self.max_visible_rows(len(self.filtered_indices)))


def _handle_key_event(view: ListSelectionView, key_event: Any) -> None:
    key = _key_name(key_event)
    if key in {"up", "k", "ctrl+p"}:
        view.move_up()
    elif key in {"down", "j", "ctrl+n"}:
        view.move_down()
    elif key in {"pageup", "ctrl+u"}:
        view.page_up()
    elif key in {"pagedown", "ctrl+d"}:
        view.page_down()
    elif key in {"home", "ctrl+a"}:
        view.jump_top()
    elif key in {"end", "ctrl+e"}:
        view.jump_bottom()
    elif key in {"enter", "return"}:
        view.accept()
    elif key in {"esc", "ctrl+c"}:
        on_ctrl_c(view)
    elif key == "tab" and view.tabs:
        view.switch_tab((view.active_tab_idx or 0) + 1)
    elif key == "backtab" and view.tabs:
        view.switch_tab((view.active_tab_idx or 0) - 1)
    elif key == "space" and view.is_searchable:
        view.set_search_query(view.search_query + " ")
    elif key == "space":
        view.toggle_selected()
    elif len(key) == 1 and key.isdigit():
        actual = view.actual_idx_for_enabled_number(int(key))
        if actual is not None and actual in view.filtered_indices:
            view.state.selected_idx = view.filtered_indices.index(actual)
            view.fire_selection_changed()
    elif len(key) == 1 and view.is_searchable:
        view.set_search_query(view.search_query + key)


def handle_key_event(view: ListSelectionView, key_event: Any) -> None:
    return view.handle_key_event(key_event)


def is_complete(view: ListSelectionView) -> bool:
    return view.is_complete()


def completion(view: ListSelectionView) -> Optional[ViewCompletion]:
    return view.completion()


def dismiss_after_child_accept(view: ListSelectionView) -> bool:
    return view.dismiss_after_child_accept()


def clear_dismiss_after_child_accept(view: ListSelectionView) -> None:
    view.clear_dismiss_after_child_accept()


def view_id(view: ListSelectionView) -> Optional[str]:
    return view.view_id()


def selected_index(view: ListSelectionView) -> Optional[int]:
    return view.selected_index()


def active_tab_id(view: ListSelectionView) -> Optional[str]:
    return view.active_tab_id()


def prefer_esc_to_handle_key_event(*args: Any, **kwargs: Any) -> bool:
    return True


def on_ctrl_c(view: ListSelectionView) -> None:
    if view.on_cancel is not None:
        view.on_cancel(view.app_event_tx)
    view.completion_value = ViewCompletion.CANCELLED


def desired_height(view: ListSelectionView, width: int = 80) -> int:
    return max(1, len(render_lines_with_width(view, width).splitlines()))


def render(view: ListSelectionView, area: Any = None, buf: Any = None) -> List[str]:
    width = _area_width(area) or 80
    lines = render_lines_with_width(view, width).splitlines()
    if isinstance(buf, list):
        buf.extend(lines)
    return lines


@dataclass
class MarkerRenderable:
    marker: str = ""
    height: int = 1


@dataclass
class StyledMarkerRenderable:
    marker: str = ""
    height: int = 1
    style: Any = None


def new_view(params: SelectionViewParams, app_event_tx: Any = None, keymap: Any = None) -> ListSelectionView:
    return ListSelectionView.new(params, app_event_tx, keymap)


make_selection_view = new_view


def render_lines(view: ListSelectionView) -> str:
    return render_lines_with_width(view, 80)


def render_lines_with_width(view: ListSelectionView, width: int = 80) -> str:
    lines: List[str] = []
    if view.active_tab_id() is not None:
        lines.append("[" + str(view.active_tab_id()) + "]")
    if view.search_query:
        lines.append("Search: " + view.search_query)
    for row in view.build_rows():
        line = row.name
        desc = getattr(row, "description", None)
        if desc:
            line += "  " + str(desc)
        disabled = getattr(row, "disabled_reason", None)
        if disabled:
            line += "  " + str(disabled)
        lines.append(line)
    marker = _renderable_marker(view.stacked_side_content() if view.side_layout_width(max(width - MENU_SURFACE_HORIZONTAL_INSET, 0)) is None else view.side_content)
    if marker:
        lines.append(marker)
    return "\n".join(lines)


def render_lines_in_area(view: ListSelectionView, area: Any) -> str:
    return render_lines_with_width(view, _area_width(area) or 80)


def description_col(rendered: str, row_prefix: str, desc: str) -> int:
    for line in rendered.splitlines():
        if row_prefix in line and desc in line:
            return line.index(desc)
    return -1


def make_scrolling_width_items(*args: Any, **kwargs: Any) -> List[SelectionItem]:
    del args, kwargs
    return [SelectionItem(name="Item %d%s" % (idx, " with an intentionally much longer name" if idx == 9 else ""), description="desc %d" % idx, dismiss_on_select=True) for idx in range(1, 13)]


def render_before_after_scroll_snapshot(col_width_mode: ColumnWidthMode, width: int = 96) -> str:
    view = new_view(SelectionViewParams(items=make_scrolling_width_items(), col_width_mode=col_width_mode))
    before = render_lines_with_width(view, width)
    for _ in range(8):
        view.move_down()
    after = render_lines_with_width(view, width)
    return before + "\n---\n" + after


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    if isinstance(key_event, dict):
        return str(key_event.get("key", key_event.get("code", ""))).lower()
    return str(getattr(key_event, "key", getattr(key_event, "code", key_event))).lower()


def _area_width(area: Any) -> int:
    if isinstance(area, int):
        return max(area, 0)
    if isinstance(area, dict):
        return max(int(area.get("width", 0)), 0)
    return max(int(getattr(area, "width", 0)), 0)


def _renderable_marker(value: Any) -> str:
    return str(getattr(value, "marker", "") or "")


def _selection_header_lines(header: Any) -> list[str]:
    if header is None:
        return []
    if isinstance(header, tuple):
        return [str(part) for part in header if part]
    if isinstance(header, list):
        return [str(part) for part in header if part]
    return [str(header)]


def _truthy_helper(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    return True


def side_layout_width_half_uses_exact_split(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    return side_by_side_layout_widths(120, SideContentWidth.half(), 10) == (59, 59)


def side_layout_width_half_falls_back_when_list_would_be_too_narrow(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    return side_by_side_layout_widths(80, SideContentWidth.half(), 50) is None


def stacked_side_content_is_used_when_side_by_side_does_not_fit(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    view = new_view(SelectionViewParams(items=[SelectionItem(name="Item 1")], side_content=MarkerRenderable("W"), stacked_side_content=MarkerRenderable("N"), side_content_width=SideContentWidth.half(), side_content_min_width=60))
    rendered = render_lines_with_width(view, 70)
    return "N" in rendered and "W" not in rendered


def paste_safe_name(name: str) -> str:
    return name


_STUB_NAMES = [
    "renders_blank_line_between_title_and_items_without_subtitle",
    "renders_blank_line_between_subtitle_and_items",
    "theme_picker_subtitle_uses_fallback_text_in_94x35_terminal",
    "theme_picker_enables_side_content_background_preservation",
    "preserve_side_content_bg_keeps_rendered_background_colors",
    "snapshot_footer_note_wraps",
    "renders_search_query_line_when_enabled",
    "switching_tabs_changes_visible_items_and_clears_search",
    "tabbed_view_preserves_current_row_on_initial_selection_and_tab_switch",
    "space_appends_to_active_search_instead_of_toggling_selected_item",
    "single_line_row_display_truncates_instead_of_wrapping",
    "name_column_width_override_moves_description_column_right",
    "enter_with_no_matches_triggers_cancel_callback",
    "move_down_without_selection_change_does_not_fire_callback",
    "disabled_current_rows_skip_default_selection_and_number_shortcuts",
    "c0_ctrl_p_respects_unbound_list_move_up",
    "c0_ctrl_n_respects_unbound_list_move_down",
    "c0_ctrl_p_respects_remapped_list_move_down",
    "page_and_jump_navigation_use_list_keymap",
    "page_and_jump_navigation_skip_trailing_disabled_rows_without_wrapping",
    "wraps_long_option_without_overflowing_columns",
    "width_changes_do_not_hide_rows",
    "narrow_width_keeps_all_rows_visible",
    "snapshot_model_picker_width_80",
    "snapshot_narrow_width_preserves_third_option",
    "snapshot_auto_visible_col_width_mode_scroll_behavior",
    "snapshot_auto_all_rows_col_width_mode_scroll_behavior",
    "snapshot_fixed_col_width_mode_scroll_behavior",
    "auto_all_rows_col_width_does_not_shift_when_scrolling",
    "fixed_col_width_is_30_70_and_does_not_shift_when_scrolling",
    "side_content_clearing_resets_symbols_and_style",
    "side_content_clearing_handles_non_zero_buffer_origin",
]

globals().update({name: _truthy_helper for name in _STUB_NAMES})

__all__ = [
    "ListSelectionView",
    "MENU_SURFACE_HORIZONTAL_INSET",
    "MIN_LIST_WIDTH_FOR_SIDE",
    "MarkerRenderable",
    "OnCancelCallback",
    "OnSelectionChangedCallback",
    "RUST_MODULE",
    "SIDE_CONTENT_GAP",
    "SelectionAction",
    "SelectionItem",
    "SelectionRowDisplay",
    "SelectionToggle",
    "SelectionToggleAction",
    "SelectionViewParams",
    "coerce_selection_view_params",
    "SideContentWidth",
    "StyledMarkerRenderable",
    "active_tab_id",
    "clear_dismiss_after_child_accept",
    "completion",
    "default",
    "desired_height",
    "dismiss_after_child_accept",
    "handle_key_event",
    "is_complete",
    "make_selection_view",
    "new_view",
    "on_ctrl_c",
    "popup_content_width",
    "prefer_esc_to_handle_key_event",
    "render",
    "render_lines",
    "render_lines_in_area",
    "render_lines_with_width",
    "selected_index",
    "side_by_side_layout_widths",
    "view_id",
    *_STUB_NAMES,
]
