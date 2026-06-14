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
from typing import Any, Callable

from .._porting import RustTuiModule, not_ported
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState
from .selection_popup_common import ColumnWidthConfig, ColumnWidthMode, GenericDisplayRow
from .selection_tabs import SelectionTab

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::list_selection_view",
    source="codex/codex-rs/tui/src/bottom_pane/list_selection_view.rs",
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
OnSelectionChangedCallback = Callable[[int, Any], None] | None
OnCancelCallback = Callable[[Any], None] | None


@dataclass
class SelectionToggle:
    is_on: bool = False
    action: SelectionToggleAction | None = None


@dataclass
class SelectionItem:
    name: str = ""
    name_prefix_spans: list[Any] = field(default_factory=list)
    toggle: SelectionToggle | None = None
    toggle_placeholder: str | None = None
    display_shortcut: Any | None = None
    description: str | None = None
    selected_description: str | None = None
    is_current: bool = False
    is_default: bool = False
    is_disabled: bool = False
    actions: list[SelectionAction] = field(default_factory=list)
    dismiss_on_select: bool = False
    dismiss_parent_on_child_accept: bool = False
    search_value: str | None = None
    disabled_reason: str | None = None


@dataclass
class SelectionViewParams:
    view_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    footer_note: Any | None = None
    footer_hint: Any | None = None
    tab_footer_hints: list[tuple[str, Any]] = field(default_factory=list)
    items: list[SelectionItem] = field(default_factory=list)
    tabs: list[SelectionTab] = field(default_factory=list)
    initial_tab_id: str | None = None
    is_searchable: bool = False
    search_placeholder: str | None = None
    col_width_mode: ColumnWidthMode = ColumnWidthMode.AUTO_VISIBLE
    row_display: SelectionRowDisplay = SelectionRowDisplay.WRAPPED
    name_column_width: int | None = None
    header: Any = None
    initial_selected_idx: int | None = None
    side_content: Any = None
    side_content_width: SideContentWidth = field(default_factory=SideContentWidth.fixed)
    side_content_min_width: int = 0
    stacked_side_content: Any | None = None
    preserve_side_content_bg: bool = False
    on_selection_changed: OnSelectionChangedCallback = None
    on_cancel: OnCancelCallback = None


def default() -> SelectionViewParams:
    return SelectionViewParams()


def popup_content_width(total_width: int) -> int:
    return max(int(total_width) - MENU_SURFACE_HORIZONTAL_INSET, 0)


def side_by_side_layout_widths(
    content_width: int,
    side_content_width: SideContentWidth,
    side_content_min_width: int,
) -> tuple[int, int] | None:
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
    view_id_value: str | None
    footer_note: Any | None
    footer_hint: Any | None
    tab_footer_hints: list[tuple[str, Any]]
    items: list[SelectionItem]
    tabs: list[SelectionTab]
    active_tab_idx: int | None
    state: ScrollState
    completion_value: str | None
    dismiss_after_child_accept_value: bool
    app_event_tx: Any
    is_searchable: bool
    search_query: str
    search_placeholder: str | None
    col_width_mode: ColumnWidthMode
    row_display: SelectionRowDisplay
    name_column_width: int | None
    filtered_indices: list[int]
    last_selected_actual_idx: int | None
    header: Any
    initial_selected_idx: int | None
    side_content: Any
    side_content_width: SideContentWidth
    side_content_min_width: int
    stacked_side_content_value: Any | None
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

    def active_items(self) -> list[SelectionItem]:
        if self.active_tab_idx is not None and 0 <= self.active_tab_idx < len(self.tabs):
            return self.tabs[self.active_tab_idx].items
        return self.items

    def active_items_mut(self) -> list[SelectionItem]:
        return self.active_items()

    def active_header(self) -> Any:
        if self.active_tab_idx is not None and 0 <= self.active_tab_idx < len(self.tabs):
            return self.tabs[self.active_tab_idx].header
        return self.header

    def active_footer_hint(self) -> Any | None:
        active = self.active_tab_id()
        if active is not None:
            for tab_id, hint in self.tab_footer_hints:
                if tab_id == active:
                    return hint
        return self.footer_hint

    def active_tab_id(self) -> str | None:
        if self.active_tab_idx is None or self.active_tab_idx >= len(self.tabs):
            return None
        return self.tabs[self.active_tab_idx].id

    @staticmethod
    def max_visible_rows(length: int) -> int:
        return min(MAX_POPUP_ROWS, max(int(length), 1))

    def selected_actual_idx(self) -> int | None:
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

    def build_rows(self) -> list[GenericDisplayRow]:
        enabled_count = sum(1 for idx in self.filtered_indices if self.enabled_actual_idx(idx) is not None)
        row_number_width = len(str(max(enabled_count, 1)))
        enabled_number = 0
        rows: list[GenericDisplayRow] = []
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

    def first_enabled_visible_idx(self) -> int | None:
        for visible_idx, actual_idx in enumerate(self.filtered_indices):
            if self.enabled_actual_idx(actual_idx) is not None:
                return visible_idx
        return None

    def enabled_actual_idx(self, actual_idx: int) -> int | None:
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

    def actual_idx_for_enabled_number(self, number: int) -> int | None:
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
            self.completion_value = "Cancelled"
            return
        item = self.active_items()[actual]
        if not self.item_is_enabled(item):
            return
        for action in item.actions:
            action(self.app_event_tx)
        self.dismiss_after_child_accept_value = item.dismiss_parent_on_child_accept
        if item.dismiss_on_select:
            self.completion_value = "Submitted"

    def set_search_query(self, query: str) -> None:
        self.search_query = query if self.is_searchable else ""
        self.apply_filter()

    def take_last_selected_index(self) -> int | None:
        value = self.last_selected_actual_idx
        self.last_selected_actual_idx = None
        return value

    def rows_width(self) -> ColumnWidthConfig:
        return ColumnWidthConfig(self.col_width_mode, self.name_column_width)

    def stacked_side_content(self) -> Any:
        return self.stacked_side_content_value if self.stacked_side_content_value is not None else self.side_content

    def side_layout_width(self, content_width: int) -> int | None:
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

    def completion(self) -> str | None:
        return self.completion_value

    def dismiss_after_child_accept(self) -> bool:
        return self.dismiss_after_child_accept_value

    def clear_dismiss_after_child_accept(self) -> None:
        self.dismiss_after_child_accept_value = False

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


def handle_key_event(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "handle_key_event")


def is_complete(view: ListSelectionView) -> bool:
    return view.is_complete()


def completion(view: ListSelectionView) -> str | None:
    return view.completion()


def dismiss_after_child_accept(view: ListSelectionView) -> bool:
    return view.dismiss_after_child_accept()


def clear_dismiss_after_child_accept(view: ListSelectionView) -> None:
    view.clear_dismiss_after_child_accept()


def view_id(view: ListSelectionView) -> str | None:
    return view.view_id()


def selected_index(view: ListSelectionView) -> int | None:
    return view.selected_index()


def active_tab_id(view: ListSelectionView) -> str | None:
    return view.active_tab_id()


def prefer_esc_to_handle_key_event(*args: Any, **kwargs: Any) -> bool:
    return True


def on_ctrl_c(view: ListSelectionView) -> None:
    if view.on_cancel is not None:
        view.on_cancel(view.app_event_tx)
    view.completion_value = "Cancelled"


def desired_height(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "desired_height")


def render(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render")


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


def render_lines(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_lines")


def render_lines_with_width(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_lines_with_width")


def render_lines_in_area(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_lines_in_area")


def description_col(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "description_col")


def make_scrolling_width_items(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "make_scrolling_width_items")


def render_before_after_scroll_snapshot(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_before_after_scroll_snapshot")


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
    "side_layout_width_half_uses_exact_split",
    "side_layout_width_half_falls_back_when_list_would_be_too_narrow",
    "stacked_side_content_is_used_when_side_by_side_does_not_fit",
    "side_content_clearing_resets_symbols_and_style",
    "side_content_clearing_handles_non_zero_buffer_origin",
]

globals().update({name: (lambda *args, _name=name, **kwargs: not_ported(RUST_MODULE, _name)) for name in _STUB_NAMES})

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
