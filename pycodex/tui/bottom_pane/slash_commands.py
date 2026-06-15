"""Slash-command filtering for Rust ``codex-tui::bottom_pane::slash_commands``.

The Rust module is shared by the composer dispatch path and the popup.  This
Python port keeps the same boundary: feature flags decide which built-in
commands are visible, service-tier commands are inserted after ``/model``, and
exact dispatch lookup intentionally ignores side-conversation popup hiding so
callers can report a context-specific unavailable-command error.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from ..slash_command import SlashCommand, built_in_slash_commands

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::slash_commands",
    source="codex/codex-rs/tui/src/bottom_pane/slash_commands.rs",
    status="complete",
)


@dataclass(frozen=True)
class ServiceTierCommand:
    """Semantic equivalent of Rust ``ServiceTierCommand``."""

    id: str
    name: str
    description: str


@dataclass(frozen=True)
class SlashCommandItem:
    """Semantic equivalent of Rust ``SlashCommandItem``.

    ``kind`` is ``"Builtin"`` or ``"ServiceTier"`` to preserve Rust variant
    names while keeping the payload Python-native.
    """

    kind: str
    value: Any

    @classmethod
    def builtin(cls, command: SlashCommand) -> "SlashCommandItem":
        return cls("Builtin", command)

    @classmethod
    def service_tier(cls, command: ServiceTierCommand) -> "SlashCommandItem":
        return cls("ServiceTier", command)

    def command(self) -> str:
        if self.kind == "Builtin":
            return _builtin(self.value).command()
        return _service_tier(self.value).name

    def supports_inline_args(self) -> bool:
        if self.kind == "Builtin":
            return _builtin(self.value).supports_inline_args()
        return False

    def available_in_side_conversation(self) -> bool:
        if self.kind == "Builtin":
            return _builtin(self.value).available_in_side_conversation()
        return False

    def available_during_task(self) -> bool:
        if self.kind == "Builtin":
            return _builtin(self.value).available_during_task()
        return False


@dataclass(frozen=True)
class BuiltinCommandFlags:
    """Feature gates used by Rust to filter built-in slash commands."""

    collaboration_modes_enabled: bool = False
    connectors_enabled: bool = False
    plugins_command_enabled: bool = False
    service_tier_commands_enabled: bool = False
    goal_command_enabled: bool = False
    personality_command_enabled: bool = False
    realtime_conversation_enabled: bool = False
    audio_device_selection_enabled: bool = False
    allow_elevate_sandbox: bool = False
    side_conversation_active: bool = False


def builtins_for_input(flags: BuiltinCommandFlags) -> List[Tuple[str, SlashCommand]]:
    """Return built-ins visible/usable for the current input flags."""

    return [(name, command) for name, command in built_in_slash_commands() if _builtin_visible(command, flags)]


def commands_for_input(
    flags: BuiltinCommandFlags,
    service_tier_commands: Iterable[ServiceTierCommand],
) -> List[SlashCommandItem]:
    """Return popup/dispatch command items with service tiers after ``/model``."""

    tiers = list(service_tier_commands)
    tiers_enabled = flags.service_tier_commands_enabled
    commands: List[SlashCommandItem] = []

    for _, command in builtins_for_input(flags):
        commands.append(SlashCommandItem.builtin(command))
        if command is SlashCommand.MODEL and tiers_enabled:
            commands.extend(SlashCommandItem.service_tier(tier) for tier in tiers)

    if flags.side_conversation_active:
        commands = [command for command in commands if command.available_in_side_conversation()]
    return commands


def find_builtin_command(name: str, flags: BuiltinCommandFlags) -> Optional[SlashCommand]:
    """Find an exact built-in command after feature gating.

    Side-conversation popup hiding is intentionally ignored for exact lookup,
    matching Rust's dispatch boundary.
    """

    try:
        command = SlashCommand.parse(name)
    except ValueError:
        return None

    dispatch_flags = replace(flags, side_conversation_active=False)
    visible_commands = {visible for _, visible in builtins_for_input(dispatch_flags)}
    if command in visible_commands:
        return command
    return None


def find_slash_command(
    name: str,
    flags: BuiltinCommandFlags,
    service_tier_commands: Iterable[ServiceTierCommand],
) -> Optional[SlashCommandItem]:
    """Find an exact built-in or enabled service-tier slash command."""

    builtin = find_builtin_command(name, flags)
    if builtin is not None:
        return SlashCommandItem.builtin(builtin)

    if not flags.service_tier_commands_enabled:
        return None

    for command in service_tier_commands:
        if command.name == name:
            return SlashCommandItem.service_tier(command)
    return None


def has_slash_command_prefix(
    name: str,
    flags: BuiltinCommandFlags,
    service_tier_commands: Iterable[ServiceTierCommand],
) -> bool:
    """Return whether any visible command fuzzily matches ``name``."""

    return any(_fuzzy_match(command.command(), name) for command in commands_for_input(flags, service_tier_commands))


def all_enabled_flags() -> BuiltinCommandFlags:
    """Test helper matching Rust's local ``all_enabled_flags`` helper."""

    return BuiltinCommandFlags(
        collaboration_modes_enabled=True,
        connectors_enabled=True,
        plugins_command_enabled=True,
        service_tier_commands_enabled=True,
        goal_command_enabled=True,
        personality_command_enabled=True,
        realtime_conversation_enabled=True,
        audio_device_selection_enabled=True,
        allow_elevate_sandbox=True,
        side_conversation_active=False,
    )


def _builtin_visible(command: SlashCommand, flags: BuiltinCommandFlags) -> bool:
    if not flags.allow_elevate_sandbox and command is SlashCommand.ELEVATE_SANDBOX:
        return False
    if not flags.collaboration_modes_enabled and command is SlashCommand.PLAN:
        return False
    if not flags.connectors_enabled and command is SlashCommand.APPS:
        return False
    if not flags.plugins_command_enabled and command is SlashCommand.PLUGINS:
        return False
    if not flags.goal_command_enabled and command is SlashCommand.GOAL:
        return False
    if not flags.personality_command_enabled and command is SlashCommand.PERSONALITY:
        return False
    if not flags.realtime_conversation_enabled and command is SlashCommand.REALTIME:
        return False
    if not flags.audio_device_selection_enabled and command is SlashCommand.SETTINGS:
        return False
    if flags.side_conversation_active and not command.available_in_side_conversation():
        return False
    return True


def _fuzzy_match(candidate: str, query: str) -> bool:
    """Small subsequence matcher for Rust ``codex_utils_fuzzy_match`` use here."""

    if not query:
        return True
    it = iter(candidate.lower())
    return all(char.lower() in it for char in query)


def _builtin(value: Any) -> SlashCommand:
    if not isinstance(value, SlashCommand):
        raise TypeError(f"expected Builtin SlashCommand payload, got {type(value).__name__}")
    return value


def _service_tier(value: Any) -> ServiceTierCommand:
    if not isinstance(value, ServiceTierCommand):
        raise TypeError(f"expected ServiceTierCommand payload, got {type(value).__name__}")
    return value


__all__ = [
    "BuiltinCommandFlags",
    "RUST_MODULE",
    "ServiceTierCommand",
    "SlashCommandItem",
    "all_enabled_flags",
    "builtins_for_input",
    "commands_for_input",
    "find_builtin_command",
    "find_slash_command",
    "has_slash_command_prefix",
]
