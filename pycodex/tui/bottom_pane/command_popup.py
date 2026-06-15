"""Command popup behavior for Rust ``codex-tui::bottom_pane::command_popup``.

The Rust popup owns command filtering, selected item movement, and conversion to
selection-popup rows.  Python keeps those semantics with lightweight semantic
rows instead of ratatui buffer mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple, Union

from .._porting import RustTuiModule
from ..slash_command import SlashCommand
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState
from .selection_popup_common import (
    ColumnWidthConfig,
    ColumnWidthMode,
    GenericDisplayRow,
    measure_rows_height_with_col_width_mode,
    render_rows_with_col_width_mode,
)
from .slash_commands import (
    BuiltinCommandFlags,
    ServiceTierCommand,
    SlashCommandItem,
    commands_for_input,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::command_popup",
    source="codex/codex-rs/tui/src/bottom_pane/command_popup.rs",
    status="complete",
)

ALIAS_COMMANDS = (SlashCommand.QUIT, SlashCommand.BTW)
COMMAND_COLUMN_WIDTH = ColumnWidthConfig(ColumnWidthMode.AUTO_ALL_ROWS, None)


@dataclass(frozen=True)
class CommandItem:
    """Rust ``CommandItem`` semantic enum."""

    kind: str
    value: Union[SlashCommand, ServiceTierCommand]

    @classmethod
    def builtin(cls, command: SlashCommand) -> "CommandItem":
        return cls("Builtin", command)

    @classmethod
    def service_tier(cls, command: ServiceTierCommand) -> "CommandItem":
        return cls("ServiceTier", command)

    def command(self) -> str:
        if self.kind == "Builtin":
            return _builtin(self.value).command()
        return _service_tier(self.value).name

    def description(self) -> str:
        if self.kind == "Builtin":
            return _builtin(self.value).description()
        return _service_tier(self.value).description


@dataclass(frozen=True)
class CommandPopupFlags:
    collaboration_modes_enabled: bool = False
    connectors_enabled: bool = False
    plugins_command_enabled: bool = False
    service_tier_commands_enabled: bool = False
    goal_command_enabled: bool = False
    personality_command_enabled: bool = False
    realtime_conversation_enabled: bool = False
    audio_device_selection_enabled: bool = False
    windows_degraded_sandbox_active: bool = False
    side_conversation_active: bool = False

    def to_builtin_flags(self) -> BuiltinCommandFlags:
        return BuiltinCommandFlags(
            collaboration_modes_enabled=self.collaboration_modes_enabled,
            connectors_enabled=self.connectors_enabled,
            plugins_command_enabled=self.plugins_command_enabled,
            service_tier_commands_enabled=self.service_tier_commands_enabled,
            goal_command_enabled=self.goal_command_enabled,
            personality_command_enabled=self.personality_command_enabled,
            realtime_conversation_enabled=self.realtime_conversation_enabled,
            audio_device_selection_enabled=self.audio_device_selection_enabled,
            allow_elevate_sandbox=self.windows_degraded_sandbox_active,
            side_conversation_active=self.side_conversation_active,
        )


@dataclass
class CommandPopup:
    command_filter: str = ""
    commands: List[CommandItem] = field(default_factory=list)
    state: ScrollState = field(default_factory=ScrollState.new)

    @classmethod
    def new(
        cls,
        flags: Optional[CommandPopupFlags] = None,
        service_tier_commands: Iterable[ServiceTierCommand] = (),
    ) -> "CommandPopup":
        flags = flags or CommandPopupFlags()
        commands: List[CommandItem] = []
        for item in commands_for_input(flags.to_builtin_flags(), tuple(service_tier_commands)):
            if item.kind == "Builtin":
                command = item.value
                if not isinstance(command, SlashCommand):
                    continue
                if command.command().startswith("debug") or command is SlashCommand.APPS:
                    continue
                commands.append(CommandItem.builtin(command))
            else:
                commands.append(CommandItem.service_tier(item.value))
        return cls(commands=commands)

    def on_composer_text_change(self, text: str) -> None:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if first_line.startswith("/"):
            token = first_line[1:].lstrip()
            self.command_filter = token.split()[0] if token.split() else ""
        else:
            self.command_filter = ""

        matches_len = len(self.filtered_items())
        self.state.clamp_selection(matches_len)
        self.state.ensure_visible(matches_len, min(MAX_POPUP_ROWS, matches_len))

    def calculate_required_height(self, width: int) -> int:
        rows = self.rows_from_matches(self.filtered())
        return measure_rows_height_with_col_width_mode(
            rows,
            self.state,
            MAX_POPUP_ROWS,
            width,
            COMMAND_COLUMN_WIDTH,
        )

    def filtered(self) -> List[Tuple[CommandItem, Optional[List[int]]]]:
        filter_text = self.command_filter.strip()
        if not filter_text:
            return [
                (command, None)
                for command in self.commands
                if not (command.kind == "Builtin" and command.value in ALIAS_COMMANDS)
            ]

        filter_lower = filter_text.lower()
        filter_chars = len(filter_text)
        exact: List[Tuple[CommandItem, Optional[List[int]]]] = []
        prefix: List[Tuple[CommandItem, Optional[List[int]]]] = []

        for command in self.commands:
            display = command.command()
            display_lower = display.lower()
            indices = list(range(filter_chars))
            if display_lower == filter_lower:
                exact.append((command, indices))
            elif display_lower.startswith(filter_lower):
                prefix.append((command, indices))

        return exact + prefix

    def filtered_items(self) -> List[CommandItem]:
        return [command for command, _indices in self.filtered()]

    def rows_from_matches(
        self,
        matches: Iterable[Tuple[CommandItem, Optional[List[int]]]],
    ) -> List[GenericDisplayRow]:
        rows: List[GenericDisplayRow] = []
        for item, indices in matches:
            rows.append(
                GenericDisplayRow(
                    name=f"/{item.command()}",
                    name_prefix_spans=[],
                    match_indices=[index + 1 for index in indices] if indices is not None else None,
                    display_shortcut=None,
                    description=item.description(),
                    category_tag=None,
                    wrap_indent=None,
                    is_disabled=False,
                    disabled_reason=None,
                )
            )
        return rows

    def move_up(self) -> None:
        length = len(self.filtered_items())
        self.state.move_up_wrap(length)
        self.state.ensure_visible(length, min(MAX_POPUP_ROWS, length))

    def move_down(self) -> None:
        length = len(self.filtered_items())
        self.state.move_down_wrap(length)
        self.state.ensure_visible(length, min(MAX_POPUP_ROWS, length))

    def selected_item(self) -> Optional[CommandItem]:
        matches = self.filtered_items()
        if self.state.selected_idx is None:
            return None
        if self.state.selected_idx < 0 or self.state.selected_idx >= len(matches):
            return None
        return matches[self.state.selected_idx]

    def render_ref(self, area: Any, buffer: Any) -> Any:
        rows = self.rows_from_matches(self.filtered())
        return render_rows_with_col_width_mode(
            _inset_area(area, left=2),
            buffer,
            rows,
            self.state,
            MAX_POPUP_ROWS,
            "no matches",
            COMMAND_COLUMN_WIDTH,
        )


def from_(value: CommandPopupFlags) -> BuiltinCommandFlags:
    return value.to_builtin_flags()


def render_ref(popup: CommandPopup, area: Any, buffer: Any) -> Any:
    return popup.render_ref(area, buffer)


def _inset_area(area: Any, *, left: int) -> Any:
    if isinstance(area, dict):
        copy = dict(area)
        copy["x"] = copy.get("x", 0) + left
        copy["width"] = max(copy.get("width", 0) - left, 0)
        return copy
    if hasattr(area, "x") and hasattr(area, "width"):
        try:
            return type(area)(area.x + left, area.y, max(area.width - left, 0), area.height)
        except Exception:
            return area
    return area


def _builtin(value: Any) -> SlashCommand:
    if not isinstance(value, SlashCommand):
        raise TypeError(f"expected SlashCommand, got {type(value).__name__}")
    return value


def _service_tier(value: Any) -> ServiceTierCommand:
    if not isinstance(value, ServiceTierCommand):
        raise TypeError(f"expected ServiceTierCommand, got {type(value).__name__}")
    return value


__all__ = [
    "ALIAS_COMMANDS",
    "COMMAND_COLUMN_WIDTH",
    "CommandItem",
    "CommandPopup",
    "CommandPopupFlags",
    "RUST_MODULE",
    "from_",
    "render_ref",
]
