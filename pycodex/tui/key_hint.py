"""Behavior port for Rust ``codex-tui::key_hint``."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="key_hint", source="codex/codex-rs/tui/src/key_hint.rs")

ALT_PREFIX = "⌥ + "
CTRL_PREFIX = "ctrl + "
SHIFT_PREFIX = "shift + "
UP_LABEL = "↑"
DOWN_LABEL = "↓"
LEFT_LABEL = "←"
RIGHT_LABEL = "→"

MOD_CONTROL = "control"
MOD_SHIFT = "shift"
MOD_ALT = "alt"


@dataclass(frozen=True)
class KeyEvent:
    code: str
    modifiers: FrozenSet[str] = frozenset()
    kind: str = "press"

    @classmethod
    def new(cls, code: Any, modifiers: Any = None, kind: str = "press") -> "KeyEvent":
        return cls(code=_coerce_key(code), modifiers=_coerce_modifiers(modifiers), kind=str(kind).lower())


@dataclass(frozen=True)
class Span:
    text: str
    style: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class KeyBinding:
    """One concrete key event that can trigger a TUI action."""

    key: str
    modifiers: FrozenSet[str] = frozenset()

    @classmethod
    def new(cls, key: Any, modifiers: Any = None) -> "KeyBinding":
        return cls(_coerce_key(key), _coerce_modifiers(modifiers))

    @classmethod
    def from_event(cls, event: Any) -> "KeyBinding":
        key, modifiers = normalize_key_parts(_event_code(event), _event_modifiers(event))
        return cls(key, modifiers)

    def is_press(self, event: Any) -> bool:
        key, modifiers = normalize_key_parts(self.key, self.modifiers)
        event_key, event_modifiers = normalize_key_parts(_event_code(event), _event_modifiers(event))
        return (key, modifiers) == (event_key, event_modifiers) and _event_kind(event) in {"press", "repeat"}

    def parts(self) -> Tuple[str, FrozenSet[str]]:
        return self.key, self.modifiers

    def display_label(self) -> str:
        modifiers = modifiers_to_string(self.modifiers)
        key = _display_key(self.key)
        return f"{modifiers}{key}"

    def to_span(self) -> Span:
        return Span(self.display_label(), key_hint_style())


class KeyBindingListExt:
    def is_pressed(self, event: Any) -> bool:
        raise NotImplementedError


def normalize_key_parts(key: Any, modifiers: Any = None) -> Tuple[str, FrozenSet[str]]:
    key = _coerce_key(key)
    mods = set(_coerce_modifiers(modifiers))
    if _is_char_key(key):
        ch = key
        if not mods:
            ctrl_char = c0_control_char_to_ctrl_char(ch)
            if ctrl_char is not None:
                return ctrl_char, frozenset({MOD_CONTROL})
        if ch.isascii() and ch.isupper():
            mods.add(MOD_SHIFT)
            return ch.lower(), frozenset(mods)
    return key, frozenset(mods)


def c0_control_char_to_ctrl_char(ch: str) -> Optional[str]:
    if len(ch) != 1:
        return None
    code = ord(ch)
    if code == 0x00:
        return " "
    if 0x01 <= code <= 0x1A:
        return chr(code - 0x01 + ord("a"))
    if 0x1C <= code <= 0x1F:
        return chr(code - 0x1C + ord("4"))
    return None


def is_pressed(bindings: Iterable[KeyBinding], event: Any) -> bool:
    return any(binding.is_press(event) for binding in bindings)


def is_plain_text_key_event(event: Any) -> bool:
    code = _event_code(event)
    modifiers = _event_modifiers(event)
    return _is_char_key(code) and not _is_ascii_control(code) and MOD_CONTROL not in modifiers and MOD_ALT not in modifiers


def plain(key: Any) -> KeyBinding:
    return KeyBinding.new(key)


def alt(key: Any) -> KeyBinding:
    return KeyBinding.new(key, {MOD_ALT})


def shift(key: Any) -> KeyBinding:
    return KeyBinding.new(key, {MOD_SHIFT})


def ctrl(key: Any) -> KeyBinding:
    return KeyBinding.new(key, {MOD_CONTROL})


def ctrl_alt(key: Any) -> KeyBinding:
    return KeyBinding.new(key, {MOD_CONTROL, MOD_ALT})


def modifiers_to_string(modifiers: Any) -> str:
    mods = _coerce_modifiers(modifiers)
    result = ""
    if MOD_CONTROL in mods:
        result += CTRL_PREFIX
    if MOD_SHIFT in mods:
        result += SHIFT_PREFIX
    if MOD_ALT in mods:
        result += ALT_PREFIX
    return result


def from_(binding: KeyBinding) -> Span:
    return binding.to_span()


def key_hint_style() -> Dict[str, bool]:
    return {"dim": True}


def has_ctrl_or_alt(mods: Any) -> bool:
    modifiers = _coerce_modifiers(mods)
    return (MOD_CONTROL in modifiers or MOD_ALT in modifiers) and not is_altgr(modifiers)


def is_altgr(mods: Any) -> bool:
    modifiers = _coerce_modifiers(mods)
    return sys.platform.startswith("win") and MOD_ALT in modifiers and MOD_CONTROL in modifiers


def is_press_accepts_press_and_repeat_but_rejects_release() -> None:
    binding = ctrl("k")
    press_event = KeyEvent.new("k", {MOD_CONTROL})
    assert binding.is_press(press_event)
    assert binding.is_press(KeyEvent.new("k", {MOD_CONTROL}, kind="repeat"))
    assert not binding.is_press(KeyEvent.new("k", {MOD_CONTROL}, kind="release"))
    assert not binding.is_press(KeyEvent.new("k"))


def keybinding_list_ext_matches_any_binding() -> None:
    bindings = [plain("a"), ctrl("b")]
    assert is_pressed(bindings, KeyEvent.new("a"))
    assert is_pressed(bindings, KeyEvent.new("b", {MOD_CONTROL}))
    assert not is_pressed(bindings, KeyEvent.new("c"))


def shifted_letter_binding_matches_uppercase_char_events() -> None:
    binding = shift("a")
    assert binding.is_press(KeyEvent.new("a", {MOD_SHIFT}))
    assert binding.is_press(KeyEvent.new("A"))
    assert binding.is_press(KeyEvent.new("A", {MOD_SHIFT}))


def shift_letter_binding_preserves_other_modifiers_with_uppercase_compat() -> None:
    binding = KeyBinding.new("i", {MOD_CONTROL, MOD_SHIFT})
    assert binding.is_press(KeyEvent.new("I", {MOD_CONTROL}))


def shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase() -> None:
    binding = shift("o")
    assert not binding.is_press(KeyEvent.new("o"))
    assert not binding.is_press(KeyEvent.new("P"))


def ctrl_letter_binding_matches_c0_control_char_events() -> None:
    binding = ctrl("p")
    assert binding.is_press(KeyEvent.new("\u0010"))
    assert not binding.is_press(KeyEvent.new("\u0010", {MOD_ALT}))


def ctrl_bindings_match_all_supported_c0_control_char_events() -> None:
    cases = [
        (" ", "\u0000"),
        *[(chr(ord("a") + i), chr(0x01 + i)) for i in range(26)],
        ("4", "\u001c"),
        ("5", "\u001d"),
        ("6", "\u001e"),
        ("7", "\u001f"),
    ]
    for ctrl_char, c0_char in cases:
        assert ctrl(ctrl_char).is_press(KeyEvent.new(c0_char))
        assert not ctrl(ctrl_char).is_press(KeyEvent.new(c0_char, {MOD_ALT}))


def ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete() -> None:
    assert not ctrl("[").is_press(KeyEvent.new("\u001b"))
    assert not ctrl("?").is_press(KeyEvent.new("\u007f"))


def history_search_ctrl_bindings_match_c0_control_char_events() -> None:
    assert ctrl("r").is_press(KeyEvent.new("\u0012"))
    assert ctrl("s").is_press(KeyEvent.new("\u0013"))


def ctrl_alt_sets_both_modifiers() -> None:
    assert ctrl_alt("v").parts() == ("v", frozenset({MOD_CONTROL, MOD_ALT}))


def has_ctrl_or_alt_checks_supported_modifier_combinations() -> None:
    assert not has_ctrl_or_alt(frozenset())
    assert has_ctrl_or_alt({MOD_CONTROL})
    assert has_ctrl_or_alt({MOD_ALT})
    assert has_ctrl_or_alt({MOD_CONTROL, MOD_ALT}) is (not sys.platform.startswith("win"))


def _display_key(key: str) -> str:
    mapping = {
        "Enter": "enter",
        "enter": "enter",
        " ": "space",
        "Up": UP_LABEL,
        "up": UP_LABEL,
        "Down": DOWN_LABEL,
        "down": DOWN_LABEL,
        "Left": LEFT_LABEL,
        "left": LEFT_LABEL,
        "Right": RIGHT_LABEL,
        "right": RIGHT_LABEL,
        "PageUp": "pgup",
        "pageup": "pgup",
        "PageDown": "pgdn",
        "pagedown": "pgdn",
        "Esc": "esc",
        "esc": "esc",
        "Tab": "tab",
        "tab": "tab",
    }
    return mapping.get(key, str(key).lower())


def _coerce_key(key: Any) -> str:
    if isinstance(key, dict):
        key = key.get("code", key.get("key", ""))
    text = str(key)
    if text.startswith("KeyCode::Char("):
        return text
    mapping = {
        "KeyCode::Enter": "Enter",
        "KeyCode::Up": "Up",
        "KeyCode::Down": "Down",
        "KeyCode::Left": "Left",
        "KeyCode::Right": "Right",
        "KeyCode::PageUp": "PageUp",
        "KeyCode::PageDown": "PageDown",
        "KeyCode::Esc": "Esc",
        "KeyCode::Tab": "Tab",
    }
    return mapping.get(text, text)


def _coerce_modifiers(modifiers: Any) -> FrozenSet[str]:
    if modifiers is None:
        return frozenset()
    if isinstance(modifiers, str):
        parts = {modifiers}
    else:
        try:
            parts = set(modifiers)
        except TypeError:
            parts = {modifiers}
    normalized: Set[str] = set()
    for part in parts:
        text = str(part).lower()
        if "control" in text or text == "ctrl":
            normalized.add(MOD_CONTROL)
        elif "shift" in text:
            normalized.add(MOD_SHIFT)
        elif "alt" in text:
            normalized.add(MOD_ALT)
        elif text in {"none", ""}:
            continue
        else:
            normalized.add(text)
    return frozenset(normalized)


def _event_code(event: Any) -> str:
    if isinstance(event, KeyEvent):
        return event.code
    if isinstance(event, dict):
        return _coerce_key(event.get("code", ""))
    return _coerce_key(getattr(event, "code", event))


def _event_modifiers(event: Any) -> FrozenSet[str]:
    if isinstance(event, KeyEvent):
        return event.modifiers
    if isinstance(event, dict):
        return _coerce_modifiers(event.get("modifiers"))
    return _coerce_modifiers(getattr(event, "modifiers", None))


def _event_kind(event: Any) -> str:
    if isinstance(event, KeyEvent):
        return event.kind
    if isinstance(event, dict):
        return str(event.get("kind", "press")).lower()
    return str(getattr(event, "kind", "press")).lower()


def _is_char_key(key: str) -> bool:
    return len(key) == 1


def _is_ascii_control(ch: str) -> bool:
    return len(ch) == 1 and ord(ch) < 0x20 or ch == "\x7f"


__all__ = [
    "ALT_PREFIX",
    "CTRL_PREFIX",
    "KeyBinding",
    "KeyBindingListExt",
    "KeyEvent",
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "RUST_MODULE",
    "DOWN_LABEL",
    "LEFT_LABEL",
    "RIGHT_LABEL",
    "SHIFT_PREFIX",
    "Span",
    "UP_LABEL",
    "alt",
    "c0_control_char_to_ctrl_char",
    "ctrl",
    "ctrl_alt",
    "ctrl_alt_sets_both_modifiers",
    "ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete",
    "ctrl_bindings_match_all_supported_c0_control_char_events",
    "ctrl_letter_binding_matches_c0_control_char_events",
    "from_",
    "has_ctrl_or_alt",
    "has_ctrl_or_alt_checks_supported_modifier_combinations",
    "history_search_ctrl_bindings_match_c0_control_char_events",
    "is_altgr",
    "is_plain_text_key_event",
    "is_press_accepts_press_and_repeat_but_rejects_release",
    "is_pressed",
    "key_hint_style",
    "keybinding_list_ext_matches_any_binding",
    "modifiers_to_string",
    "normalize_key_parts",
    "plain",
    "shift",
    "shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase",
    "shift_letter_binding_preserves_other_modifiers_with_uppercase_compat",
    "shifted_letter_binding_matches_uppercase_char_events",
]



