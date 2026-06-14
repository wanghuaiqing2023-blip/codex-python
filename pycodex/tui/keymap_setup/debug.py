"""Keymap debug inspector for ``codex-tui::keymap_setup::debug``.

Rust source: ``codex/codex-rs/tui/src/keymap_setup/debug.rs``.

Python models the bottom-pane view as semantic text lines.  The surrounding
runtime keymap/action catalog is accepted through duck-typed injected objects;
when no matcher is available the report correctly shows no assigned actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, List, Optional, Union
import textwrap
import time

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="keymap_setup::debug", source="codex/codex-rs/tui/src/keymap_setup/debug.rs")

MISSING_KEY_HINT_DELAY = 3.0
SHORT_MISSING_KEY_HINT = "Tip: Codex can only inspect keys your terminal sends."
DELAYED_MISSING_KEY_HINT = "Still waiting? If nothing changes when you press a key, your terminal is not sending that key to Codex. Only received keys can be assigned as shortcuts."


@dataclass(frozen=True)
class SemanticKeyBinding:
    code: str
    modifiers: FrozenSet[str] = frozenset()

    @classmethod
    def from_event(cls, event: Any) -> "SemanticKeyBinding":
        return cls(_event_code(event), _event_modifiers(event))

    def display_label(self) -> str:
        parts: List[str] = []
        if "control" in self.modifiers:
            parts.append("ctrl")
        if "alt" in self.modifiers:
            parts.append("alt")
        if "shift" in self.modifiers:
            parts.append("shift")
        parts.append(_display_code(self.code))
        return "+".join(parts)


@dataclass(frozen=True)
class KeymapDebugActionMatch:
    context: str
    action: str
    label: str
    description: str
    source: str = "default"

    @classmethod
    def from_any(cls, value: Any) -> "KeymapDebugActionMatch":
        source = _get(value, "source", "default")
        return cls(
            context=str(_get(value, "context", "global")),
            action=str(_get(value, "action", "unknown")),
            label=str(_get(value, "label", _get(value, "action", "unknown"))),
            description=str(_get(value, "description", "")),
            source=_source_label(source),
        )


@dataclass
class KeymapDebugReport:
    detected: SemanticKeyBinding
    config_key: Union[str, Exception]
    raw_event: str
    matches: List[KeymapDebugActionMatch] = field(default_factory=list)


@dataclass
class KeymapDebugView:
    runtime_keymap: Any
    keymap_config: Any
    opened_at: float = field(default_factory=time.monotonic)
    last_report: Optional[KeymapDebugReport] = None
    complete: bool = False
    clock: Callable[[], float] = time.monotonic

    def lines(self, width: int) -> List[str]:
        return self.lines_at(width, self.clock())

    def lines_at(self, width: int, now: float) -> List[str]:
        wrap_width = max(1, int(width))
        lines = [
            "Keypress Inspector",
            "Press any key to see what Codex receives. Esc is inspected; Ctrl+C closes.",
        ]
        hint = DELAYED_MISSING_KEY_HINT if self.should_show_delayed_hint(now) else SHORT_MISSING_KEY_HINT
        push_wrapped_dim(lines, hint, wrap_width, "", "")

        if self.last_report is None:
            lines.append("")
            lines.append("Waiting for a keypress...")
            return lines

        report = self.last_report
        lines.append("")
        lines.append(f"Detected: {report.detected.display_label()}")
        if isinstance(report.config_key, Exception):
            push_wrapped_dim(lines, f"unsupported - {report.config_key}", wrap_width, "Config key: ", "            ")
        else:
            lines.append(f"Config key: {report.config_key}")
        push_wrapped_dim(lines, report.raw_event, wrap_width, "Raw event: ", "           ")
        lines.append("")
        lines.append("Assigned actions:")
        if not report.matches:
            lines.append("  none")
        else:
            for matched_action in report.matches:
                action = (
                    f"{matched_action.context}.{matched_action.action} "
                    f"({matched_action.label}) - {matched_action.description} "
                    f"[{matched_action.source}]"
                )
                push_wrapped_dim(lines, action, wrap_width, "  - ", "    ")
        return lines

    def should_show_delayed_hint(self, now: float) -> bool:
        return self.last_report is None and now - self.opened_at >= MISSING_KEY_HINT_DELAY

    def show_delayed_hint_for_test(self) -> None:
        self.opened_at = self.clock() - MISSING_KEY_HINT_DELAY

    def render(self, area: Any = None, buf: Any = None) -> List[str]:
        width = getattr(area, "width", area if isinstance(area, int) else 80)
        lines = self.lines(width)
        if buf is not None and hasattr(buf, "draw"):
            buf.draw(lines, area)
        return lines

    def desired_height(self, width: int) -> int:
        return len(self.lines(width))

    def handle_key_event(self, key_event: Any) -> None:
        if _event_kind(key_event) == "release":
            return
        self.last_report = KeymapDebugReport(
            detected=SemanticKeyBinding.from_event(key_event),
            config_key=_key_event_to_config_key_spec(key_event),
            raw_event=key_event_debug_summary(key_event),
            matches=matching_actions_for_key_event(self.runtime_keymap, self.keymap_config, key_event),
        )

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.complete = True
        return "handled"

    def prefer_esc_to_handle_key_event(self) -> bool:
        return True

    def next_frame_delay(self) -> Optional[float]:
        if self.last_report is not None:
            return None
        remaining = self.opened_at + MISSING_KEY_HINT_DELAY - self.clock()
        return remaining if remaining > 0 else None


def build_keymap_debug_view(runtime_keymap: Any, keymap_config: Any, *, clock: Callable[[], float] = time.monotonic) -> KeymapDebugView:
    return KeymapDebugView(runtime_keymap=runtime_keymap, keymap_config=keymap_config, opened_at=clock(), clock=clock)


def render(view: KeymapDebugView, area: Any = None, buf: Any = None) -> list[str]:
    return view.render(area, buf)


def desired_height(view: KeymapDebugView, width: int) -> int:
    return view.desired_height(width)


def handle_key_event(view: KeymapDebugView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: KeymapDebugView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: KeymapDebugView) -> str:
    return view.on_ctrl_c()


def prefer_esc_to_handle_key_event(view: KeymapDebugView) -> bool:
    return view.prefer_esc_to_handle_key_event()


def next_frame_delay(view: KeymapDebugView) -> float | None:
    return view.next_frame_delay()


def push_wrapped_dim(lines: list[str], text: str, wrap_width: int, initial_indent: str, subsequent_indent: str) -> None:
    wrapped = textwrap.wrap(
        str(text),
        width=max(1, int(wrap_width)),
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        replace_whitespace=False,
        drop_whitespace=True,
    )
    lines.extend(wrapped or [initial_indent.rstrip()])


def key_event_debug_summary(key_event: Any) -> str:
    return f"code={_event_code_debug(key_event)}, modifiers={key_modifiers_debug_label(_event_modifiers(key_event))}, kind={_event_kind_debug(key_event)}"


def key_modifiers_debug_label(modifiers: Any) -> str:
    mods = _normalize_modifiers(modifiers)
    if not mods:
        return "none"
    parts = []
    for rust_name, py_name in (("ctrl", "control"), ("alt", "alt"), ("shift", "shift")):
        if py_name in mods:
            parts.append(rust_name)
    other = sorted(mod for mod in mods if mod not in {"control", "alt", "shift"})
    parts.extend(other)
    return "|".join(parts)


def matching_actions_for_key_event(runtime_keymap: Any, keymap_config: Any, key_event: Any) -> List[KeymapDebugActionMatch]:
    matcher = getattr(runtime_keymap, "matching_actions_for_key_event", None)
    if callable(matcher):
        return [KeymapDebugActionMatch.from_any(value) for value in matcher(keymap_config, key_event)]
    matcher = getattr(keymap_config, "matching_actions_for_key_event", None)
    if callable(matcher):
        return [KeymapDebugActionMatch.from_any(value) for value in matcher(runtime_keymap, key_event)]
    raw_matches = _get(runtime_keymap, "matches", None)
    if raw_matches is None:
        raw_matches = _get(keymap_config, "matches", [])
    if isinstance(raw_matches, dict):
        key = _key_event_to_config_key_spec(key_event)
        raw_matches = raw_matches.get(key, [])
    return [KeymapDebugActionMatch.from_any(value) for value in (raw_matches or [])]


def _key_event_to_config_key_spec(key_event: Any) -> Union[str, Exception]:
    try:
        binding = SemanticKeyBinding.from_event(key_event)
        return binding.display_label()
    except Exception as exc:  # pragma: no cover - defensive semantic boundary
        return exc


def _event_code(event: Any) -> str:
    if isinstance(event, dict):
        raw = event.get("code", event.get("key", ""))
    else:
        raw = getattr(event, "code", event)
    text = str(raw)
    lowered = text.lower()
    mapping = {"escape": "esc", "return": "enter", "uparrow": "up", "downarrow": "down"}
    return mapping.get(lowered, lowered)


def _display_code(code: str) -> str:
    mapping = {"esc": "esc", "enter": "enter", "up": "up", "down": "down"}
    return mapping.get(code.lower(), code.lower())


def _event_modifiers(event: Any) -> FrozenSet[str]:
    if isinstance(event, dict):
        raw = event.get("modifiers", ())
    else:
        raw = getattr(event, "modifiers", ())
    return _normalize_modifiers(raw)


def _normalize_modifiers(modifiers: Any) -> frozenset[str]:
    if modifiers is None:
        return frozenset()
    if isinstance(modifiers, str):
        items = {modifiers}
    else:
        try:
            items = set(modifiers)
        except TypeError:
            items = {modifiers}
    normalized = set()
    for item in items:
        text = str(item).lower()
        if text in {"ctrl", "control"} or "control" in text:
            normalized.add("control")
        elif text == "alt" or "alt" in text:
            normalized.add("alt")
        elif text == "shift" or "shift" in text:
            normalized.add("shift")
        elif text:
            normalized.add(text)
    return frozenset(normalized)


def _event_kind(event: Any) -> str:
    if isinstance(event, dict):
        raw = event.get("kind", "press")
    else:
        raw = getattr(event, "kind", "press")
    return str(raw).lower()


def _event_code_debug(event: Any) -> str:
    return repr(_event_code(event))


def _event_kind_debug(event: Any) -> str:
    kind = _event_kind(event)
    return kind[:1].upper() + kind[1:]


def _source_label(source: Any) -> str:
    label = getattr(source, "label", None)
    if callable(label):
        return str(label())
    if isinstance(source, dict) and "label" in source:
        return str(source["label"])
    return str(source)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


__all__ = [
    "DELAYED_MISSING_KEY_HINT",
    "KeymapDebugActionMatch",
    "KeymapDebugReport",
    "KeymapDebugView",
    "MISSING_KEY_HINT_DELAY",
    "RUST_MODULE",
    "SHORT_MISSING_KEY_HINT",
    "SemanticKeyBinding",
    "build_keymap_debug_view",
    "desired_height",
    "handle_key_event",
    "is_complete",
    "key_event_debug_summary",
    "key_modifiers_debug_label",
    "matching_actions_for_key_event",
    "next_frame_delay",
    "on_ctrl_c",
    "prefer_esc_to_handle_key_event",
    "push_wrapped_dim",
    "render",
]

