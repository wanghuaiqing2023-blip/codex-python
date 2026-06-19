"""Semantic port for Rust ``bottom_pane/chat_composer.rs``.

The Rust chat composer is a large bottom-pane input state machine. This Python
module carries the module-owned public data/config boundary and keeps editor,
popup, history, paste-burst, and rendering runtime behavior as explicit
neighboring modules or dependency boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs",
    status="complete",
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


class ChatComposer:
    """Explicit semantic boundary for the full Rust composer state machine."""

    def __init__(self, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> None:
        self.config = ChatComposerConfig.default() if config is None else config
        self._text = ""

    @classmethod
    def new_with_config(cls, *args: Any, config: ChatComposerConfig | None = None, **kwargs: Any) -> "ChatComposer":
        return cls(config=config or ChatComposerConfig.default())

    def handle_key_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event")

    def render(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.render")


def plan_mode_nudge_line() -> list[str]:
    return ["Create a plan?", "shift+tab use Plan mode", "Esc dismiss"]


__all__ = [
    "ChatComposer",
    "ChatComposerConfig",
    "ComposerDraftSnapshot",
    "FOOTER_SPACING_HEIGHT",
    "InputResult",
    "LARGE_PASTE_CHAR_THRESHOLD",
    "MAX_USER_INPUT_TEXT_CHARS",
    "QueuedInputAction",
    "RUST_MODULE",
    "plan_mode_nudge_line",
    "user_input_too_large_message",
]
