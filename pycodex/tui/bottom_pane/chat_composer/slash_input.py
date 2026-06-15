"""Behavior port for Rust ``codex-tui::bottom_pane::chat_composer::slash_input``.

The Rust module mixes small slash-input parsing helpers with larger
``ChatComposer`` popup key handling.  This Python module ports the local,
independently measurable slash-input behavior and keeps full composer lifecycle
entry points as explicit not-ported boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from pycodex.protocol.user_input import ByteRange, TextElement

from ..._porting import RustTuiModule
from ..prompt_args import parse_slash_name
from ..slash_commands import (
    BuiltinCommandFlags,
    ServiceTierCommand,
    SlashCommandItem,
    find_slash_command,
    has_slash_command_prefix,
)
from ...slash_command import SlashCommand

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::slash_input",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/slash_input.rs",
    status="complete",
)


class SlashValidation(Enum):
    """Rust ``SlashValidation`` variants."""

    IMMEDIATE = "Immediate"
    DEFERRED = "Deferred"


@dataclass(frozen=True)
class SubmissionValidation:
    """Rust ``SubmissionValidation`` with payload support for UnknownCommand."""

    kind: str
    command: Optional[str] = None

    @classmethod
    def valid(cls) -> "SubmissionValidation":
        return cls("Valid")

    @classmethod
    def unknown_command(cls, command: str) -> "SubmissionValidation":
        return cls("UnknownCommand", command)

    @property
    def is_valid(self) -> bool:
        return self.kind == "Valid"


SubmissionValidation.VALID = SubmissionValidation.valid()  # type: ignore[attr-defined]


class QueuedInputAction(Enum):
    """Rust ``QueuedInputAction`` variants used by this module."""

    PLAIN = "Plain"
    RUN_SHELL = "RunShell"
    PARSE_SLASH = "ParseSlash"


@dataclass(frozen=True)
class InlineCommand:
    """Rust ``InlineCommand`` semantic payload."""

    command: SlashCommandItem
    rest: str
    rest_offset: int


@dataclass(frozen=True)
class CommandPopupSnapshot:
    """Small semantic boundary for Rust ``CommandPopup`` construction."""

    flags: BuiltinCommandFlags
    service_tier_commands: Tuple[ServiceTierCommand, ...] = ()
    filter_text: str = ""


@dataclass(frozen=True)
class SlashCompletionResult:
    """Semantic result of Rust's draft-tail-preserving slash completion."""

    text: str
    cursor: int
    ranges_to_unmark: Tuple[Tuple[int, int], ...] = ()


@dataclass(frozen=True)
class SlashElementSyncResult:
    """Semantic result of Rust ``sync_slash_command_elements``."""

    desired_range: Optional[Tuple[int, int]]
    add_range: Optional[Tuple[int, int]]
    stale_ranges: Tuple[Tuple[int, int], ...] = ()


@dataclass
class SlashInput:
    """Rust ``SlashInput`` local behavior."""

    enabled: bool
    is_bash_mode: bool
    command_flags: BuiltinCommandFlags = field(default_factory=BuiltinCommandFlags)
    service_tier_commands: Tuple[ServiceTierCommand, ...] = ()

    @classmethod
    def new(
        cls,
        enabled: bool,
        is_bash_mode: bool,
        command_flags: Optional[BuiltinCommandFlags] = None,
        service_tier_commands: Iterable[ServiceTierCommand] = (),
    ) -> "SlashInput":
        return cls(
            enabled=enabled,
            is_bash_mode=is_bash_mode,
            command_flags=command_flags or BuiltinCommandFlags(),
            service_tier_commands=tuple(service_tier_commands),
        )

    def validate_submission(self, text: str, input_starts_with_space: bool) -> SubmissionValidation:
        if not self.enabled:
            return SubmissionValidation.VALID
        parsed = parse_slash_name(text)
        if parsed is None:
            return SubmissionValidation.VALID
        name, _rest, _rest_offset = parsed
        if input_starts_with_space or "/" in name:
            return SubmissionValidation.VALID
        if self.command(name) is not None:
            return SubmissionValidation.VALID
        return SubmissionValidation.unknown_command(name)

    def bare_command(self, text: str) -> Optional[SlashCommandItem]:
        if not self.enabled or self.is_bash_mode:
            return None
        first_line = text.splitlines()[0] if text.splitlines() else ""
        parsed_first = parse_slash_name(first_line)
        if parsed_first is None:
            return None
        name, rest, _rest_offset = parsed_first
        if rest:
            return None
        command = self.command(name)
        if command is None:
            return None
        return command

    def inline_command(self, text: str) -> Optional[InlineCommand]:
        if not self.enabled or self.is_bash_mode or text.startswith(" "):
            return None
        parsed = parse_slash_name(text)
        if parsed is None:
            return None
        name, rest, rest_offset = parsed
        if not rest or "/" in name:
            return None
        command = self.command(name)
        if command is None or not command.supports_inline_args():
            return None
        return InlineCommand(command=command, rest=rest, rest_offset=rest_offset)

    def should_parse_on_dequeue(self, text: str) -> bool:
        return self.enabled and not text.startswith(" ") and text.strip().startswith("/")

    def command_element_range(self, first_line: str, cursor: int) -> Optional[Tuple[int, int]]:
        if self.is_bash_mode:
            return None
        parsed = parse_slash_name(first_line)
        if parsed is None:
            return None
        name, _rest, _rest_offset = parsed
        if "/" in name:
            return None
        element_end = 1 + _utf8_len(name)
        first_line_len = _utf8_len(first_line)
        if cursor <= first_line_len and 1 <= cursor < element_end:
            return None
        tail = _byte_slice(first_line, element_end, first_line_len)
        has_space_after = bool(tail) and tail[0].isspace()
        if not has_space_after:
            return None
        if self.command(name) is None:
            return None
        return (0, element_end)

    def is_editing_command_name(self, first_line: str, cursor: int) -> bool:
        under_cursor = command_under_cursor(first_line, cursor)
        if under_cursor is None:
            return False
        name, rest = under_cursor
        if not self.enabled:
            return False
        if not name:
            return rest == ""
        return has_slash_command_prefix(name, self.command_flags, self.service_tier_commands)

    def command_popup(self, filter_text: str) -> CommandPopupSnapshot:
        return CommandPopupSnapshot(
            flags=BuiltinCommandFlags(
                collaboration_modes_enabled=self.command_flags.collaboration_modes_enabled,
                connectors_enabled=self.command_flags.connectors_enabled,
                plugins_command_enabled=self.command_flags.plugins_command_enabled,
                service_tier_commands_enabled=self.command_flags.service_tier_commands_enabled,
                goal_command_enabled=self.command_flags.goal_command_enabled,
                personality_command_enabled=self.command_flags.personality_command_enabled,
                realtime_conversation_enabled=self.command_flags.realtime_conversation_enabled,
                audio_device_selection_enabled=self.command_flags.audio_device_selection_enabled,
                allow_elevate_sandbox=self.command_flags.allow_elevate_sandbox,
                side_conversation_active=self.command_flags.side_conversation_active,
            ),
            service_tier_commands=tuple(self.service_tier_commands),
            filter_text=filter_text,
        )

    def command(self, name: str) -> Optional[SlashCommandItem]:
        return find_slash_command(name, self.command_flags, self.service_tier_commands)


def queued_input_action(prepared_text: str, defer_slash_validation: bool) -> QueuedInputAction:
    if defer_slash_validation and prepared_text.startswith("/"):
        return QueuedInputAction.PARSE_SLASH
    if prepared_text.startswith("!"):
        return QueuedInputAction.RUN_SHELL
    return QueuedInputAction.PLAIN


def selected_command_dispatches_immediately_on_tab(command: Any) -> bool:
    return _command_payload(command) is SlashCommand.SKILLS


def selected_command_completion(first_line: str, command: Any) -> Optional[str]:
    selected_command_text = f"/{_command_name(command)}"
    if first_line.lstrip().startswith(selected_command_text):
        return None
    return f"{selected_command_text} "


def prepared_args(prepared_text: str) -> Optional[Tuple[str, int]]:
    parsed = parse_slash_name(prepared_text)
    if parsed is None:
        return None
    _name, prepared_rest, prepared_rest_offset = parsed
    return prepared_rest, prepared_rest_offset


def args_elements(
    rest: str,
    rest_offset: int,
    text_elements: Sequence[TextElement],
) -> List[TextElement]:
    if not rest or not text_elements:
        return []
    rest_len = _utf8_len(rest)
    shifted = []  # type: List[TextElement]
    for elem in text_elements:
        byte_range = elem.byte_range
        if byte_range.end <= rest_offset:
            continue
        start = max(byte_range.start - rest_offset, 0)
        end = max(byte_range.end - rest_offset, 0)
        if start >= rest_len:
            continue
        end = min(end, rest_len)
        if start < end:
            shifted.append(elem.map_range(lambda _range, start=start, end=end: ByteRange(start, end)))
    return shifted


def command_popup_filter_text(first_line: str, cursor: int) -> Optional[str]:
    under_cursor = command_under_cursor(first_line, cursor)
    if under_cursor is None:
        return None
    name, _rest = under_cursor
    return f"/{name}"


def command_under_cursor(first_line: str, cursor: int) -> Optional[Tuple[str, str]]:
    if not first_line.startswith("/"):
        return None
    first_line_len = _utf8_len(first_line)
    if cursor > first_line_len or not _is_char_boundary(first_line, cursor):
        return None

    name_start = 1
    name_end = first_line_len
    byte_pos = name_start
    for char in first_line[1:]:
        if char.isspace():
            name_end = byte_pos
            break
        byte_pos += _utf8_len(char)

    effective_cursor = name_end if cursor <= name_start else cursor
    if effective_cursor > name_end:
        return None

    name = _byte_slice(first_line, name_start, effective_cursor)
    rest = _byte_slice(first_line, effective_cursor, first_line_len)
    return name, rest


def complete_selected_slash_command_preserving_existing_draft_tail_as_inline_args(
    text: str,
    cursor: int,
    selected_cmd: Any,
    text_elements: Sequence[TextElement] = (),
) -> Optional[SlashCompletionResult]:
    """Port Rust's inline-arg slash completion mutation as a pure result.

    The Rust method mutates ``ChatComposer.draft.textarea``.  Python keeps the
    same byte-offset replacement, command-token, tail-preservation, cursor, and
    element-unmarking semantics in a serializable result.
    """

    cmd = _builtin_slash_command(selected_cmd)
    if cmd is None or not _supports_inline_args(selected_cmd, cmd):
        return None

    text_len = _utf8_len(text)
    first_line_end = _byte_find(text, "\n")
    if first_line_end < 0:
        first_line_end = text_len
    if cursor > first_line_end or not text.startswith("/") or not _is_char_boundary(text, cursor):
        return None

    first_line = _byte_slice(text, 0, first_line_end)
    command_token_end = _command_token_end(first_line)
    typed_command_name = _byte_slice(text, 1, command_token_end)
    rest_after_token = _byte_slice(text, command_token_end, text_len)
    rest_after_token_is_empty = rest_after_token.strip() == ""
    if rest_after_token_is_empty and (cursor <= 1 or cursor >= command_token_end):
        return None

    if cursor <= 1 or (typed_command_name == cmd.command() and rest_after_token_is_empty):
        replace_end = command_token_end
    else:
        replace_end = cursor

    tail = _byte_slice(text, replace_end, text_len)
    selected_command_text = "/{}".format(cmd.command())
    replacement = selected_command_text if tail[:1].isspace() else "{} ".format(selected_command_text)
    next_text = replacement + tail
    ranges_to_unmark = []  # type: List[Tuple[int, int]]
    for element in text_elements:
        byte_range = element.byte_range
        if byte_range.start < replace_end < byte_range.end:
            ranges_to_unmark.append((byte_range.start, byte_range.end))
    return SlashCompletionResult(
        text=next_text,
        cursor=_utf8_len(next_text),
        ranges_to_unmark=tuple(ranges_to_unmark),
    )


def sync_slash_command_elements(
    slash_input: SlashInput,
    text: str,
    cursor: int,
    text_elements: Sequence[TextElement],
) -> SlashElementSyncResult:
    """Port Rust ``sync_slash_command_elements`` as semantic add/remove ranges."""

    first_line_end = _byte_find(text, "\n")
    if first_line_end < 0:
        first_line_end = _utf8_len(text)
    first_line = _byte_slice(text, 0, first_line_end)
    desired_range = slash_input.command_element_range(first_line, cursor)
    has_desired = False
    stale_ranges = []  # type: List[Tuple[int, int]]

    for element in text_elements:
        placeholder = _element_placeholder(element, text)
        if placeholder is None or not placeholder.startswith("/"):
            continue
        byte_range = element.byte_range
        element_range = (byte_range.start, byte_range.end)
        if desired_range == element_range:
            has_desired = True
        else:
            stale_ranges.append(element_range)

    add_range = desired_range if desired_range is not None and not has_desired else None
    return SlashElementSyncResult(
        desired_range=desired_range,
        add_range=add_range,
        stale_ranges=tuple(stale_ranges),
    )


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _byte_slice(value: str, start: int, end: int) -> str:
    return value.encode("utf-8")[start:end].decode("utf-8")


def _byte_find(value: str, needle: str) -> int:
    return value.encode("utf-8").find(needle.encode("utf-8"))


def _is_char_boundary(value: str, byte_index: int) -> bool:
    if byte_index < 0 or byte_index > _utf8_len(value):
        return False
    try:
        _byte_slice(value, 0, byte_index)
    except UnicodeDecodeError:
        return False
    return True


def _command_name(command: Any) -> str:
    if hasattr(command, "command"):
        return str(command.command())
    if isinstance(command, SlashCommand):
        return command.command()
    return str(command)


def _command_payload(command: Any) -> Any:
    if isinstance(command, SlashCommandItem) and command.kind == "Builtin":
        return command.value
    if isinstance(command, SlashCommand):
        return command
    return getattr(command, "value", command)


def _command_token_end(first_line: str) -> int:
    byte_pos = 1
    for char in first_line[1:]:
        if char.isspace():
            return byte_pos
        byte_pos += _utf8_len(char)
    return _utf8_len(first_line)


def _builtin_slash_command(command: Any) -> Optional[SlashCommand]:
    if isinstance(command, SlashCommandItem) and command.kind == "Builtin":
        return command.value
    if isinstance(command, SlashCommand):
        return command
    return None


def _supports_inline_args(original: Any, command: SlashCommand) -> bool:
    supports_inline_args = getattr(original, "supports_inline_args", None)
    if callable(supports_inline_args):
        return bool(supports_inline_args())
    supports_inline_args = getattr(command, "supports_inline_args", None)
    if callable(supports_inline_args):
        return bool(supports_inline_args())
    return command is SlashCommand.REVIEW


def _element_placeholder(element: TextElement, text: str) -> Optional[str]:
    placeholder = getattr(element, "placeholder", None)
    if callable(placeholder):
        return placeholder(text)
    placeholder_for_conversion_only = getattr(element, "placeholder_for_conversion_only", None)
    if callable(placeholder_for_conversion_only):
        return placeholder_for_conversion_only()
    return None


__all__ = [
    "CommandPopupSnapshot",
    "InlineCommand",
    "QueuedInputAction",
    "RUST_MODULE",
    "SlashCompletionResult",
    "SlashElementSyncResult",
    "SlashInput",
    "SlashValidation",
    "SubmissionValidation",
    "args_elements",
    "command_popup_filter_text",
    "command_under_cursor",
    "complete_selected_slash_command_preserving_existing_draft_tail_as_inline_args",
    "prepared_args",
    "queued_input_action",
    "selected_command_completion",
    "selected_command_dispatches_immediately_on_tab",
    "sync_slash_command_elements",
]
