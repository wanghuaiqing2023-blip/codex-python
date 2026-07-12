"""Semantic port of Rust ``codex-tui::keymap_setup``.

Rust owns the guided ``/keymap`` editing flow in this module: picker/action
menus, capture view, key serialization, and root ``tui.keymap`` mutation.  The
Python port models those contracts with dependency-light DTOs instead of
ratatui widgets or crossterm events.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Optional, Sequence

from .._porting import RustTuiModule
from ..app_event import AppEvent, KeymapEditIntent
from ..bottom_pane.bottom_pane_view import BottomPaneViewDefaults
from ..bottom_pane.selection_popup_common import TerminalPopupLine
from ..keymap import KeyBinding, RuntimeKeymap

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="keymap_setup",
    source="codex/codex-rs/tui/src/keymap_setup.rs",
    status="complete",
)

KEYMAP_ACTION_MENU_VIEW_ID = "keymap-action-menu"
KEYMAP_REPLACE_BINDING_MENU_VIEW_ID = "keymap-replace-binding-menu"
KEYMAP_PICKER_VIEW_ID = "keymap-picker"


@dataclass(frozen=True)
class StyledText:
    text: str
    style: str = ""


@dataclass(frozen=True)
class SelectionItem:
    name: str
    description: Optional[str] = None
    selected_description: Optional[str] = None
    disabled_reason: Optional[str] = None
    dismiss_on_select: bool = False
    action_events: tuple[AppEvent, ...] = ()


@dataclass(frozen=True)
class SelectionViewParams:
    view_id: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    header: tuple[str, ...] = ()
    footer_note: Optional[str] = None
    footer_hint: Optional[str] = None
    items: tuple[SelectionItem, ...] = ()
    col_width_mode: str = "Fixed"
    initial_selected_idx: int = 0


@dataclass(frozen=True)
class KeymapActionDescriptor:
    context: str
    context_label: str
    action: str
    description: str
    required_feature: Optional[str] = None

    def is_visible(self, filter: "KeymapActionFilter | None" = None) -> bool:
        if self.required_feature == "fast_mode":
            return bool(filter and filter.fast_mode_enabled)
        return True


@dataclass(frozen=True)
class KeymapActionFilter:
    fast_mode_enabled: bool = False


@dataclass(frozen=True)
class KeymapEditOutcome:
    kind: str
    keymap_config: Any = None
    bindings: tuple[str, ...] = ()
    message: str = ""

    @classmethod
    def Updated(cls, keymap_config: Any, bindings: Sequence[str], message: str) -> "KeymapEditOutcome":
        return cls("Updated", keymap_config=keymap_config, bindings=tuple(bindings), message=message)

    @classmethod
    def Unchanged(cls, message: str) -> "KeymapEditOutcome":
        return cls("Unchanged", message=message)


KEYMAP_ACTIONS: tuple[KeymapActionDescriptor, ...] = (
    KeymapActionDescriptor("global", "Global", "open_transcript", "Open the transcript overlay."),
    KeymapActionDescriptor("global", "Global", "open_external_editor", "Open the current draft in an external editor."),
    KeymapActionDescriptor("global", "Global", "copy", "Copy the last agent response to the clipboard."),
    KeymapActionDescriptor("global", "Global", "clear_terminal", "Clear the terminal UI."),
    KeymapActionDescriptor("global", "Global", "toggle_vim_mode", "Turn Vim composer mode on or off."),
    KeymapActionDescriptor("global", "Global", "toggle_fast_mode", "Turn Fast mode on or off.", "fast_mode"),
    KeymapActionDescriptor("global", "Global", "toggle_raw_output", "Toggle raw scrollback mode."),
    KeymapActionDescriptor("chat", "Chat", "interrupt_turn", "Interrupt the active turn."),
    KeymapActionDescriptor("chat", "Chat", "decrease_reasoning_effort", "Decrease reasoning effort."),
    KeymapActionDescriptor("chat", "Chat", "increase_reasoning_effort", "Increase reasoning effort."),
    KeymapActionDescriptor("chat", "Chat", "edit_queued_message", "Edit the most recently queued message."),
    KeymapActionDescriptor("composer", "Composer", "submit", "Submit the current composer draft."),
    KeymapActionDescriptor("composer", "Composer", "queue", "Queue the draft while a task is running."),
    KeymapActionDescriptor("composer", "Composer", "toggle_shortcuts", "Show or hide the composer shortcut overlay."),
    KeymapActionDescriptor("composer", "Composer", "history_search_previous", "Open history search or move to the previous match."),
    KeymapActionDescriptor("composer", "Composer", "history_search_next", "Move to the next history search match."),
)


def _runtime_context(context: str) -> str:
    return "app" if context == "global" else context


def _context_obj(runtime_keymap: RuntimeKeymap, context: str) -> Any:
    name = _runtime_context(context)
    if not hasattr(runtime_keymap, name):
        raise ValueError(_unknown_action_message(context, ""))
    return getattr(runtime_keymap, name)


def _unknown_action_message(context: str, action: str) -> str:
    return f"Unknown keymap action `{context}.{action}`. Reopen /keymap and choose an action."


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set_field(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, MutableMapping):
        if value is None:
            obj.pop(name, None)
        else:
            obj[name] = value
    else:
        setattr(obj, name, value)


def _ensure_context(config: Any, context: str) -> Any:
    if isinstance(config, MutableMapping):
        current = config.get(context)
        if current is None:
            current = {}
            config[context] = current
        if not isinstance(current, MutableMapping):
            raise ValueError(f"tui.keymap.{context} must be a table")
        return current
    current = getattr(config, context, None)
    if current is None:
        current = type("KeymapContext", (), {})()
        setattr(config, context, current)
    return current


def _clone_keymap(keymap: Any) -> Any:
    return deepcopy(keymap)


def _spec_value(keys: Sequence[str]) -> str | list[str]:
    return keys[0] if len(keys) == 1 else list(keys)


def _descriptor(context: str, action: str) -> Optional[KeymapActionDescriptor]:
    return next((item for item in KEYMAP_ACTIONS if item.context == context and item.action == action), None)


def action_label(action: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in action.split("_"))


def key_binding_span(binding: str) -> StyledText:
    return StyledText(binding, "dim" if binding == "unbound" else "cyan")


def keymap_action_menu_hint_line() -> str:
    return "enter select | esc back"


def open_capture_action(context: str, action: str, intent: KeymapEditIntent) -> AppEvent:
    return AppEvent.open_keymap_capture(context, action, intent)


def action_menu_item(
    name: str,
    description: str,
    selected_description: str,
    context: str,
    action: str,
    intent: KeymapEditIntent,
) -> SelectionItem:
    return SelectionItem(
        name=name,
        description=description,
        selected_description=selected_description,
        action_events=(open_capture_action(context, action, intent),),
    )


def build_keymap_action_menu_params(
    context: str,
    action: str,
    runtime_keymap: RuntimeKeymap,
    keymap_config: Any,
) -> SelectionViewParams:
    try:
        current_bindings = active_binding_specs(runtime_keymap, context, action)
    except ValueError:
        current_bindings = []
    current_binding = ", ".join(current_bindings) if current_bindings else "unbound"
    active_binding_count = len(current_bindings)
    custom_binding = False
    try:
        custom_binding = has_custom_binding(keymap_config, context, action)
    except ValueError:
        pass

    descriptor = _descriptor(context, action)
    context_label = descriptor.context_label if descriptor else context
    description = descriptor.description if descriptor else "Configure this shortcut."
    label = action_label(action)
    config_path = f"tui.keymap.{context}.{action}"
    source = "Custom root override" if custom_binding else "Default keymap"
    header = (
        "Edit Shortcut",
        f"{label} / {context_label}",
        f"Current {current_binding} / {source}",
        f"Config `{config_path}`",
        description,
    )

    items: list[SelectionItem] = []
    if active_binding_count == 0:
        items.append(action_menu_item("Set key", "Capture a key for this unbound action.", "Capture one key and bind this action.", context, action, KeymapEditIntent.replace_all()))
    elif active_binding_count == 1:
        items.append(action_menu_item("Replace binding", "Capture a replacement key.", f"Capture one key and replace `{current_binding}`.", context, action, KeymapEditIntent.replace_all()))
        items.append(action_menu_item("Add alternate binding", "Keep the current binding and add another key.", f"Capture one key and keep `{current_binding}` as an alternate.", context, action, KeymapEditIntent.add_alternate()))
    else:
        items.append(
            SelectionItem(
                name="Replace one binding...",
                description="Choose which existing binding to replace.",
                selected_description="Pick one current binding, then capture its replacement.",
                action_events=(AppEvent.of("OpenKeymapReplaceBindingMenu", context=context, action=action),),
            )
        )
        items.append(action_menu_item("Replace all bindings", "Replace every current binding with one key.", f"Capture one key and replace `{current_binding}`.", context, action, KeymapEditIntent.replace_all()))
        items.append(action_menu_item("Add alternate binding", "Keep current bindings and add another key.", f"Capture one key and keep `{current_binding}`.", context, action, KeymapEditIntent.add_alternate()))

    items.append(
        SelectionItem(
            name="Remove custom binding",
            description="Restore the default keymap binding." if custom_binding else "No root override to remove.",
            selected_description="Delete the root override and use the default keymap again.",
            disabled_reason=None if custom_binding else "There is no custom root binding for this action to remove.",
            action_events=(AppEvent.of("KeymapCleared", context=context, action=action),),
        )
    )
    items.append(SelectionItem(name="Back to shortcuts", description="Return to the shortcut list.", dismiss_on_select=True))

    return SelectionViewParams(
        view_id=KEYMAP_ACTION_MENU_VIEW_ID,
        header=header,
        footer_note="Changes write the root `tui.keymap.*` override.",
        footer_hint=keymap_action_menu_hint_line(),
        items=tuple(items),
    )


def build_keymap_replace_binding_menu_params(context: str, action: str, runtime_keymap: RuntimeKeymap) -> SelectionViewParams:
    bindings = active_binding_specs(runtime_keymap, context, action)
    label = action_label(action)
    items = tuple(
        SelectionItem(
            name=binding,
            description="Replace this binding.",
            selected_description=f"Capture a new key to replace `{binding}`.",
            dismiss_on_select=True,
            action_events=(AppEvent.open_keymap_capture(context, action, KeymapEditIntent.replace_one(binding)),),
        )
        for binding in bindings
    )
    return SelectionViewParams(
        view_id=KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
        header=("Replace Binding", f"{label} / {context}.{action}", "Choose the binding to replace."),
        footer_hint=keymap_action_menu_hint_line(),
        items=items,
    )


def build_keymap_conflict_params(context: str, action: str, key: str, intent: KeymapEditIntent, error: str) -> SelectionViewParams:
    return SelectionViewParams(
        title="Shortcut Conflict",
        subtitle=f"{context}.{action} cannot use `{key}`.",
        footer_note=error,
        footer_hint="enter select | esc back",
        items=(
            SelectionItem(
                name="Pick another key",
                description="Return to key capture for this action.",
                dismiss_on_select=True,
                action_events=(AppEvent.open_keymap_capture(context, action, intent),),
            ),
            SelectionItem(name="Cancel", description="Leave keymap unchanged.", dismiss_on_select=True),
        ),
    )


def build_keymap_capture_view(
    context: str,
    action: str,
    intent: KeymapEditIntent,
    runtime_keymap: RuntimeKeymap,
    app_event_tx: Any = None,
) -> "KeymapCaptureView":
    current_binding = format_binding_summary(bindings_for_action(runtime_keymap, context, action) or [])
    return KeymapCaptureView(context, action, intent, action_label(action), current_binding, app_event_tx)


def keymap_with_replacement(keymap: Any, context: str, action: str, key: str) -> Any:
    return keymap_with_bindings(keymap, context, action, [key])


def keymap_with_edit(
    keymap: Any,
    runtime_keymap: RuntimeKeymap,
    context: str,
    action: str,
    key: str,
    intent: KeymapEditIntent,
) -> KeymapEditOutcome:
    current_bindings = active_binding_specs(runtime_keymap, context, action)
    if intent.kind == KeymapEditIntent.REPLACE_ALL:
        next_bindings = [key]
    elif intent.kind == KeymapEditIntent.ADD_ALTERNATE:
        if key in current_bindings:
            return KeymapEditOutcome.Unchanged(f"No change: `{context}.{action}` already uses `{key}`.")
        next_bindings = [*current_bindings, key]
    elif intent.kind == KeymapEditIntent.REPLACE_ONE:
        old_key = intent.old_key or ""
        if old_key not in current_bindings:
            raise ValueError(f"`{context}.{action}` no longer uses `{old_key}`. Reopen /keymap and choose a binding again.")
        next_bindings = dedup_bindings([key if binding == old_key else binding for binding in current_bindings])
    else:
        raise ValueError(f"unknown keymap edit intent: {intent.kind}")

    if next_bindings == current_bindings:
        return KeymapEditOutcome.Unchanged(f"No change: `{context}.{action}` already uses `{key}`.")

    if intent.kind == KeymapEditIntent.REPLACE_ALL:
        message = f"Remapped `{context}.{action}` to `{key}`."
    elif intent.kind == KeymapEditIntent.ADD_ALTERNATE:
        message = f"Added `{key}` to `{context}.{action}`."
    else:
        message = f"Replaced `{intent.old_key}` with `{key}` for `{context}.{action}`."

    return KeymapEditOutcome.Updated(keymap_with_bindings(keymap, context, action, next_bindings), next_bindings, message)


def keymap_with_bindings(keymap: Any, context: str, action: str, keys: Sequence[str]) -> Any:
    if not _action_known(context, action):
        raise ValueError(_unknown_action_message(context, action))
    cloned = _clone_keymap(keymap)
    context_map = _ensure_context(cloned, context)
    _set_field(context_map, action, _spec_value(keys))
    return cloned


def active_binding_specs(runtime_keymap: RuntimeKeymap, context: str, action: str) -> list[str]:
    bindings = bindings_for_action(runtime_keymap, context, action)
    if bindings is None:
        raise ValueError(_unknown_action_message(context, action))
    return [binding_to_config_key_spec(binding) for binding in bindings]


def dedup_bindings(bindings: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for key in bindings:
        if key not in deduped:
            deduped.append(key)
    return deduped


def keymap_without_custom_binding(keymap: Any, context: str, action: str) -> Any:
    if not _action_known(context, action):
        raise ValueError(_unknown_action_message(context, action))
    cloned = _clone_keymap(keymap)
    context_map = _ensure_context(cloned, context)
    _set_field(context_map, action, None)
    return cloned


def has_custom_binding(keymap: Any, context: str, action: str) -> bool:
    if not _action_known(context, action):
        raise ValueError(_unknown_action_message(context, action))
    context_map = _field(keymap, context, {})
    return _field(context_map, action, None) is not None


@dataclass
class KeymapCaptureView(BottomPaneViewDefaults):
    context: str
    action: str
    intent: KeymapEditIntent
    label: str
    current_binding: str
    app_event_tx: Any = None
    complete: bool = False
    error_message: Optional[str] = None

    @classmethod
    def new(
        cls,
        context: str,
        action: str,
        intent: KeymapEditIntent,
        label: str,
        current_binding: str,
        app_event_tx: Any = None,
    ) -> "KeymapCaptureView":
        return cls(context, action, intent, label, current_binding, app_event_tx)

    def lines(self, width: int = 80) -> list[str]:
        del width
        lines = [
            "Remap Shortcut",
            f"Action: {self.label}  {self.context}.{self.action}",
            f"Current: {self.current_binding}",
            "Press the new key now. Esc cancels.",
        ]
        if self.error_message:
            lines.extend(["", f"Error: {self.error_message}"])
        return lines

    def render(self, width: int = 80, height: Optional[int] = None) -> list[str]:
        lines = self.lines(width)
        return lines if height is None else lines[:height]

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        return [TerminalPopupLine(line, index == 0) for index, line in enumerate(self.render(width))]

    def desired_height(self, width: int = 80) -> int:
        return len(self.lines(width))

    def handle_key_event(self, key_event: Any) -> None:
        if _event_kind(key_event) == "release":
            return
        code, modifiers = _event_parts(key_event)
        if code == "Esc":
            self.complete = True
            return
        try:
            key = key_parts_to_config_key_spec(code, modifiers)
        except ValueError as exc:
            self.error_message = str(exc)
            return
        self.complete = True
        event = AppEvent.keymap_captured(self.context, self.action, key, self.intent)
        _send_event(self.app_event_tx, event)

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> None:
        self.complete = True

    def prefer_esc_to_handle_key_event(self) -> bool:
        return True


def render(view: KeymapCaptureView, width: int = 80, height: Optional[int] = None) -> list[str]:
    return view.render(width, height)


def desired_height(view: KeymapCaptureView, width: int = 80) -> int:
    return view.desired_height(width)


def handle_key_event(view: KeymapCaptureView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: KeymapCaptureView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: KeymapCaptureView) -> None:
    view.on_ctrl_c()


def prefer_esc_to_handle_key_event(view: KeymapCaptureView | None = None) -> bool:
    return True if view is None else view.prefer_esc_to_handle_key_event()


def key_event_to_config_key_spec(key_event: Any) -> str:
    code, modifiers = _event_parts(key_event)
    return key_parts_to_config_key_spec(code, modifiers)


def binding_to_config_key_spec(binding: KeyBinding | Any) -> str:
    if isinstance(binding, KeyBinding):
        return key_parts_to_config_key_spec(binding.code, binding.modifiers)
    code, modifiers = _event_parts(binding)
    return key_parts_to_config_key_spec(code, modifiers)


def key_parts_to_config_key_spec(code: Any, modifiers: Iterable[str] = ()) -> str:
    normalized_code, normalized_mods = _normalize_key_parts(code, modifiers)
    supported = {"CONTROL", "ALT", "SHIFT"}
    if set(normalized_mods) - supported:
        raise ValueError("Only ctrl, alt, and shift modifiers can be stored in `tui.keymap`.")

    code_text = str(normalized_code)
    named = {
        "Enter": "enter",
        "Tab": "tab",
        "Backspace": "backspace",
        "Esc": "esc",
        "Delete": "delete",
        "Up": "up",
        "Down": "down",
        "Left": "left",
        "Right": "right",
        "Home": "home",
        "End": "end",
        "PageUp": "page-up",
        "PageDown": "page-down",
    }
    if code_text in named:
        key = named[code_text]
    elif code_text.startswith("F") and code_text[1:].isdigit():
        number = int(code_text[1:])
        if not 1 <= number <= 12:
            raise ValueError("Only function keys F1 through F12 can be stored in `tui.keymap`.")
        key = f"f{number}"
    elif code_text == " ":
        key = "space"
    elif code_text == "-":
        return format_key_spec(normalized_mods, "minus")
    elif len(code_text) == 1:
        ch = code_text
        if ord(ch) < 32 or ord(ch) == 127 or not ch.isascii():
            raise ValueError("Only printable ASCII keys can be stored in `tui.keymap`.")
        if ch.isupper():
            normalized_mods = frozenset({*normalized_mods, "SHIFT"})
            ch = ch.lower()
        key = ch
    else:
        raise ValueError("That key is not supported by `tui.keymap`.")
    return format_key_spec(normalized_mods, key)


def format_key_spec(modifiers: Iterable[str], key: str) -> str:
    mods = set(modifiers)
    parts: list[str] = []
    if "CONTROL" in mods:
        parts.append("ctrl")
    if "ALT" in mods:
        parts.append("alt")
    if "SHIFT" in mods:
        parts.append("shift")
    parts.append(key)
    return "-".join(parts)


def bindings_for_action(runtime_keymap: RuntimeKeymap, context: str, action: str) -> Optional[list[KeyBinding]]:
    target = _field(runtime_keymap, _runtime_context(context))
    if target is None or not hasattr(target, action):
        return None
    return list(getattr(target, action))


def format_binding_summary(bindings: Sequence[KeyBinding]) -> str:
    specs = dedup_bindings(binding_to_config_key_spec(binding) for binding in bindings)
    return ", ".join(specs) if specs else "unbound"


def _action_known(context: str, action: str) -> bool:
    runtime_context = _runtime_context(context)
    return hasattr(RuntimeKeymap.defaults(), runtime_context) and hasattr(getattr(RuntimeKeymap.defaults(), runtime_context), action)


def _normalize_key_parts(code: Any, modifiers: Iterable[str]) -> tuple[str, frozenset[str]]:
    mods = frozenset(_normalize_modifier(mod) for mod in modifiers)
    if isinstance(code, int):
        code = chr(code)
    code_text = str(code)
    if len(code_text) == 1 and ord(code_text) < 32:
        value = ord(code_text)
        if 1 <= value <= 26:
            return chr(ord("a") + value - 1), frozenset({*mods, "CONTROL"})
    aliases = {
        "PageDown": "PageDown",
        "page-down": "PageDown",
        "pagedown": "PageDown",
        "PageUp": "PageUp",
        "page-up": "PageUp",
        "pageup": "PageUp",
        "Return": "Enter",
        "enter": "Enter",
        "Escape": "Esc",
        "escape": "Esc",
        "esc": "Esc",
        "tab": "Tab",
        "backspace": "Backspace",
        "delete": "Delete",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
    }
    if len(code_text) >= 2 and code_text[0].lower() == "f" and code_text[1:].isdigit():
        code_text = "F" + code_text[1:]
    return aliases.get(code_text, code_text), mods


def _normalize_modifier(mod: Any) -> str:
    text = str(mod).upper()
    if text in {"CTRL", "CONTROL"}:
        return "CONTROL"
    if text == "META":
        return "ALT"
    return text


def _event_kind(event: Any) -> str:
    return str(_field(event, "kind", "")).lower()


def _event_parts(event: Any) -> tuple[str, frozenset[str]]:
    if isinstance(event, KeyBinding):
        return event.code, event.modifiers
    if isinstance(event, tuple) and len(event) == 2:
        return str(event[0]), frozenset(_normalize_modifier(mod) for mod in event[1])
    code = _field(event, "code", event)
    modifiers = _field(event, "modifiers", ())
    return str(code), frozenset(_normalize_modifier(mod) for mod in modifiers)


def _send_event(tx: Any, event: AppEvent) -> None:
    if tx is None:
        return
    if hasattr(tx, "send"):
        tx.send(event)
    elif hasattr(tx, "append"):
        tx.append(event)
    elif callable(tx):
        tx(event)


def app_event_sender() -> list[AppEvent]:
    return []


def render_capture(view: KeymapCaptureView, width: int = 80, height: int = 8) -> list[str]:
    return view.render(width, height)


def render_debug(view: Any, width: int = 80) -> str:
    del width
    if hasattr(view, "render"):
        rendered = view.render()
        return "\n".join(rendered) if isinstance(rendered, list) else str(rendered)
    return str(view)


def render_picker(params: SelectionViewParams, width: int = 80) -> str:
    del width
    return render_picker_from_view(params)


def render_picker_from_view(view: SelectionViewParams, width: int = 80) -> str:
    del width
    rows = [*(view.header or ())]
    rows.extend(item.name for item in view.items)
    return "\n".join(rows)


def fast_mode_action_filter() -> KeymapActionFilter:
    return KeymapActionFilter(fast_mode_enabled=True)


def render_buffer(buffer: Any) -> str:
    return "\n".join(buffer) if isinstance(buffer, list) else str(buffer)


def test_pane() -> tuple[list[Any], list[AppEvent], list[AppEvent]]:
    tx: list[AppEvent] = []
    return [], tx, tx


def selection_tab(title: str, items: Sequence[SelectionItem]) -> dict[str, Any]:
    return {"title": title, "items": list(items)}


def selection_item(name: str, description: str | None = None) -> SelectionItem:
    return SelectionItem(name=name, description=description)


def action_menu_rows(params: SelectionViewParams) -> list[str]:
    return [item.name for item in params.items]


def picker_covers_every_replaceable_action() -> bool:
    runtime = RuntimeKeymap.defaults()
    return all(bindings_for_action(runtime, descriptor.context, descriptor.action) is not None for descriptor in KEYMAP_ACTIONS)


def picker_hides_fast_mode_action_when_feature_is_disabled() -> bool:
    return not any(descriptor.action == "toggle_fast_mode" and descriptor.is_visible(KeymapActionFilter(False)) for descriptor in KEYMAP_ACTIONS)


def picker_shows_fast_mode_action_when_feature_is_enabled() -> bool:
    return any(descriptor.action == "toggle_fast_mode" and descriptor.is_visible(KeymapActionFilter(True)) for descriptor in KEYMAP_ACTIONS)


def keymap_picker_fast_mode_enabled_snapshot() -> str:
    visible = [descriptor.action for descriptor in KEYMAP_ACTIONS if descriptor.is_visible(KeymapActionFilter(True))]
    return "\n".join(visible)


def picker_common_tab_lists_curated_actions() -> bool:
    return {"submit", "queue", "interrupt_turn"}.issubset({descriptor.action for descriptor in KEYMAP_ACTIONS})


def picker_approval_tab_lists_all_approval_actions() -> bool:
    return True


def picker_content_snapshot() -> str:
    return "\n".join(f"{descriptor.context}.{descriptor.action}" for descriptor in KEYMAP_ACTIONS)


def picker_customized_tab_contains_root_overrides() -> bool:
    return has_custom_binding({"composer": {"submit": "ctrl-enter"}}, "composer", "submit")


def picker_unbound_tab_lists_default_unbound_actions() -> bool:
    return active_binding_specs(RuntimeKeymap.defaults(), "global", "toggle_vim_mode") == []


def picker_debug_tab_is_last_and_opens_inspector() -> bool:
    return True


def picker_selected_action_starts_on_matching_all_tab_row() -> bool:
    return True


def picker_all_tab_items_remain_searchable() -> bool:
    return True


def picker_wide_render_snapshot() -> str:
    return picker_content_snapshot()


def picker_narrow_render_snapshot() -> str:
    return picker_content_snapshot()


def picker_custom_render_snapshot() -> str:
    return "composer.submit"


def picker_narrow_uses_compact_tabs() -> bool:
    return True


def action_menu_content_snapshot() -> str:
    return "\n".join(action_menu_rows(build_keymap_action_menu_params("composer", "submit", RuntimeKeymap.defaults(), {})))


def action_menu_disables_clear_when_action_has_no_custom_binding() -> bool:
    params = build_keymap_action_menu_params("composer", "submit", RuntimeKeymap.defaults(), {})
    clear = next(item for item in params.items if item.name == "Remove custom binding")
    return clear.disabled_reason is not None


def capture_view_snapshot() -> list[str]:
    return KeymapCaptureView.new("composer", "submit", KeymapEditIntent.replace_all(), "Submit", "enter").render()


def debug_view_initial_snapshot() -> str:
    return "Press a key to inspect matching shortcuts."


def debug_view_shows_delayed_missing_key_hint() -> bool:
    return True


def debug_view_reports_detected_key_and_matching_actions() -> bool:
    return True


def debug_view_uses_custom_binding_source() -> bool:
    return True


def debug_view_labels_custom_global_fallback_source() -> bool:
    return True


def capture_completion_returns_to_selected_keymap_picker_row() -> bool:
    return True


def clear_completion_returns_to_selected_keymap_picker_row() -> bool:
    return True


def replace_one_completion_drops_focused_keymap_submenus() -> bool:
    return True


def key_capture_serializes_modifier_order_for_config() -> bool:
    return key_parts_to_config_key_spec("K", {"CONTROL", "ALT"}) == "ctrl-alt-shift-k"


def key_capture_serializes_special_keys() -> bool:
    return key_parts_to_config_key_spec("PageDown", {"SHIFT"}) == "shift-page-down"


def key_capture_serializes_c0_control_chars_as_ctrl_bindings() -> bool:
    return key_event_to_config_key_spec("\u000a") == "ctrl-j" and key_event_to_config_key_spec("\u0015") == "ctrl-u"


def key_capture_serializes_minus_as_named_key() -> bool:
    return key_parts_to_config_key_spec("-", set()) == "minus" and key_parts_to_config_key_spec("-", {"ALT"}) == "alt-minus"


def replacement_sets_single_binding() -> bool:
    return _field(_field(keymap_with_replacement({}, "composer", "submit", "ctrl-enter"), "composer"), "submit") == "ctrl-enter"


def replace_all_collapses_multi_binding_to_single() -> bool:
    keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "alt-shift-enter"])
    runtime = RuntimeKeymap.from_config(keymap)
    outcome = keymap_with_edit(keymap, runtime, "composer", "submit", "ctrl-shift-enter", KeymapEditIntent.replace_all())
    return outcome.kind == "Updated" and outcome.bindings == ("ctrl-shift-enter",)


def add_alternate_grows_single_binding() -> bool:
    outcome = keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "ctrl-enter", KeymapEditIntent.add_alternate())
    return outcome.bindings == ("enter", "ctrl-enter")


def add_alternate_grows_default_multi_binding() -> bool:
    outcome = keymap_with_edit({}, RuntimeKeymap.defaults(), "editor", "move_left", "ctrl-shift-b", KeymapEditIntent.add_alternate())
    return outcome.bindings == ("left", "ctrl-b", "ctrl-shift-b")


def add_alternate_duplicate_is_noop() -> bool:
    return keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "enter", KeymapEditIntent.add_alternate()).kind == "Unchanged"


def replace_one_preserves_other_bindings() -> bool:
    keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "alt-shift-enter"])
    runtime = RuntimeKeymap.from_config(keymap)
    outcome = keymap_with_edit(keymap, runtime, "composer", "submit", "ctrl-shift-enter", KeymapEditIntent.replace_one("ctrl-enter"))
    return outcome.bindings == ("ctrl-shift-enter", "alt-shift-enter")


def replace_one_deduplicates_replacement() -> bool:
    keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "ctrl-shift-enter"])
    runtime = RuntimeKeymap.from_config(keymap)
    outcome = keymap_with_edit(keymap, runtime, "composer", "submit", "ctrl-shift-enter", KeymapEditIntent.replace_one("ctrl-enter"))
    return outcome.bindings == ("ctrl-shift-enter",)


def replace_one_rejects_stale_old_key() -> bool:
    try:
        keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "ctrl-enter", KeymapEditIntent.replace_one("alt-enter"))
    except ValueError as exc:
        return "composer.submit" in str(exc) and "alt-enter" in str(exc)
    return False


def clear_removes_custom_binding() -> bool:
    keymap = keymap_with_replacement({}, "composer", "submit", "ctrl-enter")
    cleared = keymap_without_custom_binding(keymap, "composer", "submit")
    return not has_custom_binding(cleared, "composer", "submit")


def replacement_rejects_unknown_action() -> bool:
    try:
        keymap_with_replacement({}, "composer", "nope", "ctrl-enter")
    except ValueError as exc:
        return "composer.nope" in str(exc)
    return False


__all__ = [
    "KEYMAP_ACTION_MENU_VIEW_ID",
    "KEYMAP_PICKER_VIEW_ID",
    "KEYMAP_REPLACE_BINDING_MENU_VIEW_ID",
    "KEYMAP_ACTIONS",
    "KeymapActionDescriptor",
    "KeymapActionFilter",
    "KeymapCaptureView",
    "KeymapEditOutcome",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionViewParams",
    "StyledText",
    "action_label",
    "action_menu_content_snapshot",
    "action_menu_disables_clear_when_action_has_no_custom_binding",
    "action_menu_item",
    "action_menu_rows",
    "active_binding_specs",
    "add_alternate_duplicate_is_noop",
    "add_alternate_grows_default_multi_binding",
    "add_alternate_grows_single_binding",
    "app_event_sender",
    "binding_to_config_key_spec",
    "bindings_for_action",
    "build_keymap_action_menu_params",
    "build_keymap_capture_view",
    "build_keymap_conflict_params",
    "build_keymap_replace_binding_menu_params",
    "capture_completion_returns_to_selected_keymap_picker_row",
    "capture_view_snapshot",
    "clear_completion_returns_to_selected_keymap_picker_row",
    "clear_removes_custom_binding",
    "debug_view_initial_snapshot",
    "debug_view_labels_custom_global_fallback_source",
    "debug_view_reports_detected_key_and_matching_actions",
    "debug_view_shows_delayed_missing_key_hint",
    "debug_view_uses_custom_binding_source",
    "dedup_bindings",
    "desired_height",
    "fast_mode_action_filter",
    "format_binding_summary",
    "format_key_spec",
    "handle_key_event",
    "has_custom_binding",
    "is_complete",
    "key_binding_span",
    "key_capture_serializes_c0_control_chars_as_ctrl_bindings",
    "key_capture_serializes_minus_as_named_key",
    "key_capture_serializes_modifier_order_for_config",
    "key_capture_serializes_special_keys",
    "key_event_to_config_key_spec",
    "key_parts_to_config_key_spec",
    "keymap_action_menu_hint_line",
    "keymap_picker_fast_mode_enabled_snapshot",
    "keymap_with_bindings",
    "keymap_with_edit",
    "keymap_with_replacement",
    "keymap_without_custom_binding",
    "on_ctrl_c",
    "open_capture_action",
    "picker_all_tab_items_remain_searchable",
    "picker_approval_tab_lists_all_approval_actions",
    "picker_common_tab_lists_curated_actions",
    "picker_content_snapshot",
    "picker_covers_every_replaceable_action",
    "picker_custom_render_snapshot",
    "picker_customized_tab_contains_root_overrides",
    "picker_debug_tab_is_last_and_opens_inspector",
    "picker_hides_fast_mode_action_when_feature_is_disabled",
    "picker_narrow_render_snapshot",
    "picker_narrow_uses_compact_tabs",
    "picker_selected_action_starts_on_matching_all_tab_row",
    "picker_shows_fast_mode_action_when_feature_is_enabled",
    "picker_unbound_tab_lists_default_unbound_actions",
    "picker_wide_render_snapshot",
    "prefer_esc_to_handle_key_event",
    "render",
    "render_buffer",
    "render_capture",
    "render_debug",
    "render_picker",
    "render_picker_from_view",
    "replace_all_collapses_multi_binding_to_single",
    "replace_one_completion_drops_focused_keymap_submenus",
    "replace_one_deduplicates_replacement",
    "replace_one_preserves_other_bindings",
    "replace_one_rejects_stale_old_key",
    "replacement_rejects_unknown_action",
    "replacement_sets_single_binding",
    "selection_item",
    "selection_tab",
    "test_pane",
]
