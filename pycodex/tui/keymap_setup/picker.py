"""Semantic Python port of Rust ``codex-tui::keymap_setup::picker``.

Rust builds ratatui ``SelectionViewParams`` for the ``/keymap`` shortcut
picker.  Python keeps the same construction semantics as plain dataclasses:
tabs, rows, headers, search text, selected row, and action payloads are all
observable without depending on ratatui or app-event channels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import unicodedata
from typing import Any, Callable, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .actions import KEYMAP_ACTIONS
from .actions import KeymapActionFilter
from .actions import action_label
from .actions import bindings_for_action
from .actions import format_binding_summary

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="keymap_setup::picker",
    source="codex/codex-rs/tui/src/keymap_setup/picker.rs",
    status="complete",
)

KEYMAP_PICKER_VIEW_ID = "keymap-picker"
KEYMAP_ALL_TAB_ID = "all-shortcuts"
KEYMAP_COMMON_TAB_ID = "common-shortcuts"
KEYMAP_CUSTOM_TAB_ID = "custom-shortcuts"
KEYMAP_UNBOUND_TAB_ID = "unbound-shortcuts"
KEYMAP_DEBUG_TAB_ID = "debug-shortcuts"
KEYMAP_CONTEXT_LABEL_WIDTH = 12
KEYMAP_ROW_PREFIX_WIDTH = KEYMAP_CONTEXT_LABEL_WIDTH + 3


@dataclass(frozen=True)
class Span:
    text: str
    style: str = "plain"


@dataclass(frozen=True)
class Header:
    lines: Tuple[str, ...]


@dataclass
class SelectionItem:
    name: str
    description: Optional[str] = None
    selected_description: Optional[str] = None
    actions: List[Callable[[Any], None]] = field(default_factory=list)
    search_value: Optional[str] = None
    name_prefix_spans: List[Span] = field(default_factory=list)
    is_disabled: bool = False


@dataclass
class SelectionTab:
    id: str
    label: str
    header: Optional[Header] = None
    items: List[SelectionItem] = field(default_factory=list)


@dataclass
class SelectionViewParams:
    view_id: Optional[str] = None
    header: Optional[Any] = None
    footer_hint: Optional[Tuple[Span, ...]] = None
    tab_footer_hints: List[Tuple[str, Tuple[Span, ...]]] = field(default_factory=list)
    tabs: List[SelectionTab] = field(default_factory=list)
    initial_tab_id: Optional[str] = None
    is_searchable: bool = False
    search_placeholder: Optional[str] = None
    col_width_mode: str = "AutoVisible"
    row_display: str = "Wrapped"
    name_column_width: Optional[int] = None
    initial_selected_idx: Optional[int] = None


@dataclass(frozen=True)
class KeymapActionRow:
    context: str
    context_label: str
    action: str
    label: str
    description: str
    binding_summary: str
    custom_binding: bool

    def is_unbound(self) -> bool:
        return self.binding_summary == "unbound"


@dataclass(frozen=True)
class KeymapContextTab:
    id: str
    label: str
    description: str
    contexts: Tuple[str, ...]


KEYMAP_COMMON_ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("composer", "submit"),
    ("chat", "interrupt_turn"),
    ("editor", "insert_newline"),
    ("composer", "queue"),
    ("global", "toggle_fast_mode"),
    ("global", "open_external_editor"),
    ("global", "copy"),
    ("global", "toggle_vim_mode"),
    ("editor", "delete_backward_word"),
    ("editor", "delete_forward_word"),
    ("editor", "move_word_left"),
    ("editor", "move_word_right"),
    ("global", "open_transcript"),
    ("pager", "close"),
    ("pager", "page_up"),
    ("pager", "page_down"),
    ("approval", "open_fullscreen"),
    ("approval", "approve"),
    ("approval", "approve_for_session"),
    ("approval", "decline"),
    ("approval", "cancel"),
)

KEYMAP_CONTEXT_TABS: Tuple[KeymapContextTab, ...] = (
    KeymapContextTab("app-shortcuts", "App", "Global and chat-level shortcuts.", ("global", "chat")),
    KeymapContextTab("composer-shortcuts", "Composer", "Composer submission and queue shortcuts.", ("composer",)),
    KeymapContextTab("editor-shortcuts", "Editor", "Inline editor movement and editing shortcuts.", ("editor",)),
    KeymapContextTab(
        "vim-shortcuts",
        "Vim",
        "Vim normal-mode and operator shortcuts.",
        ("vim_normal", "vim_operator", "vim_text_object"),
    ),
    KeymapContextTab(
        "navigation-shortcuts",
        "Navigation",
        "Pager and selection-list navigation shortcuts.",
        ("pager", "list"),
    ),
    KeymapContextTab("approval-shortcuts", "Approval", "Approval prompt shortcuts.", ("approval",)),
)


def build_keymap_picker_params(runtime_keymap: Any, keymap_config: Any) -> SelectionViewParams:
    return build_keymap_picker_params_with_filter(runtime_keymap, keymap_config, KeymapActionFilter())


def build_keymap_picker_params_with_filter(
    runtime_keymap: Any,
    keymap_config: Any,
    action_filter: KeymapActionFilter,
) -> SelectionViewParams:
    return build_keymap_picker_params_for_action(runtime_keymap, keymap_config, action_filter, None)


def build_keymap_picker_params_for_selected_action(
    runtime_keymap: Any,
    keymap_config: Any,
    context: str,
    action: str,
) -> SelectionViewParams:
    return build_keymap_picker_params_for_selected_action_with_filter(
        runtime_keymap,
        keymap_config,
        KeymapActionFilter(),
        context,
        action,
    )


def build_keymap_picker_params_for_selected_action_with_filter(
    runtime_keymap: Any,
    keymap_config: Any,
    action_filter: KeymapActionFilter,
    context: str,
    action: str,
) -> SelectionViewParams:
    return build_keymap_picker_params_for_action(runtime_keymap, keymap_config, action_filter, (context, action))


def build_keymap_picker_params_for_action(
    runtime_keymap: Any,
    keymap_config: Any,
    action_filter: KeymapActionFilter,
    selected_action: Optional[Tuple[str, str]],
) -> SelectionViewParams:
    rows = build_keymap_rows(runtime_keymap, keymap_config, action_filter)
    total = len(rows)
    custom_count = sum(1 for row in rows if row.custom_binding)
    unbound_count = sum(1 for row in rows if row.is_unbound())
    initial_selected_idx = None
    if selected_action is not None:
        selected_context, selected_name = selected_action
        initial_selected_idx = next(
            (
                idx
                for idx, row in enumerate(rows)
                if row.context == selected_context and row.action == selected_name
            ),
            None,
        )
    name_column_width = max(
        (KEYMAP_ROW_PREFIX_WIDTH + _display_width(row.label) for row in rows),
        default=None,
    )

    tabs: List[SelectionTab] = [
        SelectionTab(
            id=KEYMAP_ALL_TAB_ID,
            label="All",
            header=keymap_header(
                "All configurable shortcuts.",
                f"{total} actions, {custom_count} customized, {unbound_count} unbound.",
            ),
            items=keymap_selection_items(rows, "No shortcuts available", "No configurable shortcuts are available."),
        )
    ]

    common_rows = keymap_common_rows(rows)
    tabs.append(
        SelectionTab(
            id=KEYMAP_COMMON_TAB_ID,
            label="Common",
            header=keymap_header("Frequently customized shortcuts.", action_count_line(len(common_rows))),
            items=keymap_selection_items(common_rows, "No common shortcuts", "No common shortcut actions are available."),
        )
    )

    custom_rows = [row for row in rows if row.custom_binding]
    tabs.append(
        SelectionTab(
            id=KEYMAP_CUSTOM_TAB_ID,
            label=f"Customized ({custom_count})",
            header=keymap_header("Root-level shortcut overrides.", action_count_line(custom_count)),
            items=keymap_selection_items(custom_rows, "No customized shortcuts", "No root-level keymap overrides have been configured."),
        )
    )

    unbound_rows = [row for row in rows if row.is_unbound()]
    tabs.append(
        SelectionTab(
            id=KEYMAP_UNBOUND_TAB_ID,
            label=f"Unbound ({unbound_count})",
            header=keymap_header("Actions without an active shortcut.", action_count_line(unbound_count)),
            items=keymap_selection_items(unbound_rows, "No unbound shortcuts", "Every configurable action currently has a shortcut."),
        )
    )

    for tab in KEYMAP_CONTEXT_TABS:
        tab_rows = [row for row in rows if row.context in tab.contexts]
        tabs.append(
            SelectionTab(
                id=tab.id,
                label=tab.label,
                header=keymap_header(tab.description, action_count_line(len(tab_rows))),
                items=keymap_selection_items(tab_rows, "No shortcuts in this group", "No configurable actions are available in this group."),
            )
        )

    tabs.append(keymap_debug_tab())

    return SelectionViewParams(
        view_id=KEYMAP_PICKER_VIEW_ID,
        header=None,
        footer_hint=keymap_picker_hint_line(),
        tab_footer_hints=[(KEYMAP_DEBUG_TAB_ID, keymap_debug_hint_line())],
        tabs=tabs,
        initial_tab_id=KEYMAP_ALL_TAB_ID,
        is_searchable=True,
        search_placeholder="Type to search shortcuts",
        col_width_mode="AutoAllRows",
        row_display="SingleLine",
        name_column_width=name_column_width,
        initial_selected_idx=initial_selected_idx,
    )


def keymap_debug_tab() -> SelectionTab:
    return SelectionTab(
        id=KEYMAP_DEBUG_TAB_ID,
        label="Debug",
        header=keymap_header(
            "Inspect keypresses from your terminal.",
            "See the key Codex detects and any shortcuts assigned to it.",
        ),
        items=[
            SelectionItem(
                name="Inspect keypresses",
                description="Press Enter to start. Then press any key to inspect it; Ctrl+C exits.",
                selected_description="Open a live inspector that shows the detected key, config key, and matching actions.",
                actions=[lambda tx: _send(tx, "OpenKeymapDebug")],
                search_value="debug inspect keypress key terminal detected actions",
            )
        ],
    )


def build_keymap_rows(runtime_keymap: Any, keymap_config: Any, action_filter: KeymapActionFilter) -> List[KeymapActionRow]:
    rows: List[KeymapActionRow] = []
    for descriptor in KEYMAP_ACTIONS:
        if not descriptor.is_visible(action_filter):
            continue
        bindings = bindings_for_action(runtime_keymap, descriptor.context, descriptor.action) or []
        rows.append(
            KeymapActionRow(
                context=descriptor.context,
                context_label=descriptor.context_label,
                action=descriptor.action,
                label=action_label(descriptor.action),
                description=descriptor.description,
                binding_summary=format_binding_summary(bindings),
                custom_binding=_has_custom_binding(keymap_config, descriptor.context, descriptor.action),
            )
        )
    return rows


def keymap_common_rows(rows: Iterable[KeymapActionRow]) -> List[KeymapActionRow]:
    row_list = list(rows)
    result: List[KeymapActionRow] = []
    for context, action in KEYMAP_COMMON_ACTIONS:
        match = next((row for row in row_list if row.context == context and row.action == action), None)
        if match is not None:
            result.append(match)
    return result


def keymap_selection_items(
    rows: Iterable[KeymapActionRow],
    empty_name: str,
    empty_description: str,
) -> List[SelectionItem]:
    items = [keymap_selection_item(row) for row in rows]
    if items:
        return items
    return [SelectionItem(name=empty_name, description=empty_description, is_disabled=True)]


def keymap_selection_item(row: KeymapActionRow) -> SelectionItem:
    source = "Custom" if row.custom_binding else "Default"
    search_value = " ".join(
        [row.context_label, row.action, row.label, row.description, row.binding_summary, source]
    )

    def action(tx: Any, *, context: str = row.context, action_name: str = row.action) -> None:
        _send(tx, {"type": "OpenKeymapActionMenu", "context": context, "action": action_name})

    return SelectionItem(
        name=row.label,
        name_prefix_spans=keymap_row_prefix(row),
        description=row.binding_summary,
        actions=[action],
        search_value=search_value,
    )


def keymap_row_prefix(row: KeymapActionRow) -> List[Span]:
    if row.custom_binding:
        indicator = Span("*", "accent")
    elif row.is_unbound():
        indicator = Span("-", "dim")
    else:
        indicator = Span(" ")
    return [
        Span(f"{row.context_label:<{KEYMAP_CONTEXT_LABEL_WIDTH}} ", "dim"),
        indicator,
        Span(" ", "dim"),
    ]


def keymap_header(description: str, summary: str) -> Header:
    return Header(("Keymap", description, summary))


def action_count_line(count: int) -> str:
    if count == 1:
        return "1 action."
    return f"{count} actions."


def keymap_picker_hint_line() -> Tuple[Span, ...]:
    return (
        Span("left/right", "accent"),
        Span(" group · ", "dim"),
        Span("enter", "accent"),
        Span(" edit shortcut · ", "dim"),
        Span("*", "accent"),
        Span(" custom · ", "dim"),
        Span("-", "accent"),
        Span(" unbound · ", "dim"),
        Span("esc", "accent"),
        Span(" close", "dim"),
    )


def keymap_debug_hint_line() -> Tuple[Span, ...]:
    return (
        Span("enter", "accent"),
        Span(" start inspector · ", "dim"),
        Span("esc", "accent"),
        Span(" close", "dim"),
    )


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _has_custom_binding(keymap_config: Any, context: str, action: str) -> bool:
    return _get_path(keymap_config, (context, action)) is not None


def _get_path(root: Any, path: Tuple[str, ...]) -> Any:
    current = root
    for part in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _send(tx: Any, event: Any) -> None:
    sender = getattr(tx, "send", None)
    if callable(sender):
        sender(event)
    elif isinstance(tx, list):
        tx.append(event)
    else:
        setattr(tx, "last_event", event)


__all__ = [
    "Header",
    "KEYMAP_ALL_TAB_ID",
    "KEYMAP_COMMON_ACTIONS",
    "KEYMAP_COMMON_TAB_ID",
    "KEYMAP_CONTEXT_LABEL_WIDTH",
    "KEYMAP_CONTEXT_TABS",
    "KEYMAP_CUSTOM_TAB_ID",
    "KEYMAP_DEBUG_TAB_ID",
    "KEYMAP_PICKER_VIEW_ID",
    "KEYMAP_ROW_PREFIX_WIDTH",
    "KEYMAP_UNBOUND_TAB_ID",
    "KeymapActionRow",
    "KeymapContextTab",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionTab",
    "SelectionViewParams",
    "Span",
    "action_count_line",
    "build_keymap_picker_params",
    "build_keymap_picker_params_for_action",
    "build_keymap_picker_params_for_selected_action",
    "build_keymap_picker_params_for_selected_action_with_filter",
    "build_keymap_picker_params_with_filter",
    "build_keymap_rows",
    "keymap_common_rows",
    "keymap_debug_hint_line",
    "_display_width",
    "keymap_debug_tab",
    "keymap_header",
    "keymap_picker_hint_line",
    "keymap_row_prefix",
    "keymap_selection_item",
    "keymap_selection_items",
]

