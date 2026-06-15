"""Semantic Python port of codex-tui ``keymap_setup/actions.rs``.

Rust owns real ``TuiKeymap`` / ``RuntimeKeymap`` storage and key event matching.
This module mirrors the keymap action catalog and exposes small semantic helpers
that work with plain Python mappings/objects and binding-like test doubles.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="keymap_setup.actions",
    source="codex/codex-rs/tui/src/keymap_setup/actions.rs",
    status="complete",
)


class KeymapActionFeature(Enum):
    FAST_MODE = "fast_mode"


@dataclass(frozen=True)
class KeymapActionFilter:
    fast_mode_enabled: bool = False


@dataclass(frozen=True)
class KeymapActionDescriptor:
    context: str
    context_label: str
    action: str
    description: str
    required_feature: Optional[KeymapActionFeature] = None

    def is_visible(self, filter: KeymapActionFilter) -> bool:
        if self.required_feature is KeymapActionFeature.FAST_MODE:
            return filter.fast_mode_enabled
        return True


@dataclass(frozen=True)
class BindingSlot:
    path: Tuple[str, ...]
    value: Any

    @property
    def is_custom(self) -> bool:
        return self.value is not None


class KeymapDebugBindingSource(Enum):
    CUSTOM = "custom"
    CUSTOM_GLOBAL = "custom_global"
    DEFAULT = "default"

    def label(self) -> str:
        if self is KeymapDebugBindingSource.CUSTOM:
            return "Custom"
        if self is KeymapDebugBindingSource.CUSTOM_GLOBAL:
            return "Custom global"
        return "Default"


@dataclass(frozen=True)
class KeymapDebugActionMatch:
    context: str
    action: str
    label: str
    description: str
    source: KeymapDebugBindingSource


def action(context: str, context_label: str, action_name: str, description: str) -> KeymapActionDescriptor:
    return KeymapActionDescriptor(context, context_label, action_name, description, None)


def gated_action(
    context: str,
    context_label: str,
    action_name: str,
    description: str,
    required_feature: KeymapActionFeature,
) -> KeymapActionDescriptor:
    return KeymapActionDescriptor(context, context_label, action_name, description, required_feature)


KEYMAP_ACTIONS: Tuple[KeymapActionDescriptor, ...] = (
    action("global", "Global", "open_transcript", "Open transcript browser"),
    action("global", "Global", "open_external_editor", "Open external editor"),
    action("global", "Global", "copy", "Copy selected text"),
    action("global", "Global", "clear_terminal", "Clear terminal"),
    action("global", "Global", "toggle_vim_mode", "Toggle Vim mode"),
    gated_action("global", "Global", "toggle_fast_mode", "Toggle fast mode", KeymapActionFeature.FAST_MODE),
    action("global", "Global", "toggle_raw_output", "Toggle raw model output"),
    action("chat", "Chat", "interrupt_turn", "Interrupt current turn"),
    action("chat", "Chat", "decrease_reasoning_effort", "Decrease reasoning effort"),
    action("chat", "Chat", "increase_reasoning_effort", "Increase reasoning effort"),
    action("chat", "Chat", "edit_queued_message", "Edit queued message"),
    action("composer", "Composer", "submit", "Submit message"),
    action("composer", "Composer", "queue", "Queue message"),
    action("composer", "Composer", "toggle_shortcuts", "Toggle shortcut help"),
    action("composer", "Composer", "history_search_previous", "Search previous history item"),
    action("composer", "Composer", "history_search_next", "Search next history item"),
    action("editor", "Editor", "insert_newline", "Insert newline"),
    action("editor", "Editor", "move_left", "Move left"),
    action("editor", "Editor", "move_right", "Move right"),
    action("editor", "Editor", "move_up", "Move up"),
    action("editor", "Editor", "move_down", "Move down"),
    action("editor", "Editor", "move_word_left", "Move word left"),
    action("editor", "Editor", "move_word_right", "Move word right"),
    action("editor", "Editor", "move_line_start", "Move to line start"),
    action("editor", "Editor", "move_line_end", "Move to line end"),
    action("editor", "Editor", "delete_backward", "Delete backward"),
    action("editor", "Editor", "delete_forward", "Delete forward"),
    action("editor", "Editor", "delete_backward_word", "Delete backward word"),
    action("editor", "Editor", "delete_forward_word", "Delete forward word"),
    action("editor", "Editor", "kill_line_start", "Kill to line start"),
    action("editor", "Editor", "kill_whole_line", "Kill whole line"),
    action("editor", "Editor", "kill_line_end", "Kill to line end"),
    action("editor", "Editor", "yank", "Yank"),
    action("vim_normal", "Vim normal", "enter_insert", "Enter insert mode"),
    action("vim_normal", "Vim normal", "append_after_cursor", "Append after cursor"),
    action("vim_normal", "Vim normal", "append_line_end", "Append at line end"),
    action("vim_normal", "Vim normal", "insert_line_start", "Insert at line start"),
    action("vim_normal", "Vim normal", "open_line_below", "Open line below"),
    action("vim_normal", "Vim normal", "open_line_above", "Open line above"),
    action("vim_normal", "Vim normal", "move_left", "Move left"),
    action("vim_normal", "Vim normal", "move_right", "Move right"),
    action("vim_normal", "Vim normal", "move_up", "Move up"),
    action("vim_normal", "Vim normal", "move_down", "Move down"),
    action("vim_normal", "Vim normal", "move_word_forward", "Move word forward"),
    action("vim_normal", "Vim normal", "move_word_backward", "Move word backward"),
    action("vim_normal", "Vim normal", "move_word_end", "Move to word end"),
    action("vim_normal", "Vim normal", "move_line_start", "Move to line start"),
    action("vim_normal", "Vim normal", "move_line_end", "Move to line end"),
    action("vim_normal", "Vim normal", "delete_char", "Delete character"),
    action("vim_normal", "Vim normal", "delete_to_line_end", "Delete to line end"),
    action("vim_normal", "Vim normal", "change_to_line_end", "Change to line end"),
    action("vim_normal", "Vim normal", "yank_line", "Yank line"),
    action("vim_normal", "Vim normal", "paste_after", "Paste after cursor"),
    action("vim_normal", "Vim normal", "start_delete_operator", "Start delete operator"),
    action("vim_normal", "Vim normal", "start_yank_operator", "Start yank operator"),
    action("vim_normal", "Vim normal", "start_change_operator", "Start change operator"),
    action("vim_normal", "Vim normal", "cancel_operator", "Cancel operator"),
    action("vim_operator", "Vim operator", "delete_line", "Delete line"),
    action("vim_operator", "Vim operator", "yank_line", "Yank line"),
    action("vim_operator", "Vim operator", "motion_left", "Motion left"),
    action("vim_operator", "Vim operator", "motion_right", "Motion right"),
    action("vim_operator", "Vim operator", "motion_up", "Motion up"),
    action("vim_operator", "Vim operator", "motion_down", "Motion down"),
    action("vim_operator", "Vim operator", "motion_word_forward", "Motion word forward"),
    action("vim_operator", "Vim operator", "motion_word_backward", "Motion word backward"),
    action("vim_operator", "Vim operator", "motion_word_end", "Motion word end"),
    action("vim_operator", "Vim operator", "motion_line_start", "Motion line start"),
    action("vim_operator", "Vim operator", "motion_line_end", "Motion line end"),
    action("vim_operator", "Vim operator", "select_inner_text_object", "Select inner text object"),
    action("vim_operator", "Vim operator", "select_around_text_object", "Select around text object"),
    action("vim_operator", "Vim operator", "cancel", "Cancel"),
    action("vim_text_object", "Vim text object", "word", "Word text object"),
    action("vim_text_object", "Vim text object", "big_word", "Big word text object"),
    action("vim_text_object", "Vim text object", "parentheses", "Parentheses text object"),
    action("vim_text_object", "Vim text object", "brackets", "Brackets text object"),
    action("vim_text_object", "Vim text object", "braces", "Braces text object"),
    action("vim_text_object", "Vim text object", "double_quote", "Double quote text object"),
    action("vim_text_object", "Vim text object", "single_quote", "Single quote text object"),
    action("vim_text_object", "Vim text object", "backtick", "Backtick text object"),
    action("vim_text_object", "Vim text object", "cancel", "Cancel"),
    action("pager", "Pager", "scroll_up", "Scroll up"),
    action("pager", "Pager", "scroll_down", "Scroll down"),
    action("pager", "Pager", "page_up", "Page up"),
    action("pager", "Pager", "page_down", "Page down"),
    action("pager", "Pager", "half_page_up", "Half page up"),
    action("pager", "Pager", "half_page_down", "Half page down"),
    action("pager", "Pager", "jump_top", "Jump to top"),
    action("pager", "Pager", "jump_bottom", "Jump to bottom"),
    action("pager", "Pager", "close", "Close pager"),
    action("pager", "Pager", "close_transcript", "Close transcript"),
    action("list", "List", "move_up", "Move up"),
    action("list", "List", "move_down", "Move down"),
    action("list", "List", "move_left", "Move left"),
    action("list", "List", "move_right", "Move right"),
    action("list", "List", "page_up", "Page up"),
    action("list", "List", "page_down", "Page down"),
    action("list", "List", "jump_top", "Jump to top"),
    action("list", "List", "jump_bottom", "Jump to bottom"),
    action("list", "List", "accept", "Accept selection"),
    action("list", "List", "cancel", "Cancel"),
    action("approval", "Approval", "open_fullscreen", "Open fullscreen"),
    action("approval", "Approval", "open_thread", "Open thread"),
    action("approval", "Approval", "approve", "Approve"),
    action("approval", "Approval", "approve_for_session", "Approve for session"),
    action("approval", "Approval", "approve_for_prefix", "Approve for prefix"),
    action("approval", "Approval", "deny", "Deny"),
    action("approval", "Approval", "decline", "Decline"),
    action("approval", "Approval", "cancel", "Cancel"),
)

_EXACT_ACTION_DESCRIPTIONS = {
    ("global", "open_transcript"): "Open the transcript overlay.",
    ("global", "open_external_editor"): "Open the current draft in an external editor.",
    ("global", "copy"): "Copy the last agent response to the clipboard.",
    ("global", "clear_terminal"): "Clear the terminal UI.",
    ("global", "toggle_vim_mode"): "Turn Vim composer mode on or off.",
    ("global", "toggle_fast_mode"): "Turn Fast mode on or off.",
    ("global", "toggle_raw_output"): "Toggle raw scrollback mode.",
    ("chat", "interrupt_turn"): "Interrupt the active turn.",
    ("chat", "decrease_reasoning_effort"): "Decrease reasoning effort.",
    ("chat", "increase_reasoning_effort"): "Increase reasoning effort.",
    ("chat", "edit_queued_message"): "Edit the most recently queued message.",
    ("composer", "submit"): "Submit the current composer draft.",
    ("composer", "queue"): "Queue the draft while a task is running.",
    ("composer", "toggle_shortcuts"): "Show or hide the composer shortcut overlay.",
    ("composer", "history_search_previous"): "Open history search or move to the previous match.",
    ("composer", "history_search_next"): "Move to the next history search match.",
    ("editor", "insert_newline"): "Insert a newline in the editor.",
    ("editor", "move_left"): "Move the cursor left.",
    ("editor", "move_right"): "Move the cursor right.",
    ("editor", "move_up"): "Move the cursor up.",
    ("editor", "move_down"): "Move the cursor down.",
    ("editor", "move_word_left"): "Move to the beginning of the previous word.",
    ("editor", "move_word_right"): "Move to the end of the next word.",
    ("editor", "move_line_start"): "Move to the beginning of the line.",
    ("editor", "move_line_end"): "Move to the end of the line.",
    ("editor", "delete_backward"): "Delete one grapheme to the left.",
    ("editor", "delete_forward"): "Delete one grapheme to the right.",
    ("editor", "delete_backward_word"): "Delete the previous word.",
    ("editor", "delete_forward_word"): "Delete the next word.",
    ("editor", "kill_line_start"): "Delete from cursor to line start.",
    ("editor", "kill_whole_line"): "Delete the current line.",
    ("editor", "kill_line_end"): "Delete from cursor to line end.",
    ("editor", "yank"): "Paste the kill buffer.",
    ("vim_normal", "enter_insert"): "Enter insert mode at the cursor.",
    ("vim_normal", "append_after_cursor"): "Enter insert mode after the cursor.",
    ("vim_normal", "append_line_end"): "Enter insert mode at end of line.",
    ("vim_normal", "insert_line_start"): "Enter insert mode at the first non-blank character.",
    ("vim_normal", "open_line_below"): "Open a new line below and enter insert mode.",
    ("vim_normal", "open_line_above"): "Open a new line above and enter insert mode.",
    ("vim_normal", "move_left"): "Move left in Vim normal mode.",
    ("vim_normal", "move_right"): "Move right in Vim normal mode.",
    ("vim_normal", "move_up"): "Move up or recall older history in Vim normal mode.",
    ("vim_normal", "move_down"): "Move down or recall newer history in Vim normal mode.",
    ("vim_normal", "move_word_forward"): "Move to the start of the next word.",
    ("vim_normal", "move_word_backward"): "Move to the start of the previous word.",
    ("vim_normal", "move_word_end"): "Move to the end of the current or next word.",
    ("vim_normal", "move_line_start"): "Move to the start of the line.",
    ("vim_normal", "move_line_end"): "Move to the end of the line.",
    ("vim_normal", "delete_char"): "Delete the character under the cursor.",
    ("vim_normal", "delete_to_line_end"): "Delete from cursor to end of line.",
    ("vim_normal", "change_to_line_end"): "Change from cursor to end of line and enter insert mode.",
    ("vim_normal", "yank_line"): "Yank the entire line.",
    ("vim_normal", "paste_after"): "Paste after the cursor.",
    ("vim_normal", "start_delete_operator"): "Begin a delete operator and wait for a motion.",
    ("vim_normal", "start_yank_operator"): "Begin a yank operator and wait for a motion.",
    ("vim_normal", "start_change_operator"): "Begin a change operator and wait for a text object.",
    ("vim_normal", "cancel_operator"): "Cancel a pending Vim operator.",
    ("vim_operator", "delete_line"): "Repeat delete operator to delete the whole line.",
    ("vim_operator", "yank_line"): "Repeat yank operator to yank the whole line.",
    ("vim_operator", "motion_left"): "Operator motion left.",
    ("vim_operator", "motion_right"): "Operator motion right.",
    ("vim_operator", "motion_up"): "Operator motion up.",
    ("vim_operator", "motion_down"): "Operator motion down.",
    ("vim_operator", "motion_word_forward"): "Operator motion to start of next word.",
    ("vim_operator", "motion_word_backward"): "Operator motion to start of previous word.",
    ("vim_operator", "motion_word_end"): "Operator motion to end of word.",
    ("vim_operator", "motion_line_start"): "Operator motion to line start.",
    ("vim_operator", "motion_line_end"): "Operator motion to line end.",
    ("vim_operator", "select_inner_text_object"): "Select an inner text object.",
    ("vim_operator", "select_around_text_object"): "Select an around text object.",
    ("vim_operator", "cancel"): "Cancel the pending operator.",
    ("vim_text_object", "word"): "Target the current word.",
    ("vim_text_object", "big_word"): "Target the current WORD.",
    ("vim_text_object", "parentheses"): "Target enclosing parentheses.",
    ("vim_text_object", "brackets"): "Target enclosing brackets.",
    ("vim_text_object", "braces"): "Target enclosing braces.",
    ("vim_text_object", "double_quote"): "Target enclosing double quotes.",
    ("vim_text_object", "single_quote"): "Target enclosing single quotes.",
    ("vim_text_object", "backtick"): "Target enclosing backticks.",
    ("vim_text_object", "cancel"): "Cancel the pending text object.",
    ("pager", "scroll_up"): "Scroll up by one row.",
    ("pager", "scroll_down"): "Scroll down by one row.",
    ("pager", "page_up"): "Scroll up by one page.",
    ("pager", "page_down"): "Scroll down by one page.",
    ("pager", "half_page_up"): "Scroll up by half a page.",
    ("pager", "half_page_down"): "Scroll down by half a page.",
    ("pager", "jump_top"): "Jump to the beginning.",
    ("pager", "jump_bottom"): "Jump to the end.",
    ("pager", "close"): "Close the pager overlay.",
    ("pager", "close_transcript"): "Close the transcript overlay.",
    ("list", "move_up"): "Move list selection up.",
    ("list", "move_down"): "Move list selection down.",
    ("list", "move_left"): "Move horizontally left in list pickers.",
    ("list", "move_right"): "Move horizontally right in list pickers.",
    ("list", "page_up"): "Move list selection up by one page.",
    ("list", "page_down"): "Move list selection down by one page.",
    ("list", "jump_top"): "Jump to the first list item.",
    ("list", "jump_bottom"): "Jump to the last list item.",
    ("list", "accept"): "Accept the current list selection.",
    ("list", "cancel"): "Cancel and close selection views.",
    ("approval", "open_fullscreen"): "Open approval details fullscreen.",
    ("approval", "open_thread"): "Open the approval source thread when available.",
    ("approval", "approve"): "Approve the primary option.",
    ("approval", "approve_for_session"): "Approve for the session when available.",
    ("approval", "approve_for_prefix"): "Approve with an exec-policy prefix when available.",
    ("approval", "deny"): "Choose the explicit deny option when available.",
    ("approval", "decline"): "Decline and provide corrective guidance.",
    ("approval", "cancel"): "Cancel an elicitation request.",
}

KEYMAP_ACTIONS = tuple(
    KeymapActionDescriptor(
        descriptor.context,
        descriptor.context_label,
        descriptor.action,
        _EXACT_ACTION_DESCRIPTIONS[(descriptor.context, descriptor.action)],
        descriptor.required_feature,
    )
    for descriptor in KEYMAP_ACTIONS
)
_ACTION_LOOKUP = {(descriptor.context, descriptor.action) for descriptor in KEYMAP_ACTIONS}
_GLOBAL_FALLBACK_ACTIONS = {"submit", "queue", "toggle_shortcuts"}


def action_label(action_name: str) -> str:
    words: List[str] = []
    for word in action_name.split("_"):
        if not word:
            words.append("")
        else:
            words.append(word[0].upper() + word[1:])
    return " ".join(words)


def binding_slot(keymap: Any, context: str, action_name: str) -> Optional[BindingSlot]:
    if (context, action_name) not in _ACTION_LOOKUP:
        return None
    path = (context, action_name)
    return BindingSlot(path, _get_path(keymap, path))


def global_fallback_slot(keymap: Any, descriptor: KeymapActionDescriptor) -> Optional[BindingSlot]:
    if descriptor.context != "composer" or descriptor.action not in _GLOBAL_FALLBACK_ACTIONS:
        return None
    path = ("global", descriptor.action)
    return BindingSlot(path, _get_path(keymap, path))


def bindings_for_action(runtime_keymap: Any, context: str, action_name: str) -> Optional[List[Any]]:
    if (context, action_name) not in _ACTION_LOOKUP:
        return None
    runtime_context = "app" if context == "global" else context
    value = _get_path(runtime_keymap, (runtime_context, action_name))
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        return [value.decode() if isinstance(value, bytes) else value]
    try:
        return list(value)
    except TypeError:
        return [value]


def format_binding_summary(bindings: Optional[Iterable[Any]]) -> str:
    seen = set()
    specs = []
    for binding in bindings or ():
        spec = _binding_to_config_key_spec(binding)
        if spec and spec not in seen:
            seen.add(spec)
            specs.append(spec)
    return ", ".join(specs) if specs else "unbound"


def matching_actions_for_key_event(
    runtime_keymap: Any,
    keymap_config: Any,
    event: Any,
) -> List[KeymapDebugActionMatch]:
    matches: List[KeymapDebugActionMatch] = []
    for descriptor in KEYMAP_ACTIONS:
        bindings = bindings_for_action(runtime_keymap, descriptor.context, descriptor.action)
        if not bindings:
            continue
        if any(_binding_is_press(binding, event) for binding in bindings):
            matches.append(
                KeymapDebugActionMatch(
                    context=descriptor.context,
                    action=descriptor.action,
                    label=action_label(descriptor.action),
                    description=descriptor.description,
                    source=debug_binding_source(keymap_config, descriptor),
                )
            )
    return matches


def debug_binding_source(keymap_config: Any, descriptor: KeymapActionDescriptor) -> KeymapDebugBindingSource:
    direct = binding_slot(keymap_config, descriptor.context, descriptor.action)
    if direct is not None and direct.is_custom:
        return KeymapDebugBindingSource.CUSTOM
    fallback = global_fallback_slot(keymap_config, descriptor)
    if fallback is not None and fallback.is_custom:
        return KeymapDebugBindingSource.CUSTOM_GLOBAL
    return KeymapDebugBindingSource.DEFAULT


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


def _binding_to_config_key_spec(binding: Any) -> Optional[str]:
    if binding is None:
        return None
    if isinstance(binding, bytes):
        return binding.decode()
    if isinstance(binding, str):
        return binding
    if isinstance(binding, dict):
        value = binding.get("config_spec", binding.get("spec", binding.get("display_label")))
        return str(value) if value is not None else None
    for attr in ("config_spec", "spec", "display_label"):
        value = getattr(binding, attr, None)
        if value is not None:
            return str(value() if callable(value) else value)
    return str(binding)


def _event_spec(event: Any) -> Optional[str]:
    if isinstance(event, bytes):
        return event.decode()
    if isinstance(event, str):
        return event
    if isinstance(event, dict):
        value = event.get("config_spec", event.get("spec", event.get("key", event.get("code"))))
        return str(value) if value is not None else None
    for attr in ("config_spec", "spec", "key", "code"):
        value = getattr(event, attr, None)
        if value is not None:
            return str(value() if callable(value) else value)
    return None


def _binding_is_press(binding: Any, event: Any) -> bool:
    is_press = getattr(binding, "is_press", None)
    if callable(is_press):
        return bool(is_press(event))
    if isinstance(binding, dict):
        is_press = binding.get("is_press")
        if callable(is_press):
            return bool(is_press(event))
    binding_spec = _binding_to_config_key_spec(binding)
    event_spec = _event_spec(event)
    return binding_spec is not None and event_spec is not None and binding_spec == event_spec


__all__ = [
    "BindingSlot",
    "KEYMAP_ACTIONS",
    "KeymapActionDescriptor",
    "KeymapActionFeature",
    "KeymapActionFilter",
    "KeymapDebugActionMatch",
    "KeymapDebugBindingSource",
    "RUST_MODULE",
    "action",
    "action_label",
    "binding_slot",
    "bindings_for_action",
    "debug_binding_source",
    "format_binding_summary",
    "gated_action",
    "global_fallback_slot",
    "matching_actions_for_key_event",
]


