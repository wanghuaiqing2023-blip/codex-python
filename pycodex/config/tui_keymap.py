"""TUI keymap config schema ported from ``codex-config::tui_keymap``.

This module owns the on-disk ``[tui.keymap]`` persistence contract:
context/action shape validation, single-or-many binding values, and canonical
key-spec normalization. Runtime dispatch and conflict checks remain in
``pycodex.tui.keymap``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields
from typing import Any, ClassVar, Sequence


MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
}
MODIFIER_ORDER = ("ctrl", "alt", "shift")
KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "spacebar": "space",
    "pgup": "page-up",
    "pageup": "page-up",
    "pgdn": "page-down",
    "pagedown": "page-down",
    "del": "delete",
}
NAMED_KEYS = {
    "enter",
    "tab",
    "backspace",
    "esc",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "page-up",
    "page-down",
    "space",
    "minus",
}


def normalize_keybinding_spec(raw: str) -> str:
    """Normalize one user-authored key spec into Rust's canonical spelling."""

    lower = raw.strip().lower()
    if not lower:
        raise ValueError(
            "keybinding cannot be empty. Use values like `ctrl-a` or `shift-enter`."
        )

    segments = [segment for segment in lower.split("-") if segment]
    if not segments:
        raise ValueError(
            f"invalid keybinding `{raw}`. Use values like `ctrl-a`, `shift-enter`, or `page-down`."
        )

    modifiers = {modifier: False for modifier in MODIFIER_ORDER}
    key_segments: list[str] = []
    saw_key = False
    for segment in segments:
        modifier = MODIFIER_ALIASES.get(segment)
        if not saw_key and modifier is not None:
            if modifiers[modifier]:
                raise ValueError(
                    f"duplicate modifier in keybinding `{raw}`. Use each modifier at most once."
                )
            modifiers[modifier] = True
            continue

        saw_key = True
        key_segments.append(segment)

    if not key_segments:
        raise ValueError(
            f"missing key in keybinding `{raw}`. Add a key name like `a`, `enter`, or `page-down`."
        )

    if any(segment in MODIFIER_ALIASES for segment in key_segments):
        raise ValueError(
            f"invalid keybinding `{raw}`: modifiers must come before the key (for example `ctrl-a`)."
        )

    key = normalize_key_name("-".join(key_segments), raw)
    parts = [modifier for modifier in MODIFIER_ORDER if modifiers[modifier]]
    parts.append(key)
    return "-".join(parts)


def normalize_key_name(key: str, original: str) -> str:
    alias = KEY_ALIASES.get(key, key)
    if len(alias) == 1:
        ch = alias[0]
        if ch.isascii() and ch >= " " and ch != "-":
            return alias

    if alias in NAMED_KEYS:
        return alias

    if alias.startswith("f"):
        try:
            number = int(alias[1:])
        except ValueError:
            number = 0
        if 1 <= number <= 12:
            return alias

    raise ValueError(
        f"unknown key `{key}` in keybinding `{original}`. "
        "Use a printable character, function keys (`f1`-`f12`), or one of: "
        "enter, tab, backspace, esc, delete, arrows, home/end, page-up/page-down, space, minus."
    )


@dataclass(frozen=True)
class KeybindingSpec:
    value: str

    @classmethod
    def from_value(cls, value: Any) -> "KeybindingSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("keybinding must be a string")
        return cls(normalize_keybinding_spec(value))

    def as_str(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class KeybindingsSpec:
    specs: tuple[KeybindingSpec, ...]
    is_many: bool = False

    @classmethod
    def from_value(cls, value: Any, *, path: str = "keybinding") -> "KeybindingsSpec":
        if isinstance(value, cls):
            return value
        if isinstance(value, KeybindingSpec):
            return cls((value,), is_many=False)
        if isinstance(value, str):
            try:
                return cls((KeybindingSpec.from_value(value),), is_many=False)
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"{path}: {exc}") from exc
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            specs: list[KeybindingSpec] = []
            for index, item in enumerate(value):
                try:
                    specs.append(KeybindingSpec.from_value(item))
                except (TypeError, ValueError) as exc:
                    raise type(exc)(f"{path}[{index}]: {exc}") from exc
            return cls(tuple(specs), is_many=True)
        raise TypeError(f"{path} must be a string or array of strings")

    def spec_strings(self) -> tuple[str, ...]:
        return tuple(spec.as_str() for spec in self.specs)

    def to_value(self) -> str | list[str]:
        values = list(self.spec_strings())
        if self.is_many:
            return values
        return values[0]


class _ContextMixin:
    ACTIONS: ClassVar[tuple[str, ...]]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None, *, path: str = ""):
        value = _mapping_or_empty(value, cls.__name__)
        unknown = [str(key) for key in value if key not in cls.ACTIONS]
        if unknown:
            raise ValueError(f"unknown fields for {path or cls.__name__}: {', '.join(unknown)}")
        kwargs = {}
        for action in cls.ACTIONS:
            if action in value:
                kwargs[action] = KeybindingsSpec.from_value(value[action], path=f"{path}.{action}" if path else action)
        return cls(**kwargs)

    def to_mapping(self) -> dict[str, str | list[str]]:
        result: dict[str, str | list[str]] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if value is not None:
                result[item.name] = value.to_value()
        return result

    def is_empty(self) -> bool:
        return not self.to_mapping()


@dataclass(frozen=True)
class TuiGlobalKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "open_transcript",
        "open_external_editor",
        "copy",
        "clear_terminal",
        "submit",
        "queue",
        "toggle_shortcuts",
        "toggle_vim_mode",
        "toggle_fast_mode",
        "toggle_raw_output",
    )

    open_transcript: KeybindingsSpec | None = None
    open_external_editor: KeybindingsSpec | None = None
    copy: KeybindingsSpec | None = None
    clear_terminal: KeybindingsSpec | None = None
    submit: KeybindingsSpec | None = None
    queue: KeybindingsSpec | None = None
    toggle_shortcuts: KeybindingsSpec | None = None
    toggle_vim_mode: KeybindingsSpec | None = None
    toggle_fast_mode: KeybindingsSpec | None = None
    toggle_raw_output: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiChatKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "interrupt_turn",
        "decrease_reasoning_effort",
        "increase_reasoning_effort",
        "edit_queued_message",
    )

    interrupt_turn: KeybindingsSpec | None = None
    decrease_reasoning_effort: KeybindingsSpec | None = None
    increase_reasoning_effort: KeybindingsSpec | None = None
    edit_queued_message: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiComposerKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "submit",
        "queue",
        "toggle_shortcuts",
        "history_search_previous",
        "history_search_next",
    )

    submit: KeybindingsSpec | None = None
    queue: KeybindingsSpec | None = None
    toggle_shortcuts: KeybindingsSpec | None = None
    history_search_previous: KeybindingsSpec | None = None
    history_search_next: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiEditorKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "insert_newline",
        "move_left",
        "move_right",
        "move_up",
        "move_down",
        "move_word_left",
        "move_word_right",
        "move_line_start",
        "move_line_end",
        "delete_backward",
        "delete_forward",
        "delete_backward_word",
        "delete_forward_word",
        "kill_line_start",
        "kill_whole_line",
        "kill_line_end",
        "yank",
    )

    insert_newline: KeybindingsSpec | None = None
    move_left: KeybindingsSpec | None = None
    move_right: KeybindingsSpec | None = None
    move_up: KeybindingsSpec | None = None
    move_down: KeybindingsSpec | None = None
    move_word_left: KeybindingsSpec | None = None
    move_word_right: KeybindingsSpec | None = None
    move_line_start: KeybindingsSpec | None = None
    move_line_end: KeybindingsSpec | None = None
    delete_backward: KeybindingsSpec | None = None
    delete_forward: KeybindingsSpec | None = None
    delete_backward_word: KeybindingsSpec | None = None
    delete_forward_word: KeybindingsSpec | None = None
    kill_line_start: KeybindingsSpec | None = None
    kill_whole_line: KeybindingsSpec | None = None
    kill_line_end: KeybindingsSpec | None = None
    yank: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiVimNormalKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "enter_insert",
        "append_after_cursor",
        "append_line_end",
        "insert_line_start",
        "open_line_below",
        "open_line_above",
        "move_left",
        "move_right",
        "move_up",
        "move_down",
        "move_word_forward",
        "move_word_backward",
        "move_word_end",
        "move_line_start",
        "move_line_end",
        "delete_char",
        "delete_to_line_end",
        "change_to_line_end",
        "yank_line",
        "paste_after",
        "start_delete_operator",
        "start_yank_operator",
        "start_change_operator",
        "cancel_operator",
    )

    enter_insert: KeybindingsSpec | None = None
    append_after_cursor: KeybindingsSpec | None = None
    append_line_end: KeybindingsSpec | None = None
    insert_line_start: KeybindingsSpec | None = None
    open_line_below: KeybindingsSpec | None = None
    open_line_above: KeybindingsSpec | None = None
    move_left: KeybindingsSpec | None = None
    move_right: KeybindingsSpec | None = None
    move_up: KeybindingsSpec | None = None
    move_down: KeybindingsSpec | None = None
    move_word_forward: KeybindingsSpec | None = None
    move_word_backward: KeybindingsSpec | None = None
    move_word_end: KeybindingsSpec | None = None
    move_line_start: KeybindingsSpec | None = None
    move_line_end: KeybindingsSpec | None = None
    delete_char: KeybindingsSpec | None = None
    delete_to_line_end: KeybindingsSpec | None = None
    change_to_line_end: KeybindingsSpec | None = None
    yank_line: KeybindingsSpec | None = None
    paste_after: KeybindingsSpec | None = None
    start_delete_operator: KeybindingsSpec | None = None
    start_yank_operator: KeybindingsSpec | None = None
    start_change_operator: KeybindingsSpec | None = None
    cancel_operator: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiVimOperatorKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "delete_line",
        "yank_line",
        "motion_left",
        "motion_right",
        "motion_up",
        "motion_down",
        "motion_word_forward",
        "motion_word_backward",
        "motion_word_end",
        "motion_line_start",
        "motion_line_end",
        "select_inner_text_object",
        "select_around_text_object",
        "cancel",
    )

    delete_line: KeybindingsSpec | None = None
    yank_line: KeybindingsSpec | None = None
    motion_left: KeybindingsSpec | None = None
    motion_right: KeybindingsSpec | None = None
    motion_up: KeybindingsSpec | None = None
    motion_down: KeybindingsSpec | None = None
    motion_word_forward: KeybindingsSpec | None = None
    motion_word_backward: KeybindingsSpec | None = None
    motion_word_end: KeybindingsSpec | None = None
    motion_line_start: KeybindingsSpec | None = None
    motion_line_end: KeybindingsSpec | None = None
    select_inner_text_object: KeybindingsSpec | None = None
    select_around_text_object: KeybindingsSpec | None = None
    cancel: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiVimTextObjectKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "word",
        "big_word",
        "parentheses",
        "brackets",
        "braces",
        "double_quote",
        "single_quote",
        "backtick",
        "cancel",
    )

    word: KeybindingsSpec | None = None
    big_word: KeybindingsSpec | None = None
    parentheses: KeybindingsSpec | None = None
    brackets: KeybindingsSpec | None = None
    braces: KeybindingsSpec | None = None
    double_quote: KeybindingsSpec | None = None
    single_quote: KeybindingsSpec | None = None
    backtick: KeybindingsSpec | None = None
    cancel: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiPagerKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "scroll_up",
        "scroll_down",
        "page_up",
        "page_down",
        "half_page_up",
        "half_page_down",
        "jump_top",
        "jump_bottom",
        "close",
        "close_transcript",
    )

    scroll_up: KeybindingsSpec | None = None
    scroll_down: KeybindingsSpec | None = None
    page_up: KeybindingsSpec | None = None
    page_down: KeybindingsSpec | None = None
    half_page_up: KeybindingsSpec | None = None
    half_page_down: KeybindingsSpec | None = None
    jump_top: KeybindingsSpec | None = None
    jump_bottom: KeybindingsSpec | None = None
    close: KeybindingsSpec | None = None
    close_transcript: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiListKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "page_up",
        "page_down",
        "jump_top",
        "jump_bottom",
        "accept",
        "cancel",
    )

    move_up: KeybindingsSpec | None = None
    move_down: KeybindingsSpec | None = None
    move_left: KeybindingsSpec | None = None
    move_right: KeybindingsSpec | None = None
    page_up: KeybindingsSpec | None = None
    page_down: KeybindingsSpec | None = None
    jump_top: KeybindingsSpec | None = None
    jump_bottom: KeybindingsSpec | None = None
    accept: KeybindingsSpec | None = None
    cancel: KeybindingsSpec | None = None


@dataclass(frozen=True)
class TuiApprovalKeymap(_ContextMixin):
    ACTIONS: ClassVar[tuple[str, ...]] = (
        "open_fullscreen",
        "open_thread",
        "approve",
        "approve_for_session",
        "approve_for_prefix",
        "deny",
        "decline",
        "cancel",
    )

    open_fullscreen: KeybindingsSpec | None = None
    open_thread: KeybindingsSpec | None = None
    approve: KeybindingsSpec | None = None
    approve_for_session: KeybindingsSpec | None = None
    approve_for_prefix: KeybindingsSpec | None = None
    deny: KeybindingsSpec | None = None
    decline: KeybindingsSpec | None = None
    cancel: KeybindingsSpec | None = None


CONTEXT_TYPES = {
    "global": TuiGlobalKeymap,
    "chat": TuiChatKeymap,
    "composer": TuiComposerKeymap,
    "editor": TuiEditorKeymap,
    "vim_normal": TuiVimNormalKeymap,
    "vim_operator": TuiVimOperatorKeymap,
    "vim_text_object": TuiVimTextObjectKeymap,
    "pager": TuiPagerKeymap,
    "list": TuiListKeymap,
    "approval": TuiApprovalKeymap,
}


@dataclass(frozen=True)
class TuiKeymap(Mapping[str, dict[str, str | list[str]]]):
    global_: TuiGlobalKeymap = TuiGlobalKeymap()
    chat: TuiChatKeymap = TuiChatKeymap()
    composer: TuiComposerKeymap = TuiComposerKeymap()
    editor: TuiEditorKeymap = TuiEditorKeymap()
    vim_normal: TuiVimNormalKeymap = TuiVimNormalKeymap()
    vim_operator: TuiVimOperatorKeymap = TuiVimOperatorKeymap()
    vim_text_object: TuiVimTextObjectKeymap = TuiVimTextObjectKeymap()
    pager: TuiPagerKeymap = TuiPagerKeymap()
    list: TuiListKeymap = TuiListKeymap()
    approval: TuiApprovalKeymap = TuiApprovalKeymap()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "TuiKeymap":
        value = _mapping_or_empty(value, "TuiKeymap")
        unknown = [str(key) for key in value if key not in CONTEXT_TYPES]
        if unknown:
            raise ValueError(f"unknown fields for TuiKeymap: {', '.join(unknown)}")
        kwargs: dict[str, Any] = {}
        for context, context_type in CONTEXT_TYPES.items():
            attr = "global_" if context == "global" else context
            kwargs[attr] = context_type.from_mapping(value.get(context), path=f"tui.keymap.{context}")
        return cls(**kwargs)

    def __getattr__(self, name: str) -> Any:
        if name == "global":
            return self.global_
        raise AttributeError(name)

    def to_mapping(self) -> dict[str, dict[str, str | list[str]]]:
        result: dict[str, dict[str, str | list[str]]] = {}
        for context in CONTEXT_TYPES:
            attr = "global_" if context == "global" else context
            context_mapping = getattr(self, attr).to_mapping()
            if context_mapping:
                result[context] = context_mapping
        return result

    def is_empty(self) -> bool:
        return not self.to_mapping()

    def __getitem__(self, key: str) -> dict[str, str | list[str]]:
        return self.to_mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_mapping())

    def __len__(self) -> int:
        return len(self.to_mapping())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return self.to_mapping() == dict(other)
        if isinstance(other, TuiKeymap):
            return self.to_mapping() == other.to_mapping()
        return False


def _mapping_or_empty(value: Mapping[str, Any] | None, type_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping or None")
    return value


__all__ = [
    "KeybindingSpec",
    "KeybindingsSpec",
    "TuiApprovalKeymap",
    "TuiChatKeymap",
    "TuiComposerKeymap",
    "TuiEditorKeymap",
    "TuiGlobalKeymap",
    "TuiKeymap",
    "TuiListKeymap",
    "TuiPagerKeymap",
    "TuiVimNormalKeymap",
    "TuiVimOperatorKeymap",
    "TuiVimTextObjectKeymap",
    "normalize_key_name",
    "normalize_keybinding_spec",
]
