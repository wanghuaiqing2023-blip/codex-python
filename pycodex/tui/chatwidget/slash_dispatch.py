"""Slash-command dispatch helpers for Rust ``chatwidget::slash_dispatch``.

The full Rust module dispatches many commands through ``ChatWidget``.  Python
keeps the module-owned pure contracts here: dispatch-source tagging, prepared
argument payloads, side/review guard messages, queued-drain decisions, and
inline-argument text-element remapping.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, List, Optional, Set, Union

from .._porting import RustTuiModule
from ..slash_command import SlashCommand

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::slash_dispatch",
    source="codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs",
    status="complete",
)

SIDE_STARTING_CONTEXT_LABEL = "Side starting..."
SIDE_SLASH_COMMAND_UNAVAILABLE_HINT = "Press Ctrl+C to return to the main thread first."
GOAL_USAGE = "Usage: /goal <objective>"
GOAL_USAGE_HINT = "Example: /goal improve benchmark coverage"
RAW_USAGE = "Usage: /raw [on|off]"


class SlashCommandDispatchSource(Enum):
    LIVE = "live"
    QUEUED = "queued"


class QueueDrain(Enum):
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int


@dataclass(frozen=True)
class TextElement:
    byte_range: ByteRange
    payload: Any = None

    def map_range(self, new_range: ByteRange) -> "TextElement":
        return replace(self, byte_range=new_range)


@dataclass(frozen=True)
class PreparedSlashCommandArgs:
    args: str
    text_elements: tuple[Any, ...] = ()
    local_images: tuple[Any, ...] = ()
    remote_image_urls: tuple[str, ...] = ()
    mention_bindings: tuple[Any, ...] = ()
    source: SlashCommandDispatchSource = SlashCommandDispatchSource.LIVE


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    error_message: Optional[str] = None
    drain_pending_submission: bool = False


@dataclass(frozen=True)
class PreparedUserMessage:
    text: str
    local_images: tuple[Any, ...]
    remote_image_urls: tuple[str, ...]
    text_elements: tuple[Any, ...]
    mention_bindings: tuple[Any, ...]


_QUEUED_CONTINUE_COMMANDS: Set[SlashCommand] = {
    SlashCommand.IDE,
    SlashCommand.STATUS,
    SlashCommand.DEBUG_CONFIG,
    SlashCommand.PS,
    SlashCommand.STOP,
    SlashCommand.MEMORY_DROP,
    SlashCommand.MEMORY_UPDATE,
    SlashCommand.MCP,
    SlashCommand.APPS,
    SlashCommand.PLUGINS,
    SlashCommand.ROLLOUT,
    SlashCommand.COPY,
    SlashCommand.RAW,
    SlashCommand.VIM,
    SlashCommand.DIFF,
    SlashCommand.RENAME,
    SlashCommand.TEST_APPROVAL,
}


def side_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable in side conversations. {SIDE_SLASH_COMMAND_UNAVAILABLE_HINT}"


def before_session_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable before the session starts."


def review_side_unavailable_message(cmd: Union[SlashCommand, str]) -> str:
    command = cmd.command() if isinstance(cmd, SlashCommand) else str(cmd).lstrip("/")
    return f"'/{command}' is unavailable while code review is running."


def ensure_slash_command_allowed_in_side_conversation(active_side_conversation: bool, cmd: SlashCommand) -> GuardResult:
    if not active_side_conversation or cmd.available_in_side_conversation():
        return GuardResult(True)
    return GuardResult(False, side_unavailable_message(cmd), True)


def ensure_side_command_allowed_outside_review(review_mode: bool, cmd: SlashCommand) -> GuardResult:
    if cmd not in {SlashCommand.SIDE, SlashCommand.BTW} or not review_mode:
        return GuardResult(True)
    return GuardResult(False, review_side_unavailable_message(cmd), True)


def queued_command_drain_result(
    cmd: SlashCommand,
    *,
    user_turn_pending_or_running: bool = False,
    no_modal_or_popup_active: bool = True,
) -> QueueDrain:
    if user_turn_pending_or_running or not no_modal_or_popup_active:
        return QueueDrain.STOP
    return QueueDrain.CONTINUE if cmd in _QUEUED_CONTINUE_COMMANDS else QueueDrain.STOP


def slash_command_args_elements(
    rest: str,
    rest_offset: int,
    text_elements: Iterable[Any],
) -> List[Any]:
    if not rest:
        return []
    out: List[Any] = []
    for elem in text_elements:
        byte_range = _byte_range(elem)
        if byte_range is None or byte_range.end <= rest_offset:
            continue
        start = max(0, byte_range.start - rest_offset)
        end = byte_range.end - rest_offset
        if start >= len(rest):
            continue
        end = min(end, len(rest))
        if start < end:
            out.append(_map_element_range(elem, ByteRange(start, end)))
    return out


def prepared_inline_user_message(prepared: PreparedSlashCommandArgs) -> PreparedUserMessage:
    return PreparedUserMessage(
        text=prepared.args,
        local_images=tuple(prepared.local_images),
        remote_image_urls=tuple(prepared.remote_image_urls),
        text_elements=tuple(prepared.text_elements),
        mention_bindings=tuple(prepared.mention_bindings),
    )


def raw_output_mode_arg(trimmed: str) -> Optional[bool]:
    value = trimmed.strip().lower()
    if value == "on":
        return True
    if value == "off":
        return False
    return None


def mcp_detail_arg(trimmed: str) -> Optional[str]:
    return "full" if trimmed.strip().lower() == "verbose" else None


def keymap_arg_action(trimmed: str) -> Optional[str]:
    value = trimmed.strip().lower()
    if value == "":
        return "picker"
    if value == "debug":
        return "debug"
    return None


def pets_disable_arg(trimmed: str) -> bool:
    return trimmed.strip().lower() in {"disable", "disabled", "hide", "hidden", "off", "none"}


def _byte_range(elem: Any) -> Optional[ByteRange]:
    raw = getattr(elem, "byte_range", None)
    if raw is None and isinstance(elem, dict):
        raw = elem.get("byte_range")
    if raw is None:
        return None
    if isinstance(raw, ByteRange):
        return raw
    if isinstance(raw, range):
        return ByteRange(raw.start, raw.stop)
    if isinstance(raw, tuple) and len(raw) == 2:
        return ByteRange(int(raw[0]), int(raw[1]))
    start = getattr(raw, "start", None)
    end = getattr(raw, "end", None)
    if start is None and isinstance(raw, dict):
        start = raw.get("start")
        end = raw.get("end")
    if start is None or end is None:
        return None
    return ByteRange(int(start), int(end))


def _map_element_range(elem: Any, byte_range: ByteRange) -> Any:
    mapper = getattr(elem, "map_range", None)
    if callable(mapper):
        try:
            return mapper(byte_range)
        except TypeError:
            return mapper(lambda _old: byte_range)
    if isinstance(elem, TextElement):
        return elem.map_range(byte_range)
    if isinstance(elem, dict):
        copy = dict(elem)
        copy["byte_range"] = byte_range
        return copy
    try:
        return replace(elem, byte_range=byte_range)
    except Exception:
        return TextElement(byte_range, elem)


__all__ = [
    "ByteRange",
    "GOAL_USAGE",
    "GOAL_USAGE_HINT",
    "GuardResult",
    "PreparedSlashCommandArgs",
    "PreparedUserMessage",
    "QueueDrain",
    "RAW_USAGE",
    "RUST_MODULE",
    "SIDE_SLASH_COMMAND_UNAVAILABLE_HINT",
    "SIDE_STARTING_CONTEXT_LABEL",
    "SlashCommandDispatchSource",
    "TextElement",
    "before_session_unavailable_message",
    "ensure_side_command_allowed_outside_review",
    "ensure_slash_command_allowed_in_side_conversation",
    "keymap_arg_action",
    "mcp_detail_arg",
    "pets_disable_arg",
    "prepared_inline_user_message",
    "queued_command_drain_result",
    "raw_output_mode_arg",
    "review_side_unavailable_message",
    "side_unavailable_message",
    "slash_command_args_elements",
]
