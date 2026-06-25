"""Semantic slice for Rust ``bottom_pane/chat_composer.rs``.

The full Rust chat composer is a large bottom-pane input state machine. This
module ports the independently useful public data/config boundary first and
keeps editor, popup, history, paste-burst, and rendering behavior as explicit
follow-up slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, MutableSequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
)

LARGE_PASTE_CHAR_THRESHOLD = 1000
MAX_USER_INPUT_TEXT_CHARS = 512_000
FOOTER_SPACING_HEIGHT = 0


def user_input_too_large_message(actual_chars: int) -> str:
    return (
        f"Message exceeds the maximum length of {MAX_USER_INPUT_TEXT_CHARS} "
        f"characters ({int(actual_chars)} provided)."
    )


class QueuedInputAction(Enum):
    Plain = "plain"
    ParseSlash = "parse_slash"
    RunShell = "run_shell"


@dataclass(frozen=True)
class KeyEvent:
    code: str
    modifiers: tuple[str, ...] = ()
    kind: str = "press"
    char: str | None = None

    @classmethod
    def char_event(
        cls,
        char: str,
        *,
        modifiers: tuple[str, ...] | list[str] = (),
        kind: str = "press",
    ) -> "KeyEvent":
        return cls(code="char", modifiers=tuple(modifiers), kind=kind, char=char)

    @classmethod
    def key(
        cls,
        code: str,
        *,
        modifiers: tuple[str, ...] | list[str] = (),
        kind: str = "press",
    ) -> "KeyEvent":
        return cls(code=code, modifiers=tuple(modifiers), kind=kind)

    def binding_key(self) -> tuple[str, tuple[str, ...], str | None]:
        return (self.code.lower(), tuple(sorted(m.lower() for m in self.modifiers)), self.char)


@dataclass(frozen=True)
class InputResult:
    kind: str
    text: str | None = None
    text_elements: list[Any] = field(default_factory=list)
    action: QueuedInputAction | None = None
    command: Any = None
    args: str | None = None

    @classmethod
    def Submitted(cls, text: str, text_elements: list[Any] | None = None) -> "InputResult":
        return cls("Submitted", text=text, text_elements=list(text_elements or []))

    @classmethod
    def Queued(
        cls,
        text: str,
        text_elements: list[Any] | None = None,
        action: QueuedInputAction = QueuedInputAction.Plain,
    ) -> "InputResult":
        return cls("Queued", text=text, text_elements=list(text_elements or []), action=QueuedInputAction(action))

    @classmethod
    def Command(cls, command: Any) -> "InputResult":
        return cls("Command", command=command)

    @classmethod
    def ServiceTierCommand(cls, command: Any) -> "InputResult":
        return cls("ServiceTierCommand", command=command)

    @classmethod
    def CommandWithArgs(cls, command: Any, args: str, text_elements: list[Any] | None = None) -> "InputResult":
        return cls("CommandWithArgs", command=command, args=args, text_elements=list(text_elements or []))

    @classmethod
    def None_(cls) -> "InputResult":
        return cls("None")


@dataclass(frozen=True)
class ChatComposerConfig:
    popups_enabled: bool = True
    slash_commands_enabled: bool = True
    image_paste_enabled: bool = True

    @classmethod
    def default(cls) -> "ChatComposerConfig":
        return cls()

    @classmethod
    def plain_text(cls) -> "ChatComposerConfig":
        return cls(popups_enabled=False, slash_commands_enabled=False, image_paste_enabled=False)


@dataclass(frozen=True)
class ComposerDraftSnapshot:
    text: str
    text_elements: list[Any] = field(default_factory=list)
    local_images: list[Any] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    mention_bindings: list[Any] = field(default_factory=list)
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ChatComposerRenderSnapshot:
    area: Any = None
    mask_char: str | None = None
    textarea_right_reserve: int = 0
    active_popup: str = "none"
    prompt: str = ">"
    text: str = ""
    placeholder: str | None = None
    remote_image_urls: tuple[str, ...] = ()
    footer: tuple[str, ...] = ()
    input_enabled: bool = True


class ChatComposer:
    """Semantic entry boundary for Rust's full composer state machine."""

    def __init__(self, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> None:
        self.config = ChatComposerConfig.default() if config is None else config
        self.input_enabled = bool(kwargs.pop("input_enabled", True))
        self.input_disabled_placeholder = kwargs.pop("input_disabled_placeholder", None)
        self.placeholder_text = kwargs.pop("placeholder_text", "Ask Codex to do anything")
        self.is_bash_mode = bool(kwargs.pop("is_bash_mode", False))
        self.is_task_running = bool(kwargs.pop("is_task_running", False))
        self.history_search_active = bool(kwargs.pop("history_search_active", False))
        self.active_popup = str(kwargs.pop("active_popup", "none")).lower()
        self.history_search_previous_keys = {
            _binding_key(item)
            for item in kwargs.pop(
                "history_search_previous_keys",
                [KeyEvent.char_event("r", modifiers=("control",))],
            )
        }
        self.remote_image_urls = list(kwargs.pop("remote_image_urls", []))
        self.footer = list(kwargs.pop("footer", []))
        self.handlers: dict[str, Callable[[KeyEvent], tuple[InputResult, bool]]] = dict(
            kwargs.pop("handlers", {})
        )
        self.dispatch_log: list[str] = []
        self.sync_count = 0
        self.reset_vim_count = 0
        self.render_log: list[tuple[str, Any, str | None, int]] = []
        self._text = str(kwargs.pop("text", ""))

    @classmethod
    def new_with_config(cls, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> "ChatComposer":
        return cls(*args, config=config or ChatComposerConfig.default(), **kwargs)

    def handle_key_event(self, key_event: KeyEvent | dict[str, Any] | str, **kwargs: Any) -> tuple[InputResult, bool]:
        event = _coerce_key_event(key_event, **kwargs)
        if not self.input_enabled:
            return (InputResult.None_(), False)
        if event.kind.lower() == "release":
            return (InputResult.None_(), False)
        if self.history_search_active:
            return self._dispatch("history_search", event)
        if self.is_history_search_key(event):
            return self.begin_history_search()

        target = {
            "command": "slash_popup",
            "file": "file_popup",
            "skill": "skill_popup",
            "mentionv2": "mentions_v2_popup",
            "mention_v2": "mentions_v2_popup",
        }.get(self.active_popup, "without_popup")
        result = self._dispatch(target, event)
        self.reset_vim_mode_after_successful_dispatch(result[0])
        self.sync_popups()
        return result

    def is_history_search_key(self, key_event: KeyEvent) -> bool:
        return key_event.binding_key() in self.history_search_previous_keys

    def begin_history_search(self) -> tuple[InputResult, bool]:
        self.history_search_active = True
        self.dispatch_log.append("begin_history_search")
        return (InputResult.None_(), True)

    def reset_vim_mode_after_successful_dispatch(self, result: InputResult) -> None:
        if result.kind != "None":
            self.reset_vim_count += 1

    def sync_popups(self) -> None:
        self.sync_count += 1

    def render(self, area: Any = None, buf: MutableSequence[Any] | None = None) -> ChatComposerRenderSnapshot:
        return self.render_with_mask(area, buf, None)

    def render_with_mask(
        self,
        area: Any = None,
        buf: MutableSequence[Any] | None = None,
        mask_char: str | None = None,
    ) -> ChatComposerRenderSnapshot:
        return self.render_with_mask_and_textarea_right_reserve(area, buf, mask_char, 0)

    def render_with_mask_and_textarea_right_reserve(
        self,
        area: Any = None,
        buf: MutableSequence[Any] | None = None,
        mask_char: str | None = None,
        textarea_right_reserve: int = 0,
    ) -> ChatComposerRenderSnapshot:
        self.render_log.append(("render_with_mask_and_textarea_right_reserve", area, mask_char, int(textarea_right_reserve)))
        visible_text = self._text if mask_char is None else mask_char * len(self._text)
        placeholder = None
        if not self.input_enabled:
            placeholder = self.input_disabled_placeholder or "Input disabled."
        elif not self._text and not self.is_bash_mode:
            placeholder = self.placeholder_text
        snapshot = ChatComposerRenderSnapshot(
            area=area,
            mask_char=mask_char,
            textarea_right_reserve=int(textarea_right_reserve),
            active_popup=self.active_popup,
            prompt="!" if self.is_bash_mode else ">",
            text=visible_text,
            placeholder=placeholder,
            remote_image_urls=tuple(self.remote_image_urls),
            footer=tuple(self.footer),
            input_enabled=self.input_enabled,
        )
        if buf is not None and hasattr(buf, "append"):
            buf.append(snapshot)
        return snapshot

    def _dispatch(self, target: str, key_event: KeyEvent) -> tuple[InputResult, bool]:
        self.dispatch_log.append(target)
        handler = self.handlers.get(target)
        if handler is not None:
            return handler(key_event)
        if target == "without_popup":
            if key_event.code.lower() == "char" and key_event.char is not None:
                self._text += key_event.char
                return (InputResult.None_(), True)
            if key_event.code.lower() == "enter" and self._text.strip():
                text = self._text
                self._text = ""
                return (InputResult.Submitted(text), True)
        return (InputResult.None_(), False)


def _binding_key(item: KeyEvent | dict[str, Any] | str) -> tuple[str, tuple[str, ...], str | None]:
    return _coerce_key_event(item).binding_key()


def _coerce_key_event(event: KeyEvent | dict[str, Any] | str, **kwargs: Any) -> KeyEvent:
    if isinstance(event, KeyEvent):
        return event
    if isinstance(event, str):
        if len(event) == 1:
            return KeyEvent.char_event(event, **kwargs)
        return KeyEvent.key(event, **kwargs)
    if isinstance(event, dict):
        data = dict(event)
        data.update(kwargs)
        code = str(data.pop("code", "char" if "char" in data else ""))
        char = data.pop("char", None)
        modifiers = data.pop("modifiers", ())
        kind = str(data.pop("kind", "press"))
        return KeyEvent(code=code, char=char, modifiers=tuple(modifiers), kind=kind)
    raise TypeError(f"unsupported key event: {event!r}")


def plan_mode_nudge_line() -> list[str]:
    return ["Create a plan?", "shift+tab use Plan mode", "Esc dismiss"]


__all__ = [
    "ChatComposer",
    "ChatComposerConfig",
    "ChatComposerRenderSnapshot",
    "ComposerDraftSnapshot",
    "FOOTER_SPACING_HEIGHT",
    "InputResult",
    "KeyEvent",
    "LARGE_PASTE_CHAR_THRESHOLD",
    "MAX_USER_INPUT_TEXT_CHARS",
    "QueuedInputAction",
    "RUST_MODULE",
    "plan_mode_nudge_line",
    "user_input_too_large_message",
]
