"""Chat-widget keymap picker integration for ``codex-tui::chatwidget::keymap_picker``.

Rust keeps keymap editing models in ``keymap_setup`` and ``keymap``.  This module
ports the ChatWidget-owned integration contract: opening semantic picker/capture
views, routing back to the edited row, and applying a committed runtime keymap
update to all live widget caches together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .. import keymap_setup
from ..keymap import RuntimeKeymap
from ..keymap_setup import picker as keymap_picker_model
from ..bottom_pane.list_selection_view import coerce_selection_view_params
from ..bottom_pane.view_stack import TerminalSelectionTransition

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


class TerminalKeymapPopupController:
    """Terminal controller for the complete Rust ``/keymap`` edit flow."""

    def __init__(self, app_runtime: Any) -> None:
        self.app_runtime = app_runtime
        self._events: list[Any] = []
        self.keymap_config = self._current_keymap_config()
        self.runtime_keymap = RuntimeKeymap.from_config(self.keymap_config)

    def open_view(self) -> Any:
        self._refresh()
        params = keymap_picker_model.build_keymap_picker_params_with_filter(
            self.runtime_keymap,
            self.keymap_config,
            keymap_picker_model.KeymapActionFilter(
                fast_mode_enabled=bool(getattr(self.app_runtime, "fast_mode_enabled", False))
            ),
        )
        return coerce_selection_view_params(params)

    def handle_command_with_args(self, args: str) -> Any:
        if str(args).strip().lower() == "debug":
            return keymap_setup.build_keymap_debug_view(self.runtime_keymap, self.keymap_config)
        return self.open_view()

    def handle_events(self, events: tuple[object, ...]) -> TerminalSelectionTransition | None:
        pending = [*events, *self._events]
        self._events.clear()
        for event in pending:
            kind, payload = _terminal_keymap_event(event)
            if kind == "OpenKeymapActionMenu":
                params = keymap_setup.build_keymap_action_menu_params(
                    str(payload.get("context", "")),
                    str(payload.get("action", "")),
                    self.runtime_keymap,
                    self.keymap_config,
                )
                return TerminalSelectionTransition(coerce_selection_view_params(params))
            if kind == "OpenKeymapReplaceBindingMenu":
                params = keymap_setup.build_keymap_replace_binding_menu_params(
                    str(payload.get("context", "")),
                    str(payload.get("action", "")),
                    self.runtime_keymap,
                )
                return TerminalSelectionTransition(coerce_selection_view_params(params))
            if kind == "OpenKeymapCapture":
                view = keymap_setup.build_keymap_capture_view(
                    str(payload.get("context", "")),
                    str(payload.get("action", "")),
                    payload.get("intent"),
                    self.runtime_keymap,
                    self._events,
                )
                return TerminalSelectionTransition(view)
            if kind == "OpenKeymapDebug":
                return TerminalSelectionTransition(
                    keymap_setup.build_keymap_debug_view(self.runtime_keymap, self.keymap_config)
                )
            if kind == "KeymapCaptured":
                return self._apply_capture(payload)
            if kind == "KeymapCleared":
                return self._apply_clear(payload)
        return None

    def _apply_capture(self, payload: dict[str, Any]) -> TerminalSelectionTransition:
        context = str(payload.get("context", ""))
        action = str(payload.get("action", ""))
        key = str(payload.get("key", ""))
        intent = payload.get("intent")
        try:
            outcome = keymap_setup.keymap_with_edit(
                self.keymap_config,
                self.runtime_keymap,
                context,
                action,
                key,
                intent,
            )
            if outcome.kind == "Unchanged":
                self.app_runtime.chat_widget.add_info_message(outcome.message, None)
                return TerminalSelectionTransition(self._picker_for(context, action))
            candidate_runtime = RuntimeKeymap.from_config(outcome.keymap_config)
        except Exception as exc:
            params = keymap_setup.build_keymap_conflict_params(context, action, key, intent, str(exc))
            return TerminalSelectionTransition(coerce_selection_view_params(params))

        try:
            self.app_runtime.persist_keymap_update(
                context,
                action,
                outcome.keymap_config,
                candidate_runtime,
                outcome.bindings,
            )
        except Exception as exc:
            self.app_runtime.chat_widget.add_error_message(f"Failed to save shortcut: {exc}")
            return TerminalSelectionTransition(self._picker_for(context, action))
        self.keymap_config = outcome.keymap_config
        self.runtime_keymap = candidate_runtime
        self.app_runtime.chat_widget.add_info_message(outcome.message, None)
        return TerminalSelectionTransition(
            self._picker_for(context, action),
            replace_view_ids=(
                KEYMAP_PICKER_VIEW_ID,
                KEYMAP_ACTION_MENU_VIEW_ID,
                KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
            ),
        )

    def _apply_clear(self, payload: dict[str, Any]) -> TerminalSelectionTransition:
        context = str(payload.get("context", ""))
        action = str(payload.get("action", ""))
        candidate = keymap_setup.keymap_without_custom_binding(self.keymap_config, context, action)
        candidate_runtime = RuntimeKeymap.from_config(candidate)

        try:
            self.app_runtime.persist_keymap_clear(context, action, candidate, candidate_runtime)
        except Exception as exc:
            self.app_runtime.chat_widget.add_error_message(f"Failed to save shortcut: {exc}")
            return TerminalSelectionTransition(self._picker_for(context, action))
        self.keymap_config = candidate
        self.runtime_keymap = candidate_runtime
        self.app_runtime.chat_widget.add_info_message(
            f"Restored default shortcut for {context}.{action}.",
            None,
        )
        return TerminalSelectionTransition(
            self._picker_for(context, action),
            replace_view_ids=(
                KEYMAP_PICKER_VIEW_ID,
                KEYMAP_ACTION_MENU_VIEW_ID,
                KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
            ),
        )

    def _picker_for(
        self,
        context: str,
        action: str,
        config: Any = None,
        runtime: RuntimeKeymap | None = None,
    ) -> Any:
        params = keymap_picker_model.build_keymap_picker_params_for_selected_action_with_filter(
            runtime or self.runtime_keymap,
            self.keymap_config if config is None else config,
            keymap_picker_model.KeymapActionFilter(
                fast_mode_enabled=bool(getattr(self.app_runtime, "fast_mode_enabled", False))
            ),
            context,
            action,
        )
        return coerce_selection_view_params(params)

    def _refresh(self) -> None:
        self.keymap_config = self._current_keymap_config()
        self.runtime_keymap = RuntimeKeymap.from_config(self.keymap_config)

    def _current_keymap_config(self) -> Any:
        runtime = self.app_runtime.active_thread_runtime
        for source in (
            getattr(runtime, "session_config", None),
            getattr(runtime, "config", None),
            runtime,
        ):
            if source is None:
                continue
            value = source.get("tui_keymap") if isinstance(source, dict) else getattr(source, "tui_keymap", None)
            if value is not None:
                return value
        return {}


def _terminal_keymap_event(event: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(event, str):
        return event, {}
    if isinstance(event, dict):
        kind = str(event.get("type") or event.get("kind") or event.get("event") or "")
        return kind, dict(event)
    kind = str(getattr(event, "kind", ""))
    payload = getattr(event, "payload", {})
    return kind, dict(payload) if isinstance(payload, dict) else {}


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
    "TerminalKeymapPopupController",
    "RUST_MODULE",
    "build_keymap_action_menu_params",
    "build_keymap_capture_view",
    "build_keymap_debug_view",
    "build_keymap_picker_params_for_selected_action_with_filter",
    "build_keymap_picker_params_with_filter",
    "build_keymap_replace_binding_menu_params",
    "queued_message_edit_hint_binding",
]
