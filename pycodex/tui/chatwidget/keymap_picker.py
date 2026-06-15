"""Chat-widget keymap picker integration for ``codex-tui::chatwidget::keymap_picker``.

Rust keeps keymap editing models in ``keymap_setup`` and ``keymap``.  This module
ports the ChatWidget-owned integration contract: opening semantic picker/capture
views, routing back to the edited row, and applying a committed runtime keymap
update to all live widget caches together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::keymap_picker",
    source="codex/codex-rs/tui/src/chatwidget/keymap_picker.rs",
    status="complete",
)

KEYMAP_PICKER_VIEW_ID = "keymap-picker"
KEYMAP_ACTION_MENU_VIEW_ID = "keymap-action-menu"
KEYMAP_REPLACE_BINDING_MENU_VIEW_ID = "keymap-replace-binding-menu"


@dataclass(frozen=True)
class KeymapActionFilter:
    fast_mode_enabled: bool = False


@dataclass(frozen=True)
class KeymapView:
    kind: str
    view_id: Optional[str] = None
    context: Optional[str] = None
    action: Optional[str] = None
    intent: Any = None
    selected_action: Optional[Tuple[str, str]] = None
    filter: Optional[KeymapActionFilter] = None
    config: Any = None
    runtime_keymap: Any = None


@dataclass
class KeymapPickerWidgetState:
    tui_keymap: Any = field(default_factory=dict)
    runtime_keymap: Any = None
    fast_mode_enabled: bool = False
    copy_last_response_binding: Any = None
    chat_keymap: Any = None
    queued_message_edit_hint_binding: Any = None
    shown_selection_views: List[KeymapView] = field(default_factory=list)
    shown_views: List[KeymapView] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    redraws: int = 0
    bottom_pane_queued_message_edit_binding: Any = None
    bottom_pane_keymap_bindings: Any = None
    replace_active_result: bool = True
    replace_calls: List[Tuple[Tuple[str, ...], KeymapView]] = field(default_factory=list)

    def open_keymap_picker(self) -> None:
        runtime_or_error = self.runtime_keymap_from_config(self.tui_keymap)
        if isinstance(runtime_or_error, Exception):
            self.add_error_message(f"Invalid `tui.keymap` configuration: {runtime_or_error}")
            return
        params = build_keymap_picker_params_with_filter(
            runtime_or_error,
            self.tui_keymap,
            self.keymap_action_filter(),
        )
        self.show_selection_view(params)

    def open_keymap_action_menu(self, context: str, action: str, runtime_keymap: Any) -> None:
        self.show_selection_view(build_keymap_action_menu_params(context, action, runtime_keymap, self.tui_keymap))

    def open_keymap_capture(self, context: str, action: str, intent: Any, runtime_keymap: Any) -> None:
        self.show_view(build_keymap_capture_view(context, action, intent, runtime_keymap))
        self.request_redraw()

    def open_keymap_debug(self, runtime_keymap: Any) -> None:
        self.show_view(build_keymap_debug_view(runtime_keymap, self.tui_keymap))
        self.request_redraw()

    def open_keymap_replace_binding_menu(self, context: str, action: str, runtime_keymap: Any) -> None:
        self.show_selection_view(build_keymap_replace_binding_menu_params(context, action, runtime_keymap))

    def return_to_keymap_picker(self, context: str, action: str, runtime_keymap: Any) -> None:
        params = build_keymap_picker_params_for_selected_action_with_filter(
            runtime_keymap,
            self.tui_keymap,
            self.keymap_action_filter(),
            context,
            action,
        )
        replaced = self.replace_active_views_with_selection_view(
            (KEYMAP_PICKER_VIEW_ID, KEYMAP_ACTION_MENU_VIEW_ID, KEYMAP_REPLACE_BINDING_MENU_VIEW_ID),
            params,
        )
        if not replaced:
            fallback = build_keymap_picker_params_for_selected_action_with_filter(
                runtime_keymap,
                self.tui_keymap,
                self.keymap_action_filter(),
                context,
                action,
            )
            self.show_selection_view(fallback)
        self.request_redraw()

    def keymap_action_filter(self) -> KeymapActionFilter:
        return KeymapActionFilter(fast_mode_enabled=bool(self.fast_mode_enabled))

    def apply_keymap_update(self, keymap_config: Any, runtime_keymap: Any) -> None:
        self.tui_keymap = keymap_config
        self.copy_last_response_binding = _get_path(runtime_keymap, "app", "copy")
        self.chat_keymap = _get(runtime_keymap, "chat")
        self.queued_message_edit_hint_binding = queued_message_edit_hint_binding(
            _get_path(self.chat_keymap, "edit_queued_message"),
        )
        self.set_queued_message_edit_binding(self.queued_message_edit_hint_binding)
        self.set_keymap_bindings(runtime_keymap)
        self.request_redraw()

    def runtime_keymap_from_config(self, config: Any) -> Any:
        if isinstance(config, Exception):
            return config
        if isinstance(config, dict) and "error" in config:
            return ValueError(str(config["error"]))
        return self.runtime_keymap if self.runtime_keymap is not None else config

    def show_selection_view(self, params: KeymapView) -> None:
        self.shown_selection_views.append(params)

    def show_view(self, view: KeymapView) -> None:
        self.shown_views.append(view)

    def replace_active_views_with_selection_view(self, view_ids: Tuple[str, ...], params: KeymapView) -> bool:
        self.replace_calls.append((view_ids, params))
        return self.replace_active_result

    def add_error_message(self, message: str) -> None:
        self.errors.append(message)

    def set_queued_message_edit_binding(self, binding: Any) -> None:
        self.bottom_pane_queued_message_edit_binding = binding

    def set_keymap_bindings(self, runtime_keymap: Any) -> None:
        self.bottom_pane_keymap_bindings = runtime_keymap

    def request_redraw(self) -> None:
        self.redraws += 1


def build_keymap_picker_params_with_filter(runtime_keymap: Any, config: Any, action_filter: KeymapActionFilter) -> KeymapView:
    return KeymapView("picker", KEYMAP_PICKER_VIEW_ID, filter=action_filter, config=config, runtime_keymap=runtime_keymap)


def build_keymap_picker_params_for_selected_action_with_filter(
    runtime_keymap: Any,
    config: Any,
    action_filter: KeymapActionFilter,
    context: str,
    action: str,
) -> KeymapView:
    return KeymapView(
        "picker",
        KEYMAP_PICKER_VIEW_ID,
        selected_action=(context, action),
        filter=action_filter,
        config=config,
        runtime_keymap=runtime_keymap,
    )


def build_keymap_action_menu_params(context: str, action: str, runtime_keymap: Any, config: Any) -> KeymapView:
    return KeymapView("action-menu", KEYMAP_ACTION_MENU_VIEW_ID, context=context, action=action, config=config, runtime_keymap=runtime_keymap)


def build_keymap_capture_view(context: str, action: str, intent: Any, runtime_keymap: Any) -> KeymapView:
    return KeymapView("capture", context=context, action=action, intent=intent, runtime_keymap=runtime_keymap)


def build_keymap_debug_view(runtime_keymap: Any, config: Any) -> KeymapView:
    return KeymapView("debug", config=config, runtime_keymap=runtime_keymap)


def build_keymap_replace_binding_menu_params(context: str, action: str, runtime_keymap: Any) -> KeymapView:
    return KeymapView("replace-binding-menu", KEYMAP_REPLACE_BINDING_MENU_VIEW_ID, context=context, action=action, runtime_keymap=runtime_keymap)


def queued_message_edit_hint_binding(binding: Any) -> Any:
    return binding


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_path(obj: Any, *names: str) -> Any:
    current = obj
    for name in names:
        current = _get(current, name)
    return current


__all__ = [
    "KEYMAP_ACTION_MENU_VIEW_ID",
    "KEYMAP_PICKER_VIEW_ID",
    "KEYMAP_REPLACE_BINDING_MENU_VIEW_ID",
    "KeymapActionFilter",
    "KeymapPickerWidgetState",
    "KeymapView",
    "RUST_MODULE",
    "build_keymap_action_menu_params",
    "build_keymap_capture_view",
    "build_keymap_debug_view",
    "build_keymap_picker_params_for_selected_action_with_filter",
    "build_keymap_picker_params_with_filter",
    "build_keymap_replace_binding_menu_params",
    "queued_message_edit_hint_binding",
]
