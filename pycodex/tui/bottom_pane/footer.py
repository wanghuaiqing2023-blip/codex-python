"""Semantic footer helpers for Rust ``bottom_pane/footer.rs``.

The Rust module is mostly pure formatting plus ratatui rendering.  Python keeps
the formatting/state-machine contract as strings and lightweight dataclasses;
exact cell rendering and the full width-collapse algorithm stay renderer
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::footer",
    source="codex/codex-rs/tui/src/bottom_pane/footer.rs",
    status="complete",
)

MODE_CYCLE_HINT = "shift+tab to cycle"
FOOTER_CONTEXT_GAP_COLS = 1
FOOTER_INDENT_COLS = 2
COLUMNS = 2
COLUMN_PADDING = (4, 4)
COLUMN_GAP = 4


@dataclass(frozen=True)
class KeyBinding:
    code: str
    modifiers: Tuple[str, ...] = ()

    def __str__(self) -> str:
        if not self.modifiers:
            return self.code
        return "+".join((*self.modifiers, self.code))


def plain(code: str) -> KeyBinding:
    return KeyBinding(code)


def ctrl(code: str) -> KeyBinding:
    return KeyBinding(code, ("ctrl",))


def alt(code: str) -> KeyBinding:
    return KeyBinding(code, ("alt",))


def shift(code: str) -> KeyBinding:
    return KeyBinding(code, ("shift",))


def ctrl_alt(code: str) -> KeyBinding:
    return KeyBinding(code, ("ctrl", "alt"))


class CollaborationModeIndicator(Enum):
    PLAN = "Plan"
    PAIR_PROGRAMMING = "PairProgramming"
    EXECUTE = "Execute"

    def label(self, show_cycle_hint: bool = False) -> str:
        suffix = f" ({MODE_CYCLE_HINT})" if show_cycle_hint else ""
        if self is CollaborationModeIndicator.PLAN:
            return f"Plan mode{suffix}"
        if self is CollaborationModeIndicator.PAIR_PROGRAMMING:
            return f"Pair Programming mode{suffix}"
        return f"Execute mode{suffix}"


@dataclass(frozen=True)
class GoalStatusIndicator:
    kind: str
    usage: Optional[str] = None

    @classmethod
    def Active(cls, usage: Optional[str] = None) -> "GoalStatusIndicator":
        return cls("Active", usage)

    @classmethod
    def BudgetLimited(cls, usage: Optional[str] = None) -> "GoalStatusIndicator":
        return cls("BudgetLimited", usage)

    @classmethod
    def Complete(cls, usage: Optional[str] = None) -> "GoalStatusIndicator":
        return cls("Complete", usage)


class FooterMode(Enum):
    HISTORY_SEARCH = "HistorySearch"
    QUIT_SHORTCUT_REMINDER = "QuitShortcutReminder"
    SHORTCUT_OVERLAY = "ShortcutOverlay"
    ESC_HINT = "EscHint"
    COMPOSER_EMPTY = "ComposerEmpty"
    COMPOSER_HAS_DRAFT = "ComposerHasDraft"


@dataclass(frozen=True)
class FooterKeyHints:
    toggle_shortcuts: Optional[KeyBinding] = None
    queue: Optional[KeyBinding] = None
    insert_newline: Optional[KeyBinding] = None
    external_editor: Optional[KeyBinding] = None
    edit_previous: Optional[KeyBinding] = None
    show_transcript: Optional[KeyBinding] = None
    history_search: Optional[KeyBinding] = None
    reasoning_down: Optional[KeyBinding] = None
    reasoning_up: Optional[KeyBinding] = None

    @classmethod
    def default_bindings(cls) -> "FooterKeyHints":
        return cls(
            toggle_shortcuts=plain("?"),
            queue=plain("Tab"),
            insert_newline=ctrl("j"),
            external_editor=ctrl("g"),
            edit_previous=plain("Esc"),
            show_transcript=ctrl("t"),
            history_search=ctrl("r"),
            reasoning_down=alt(","),
            reasoning_up=alt("."),
        )


@dataclass
class FooterProps:
    mode: FooterMode = FooterMode.COMPOSER_EMPTY
    esc_backtrack_hint: bool = False
    use_shift_enter_hint: bool = False
    is_task_running: bool = False
    collaboration_modes_enabled: bool = False
    is_wsl: bool = False
    quit_shortcut_key: KeyBinding = ctrl("c")
    status_line_value: Optional[str] = None
    status_line_enabled: bool = False
    key_hints: FooterKeyHints = FooterKeyHints.default_bindings()
    active_agent_label: Optional[str] = None


@dataclass(frozen=True)
class TerminalIdleFooterData:
    """Text-only footer inputs for the real-terminal scrollback product path."""

    model_with_reasoning: str
    cwd: Union[str, Path, None] = None
    show_fast_status: bool = False


class SummaryHintKind(Enum):
    NONE = "None"
    SHORTCUTS = "Shortcuts"
    QUEUE_MESSAGE = "QueueMessage"
    QUEUE_SHORT = "QueueShort"


@dataclass(frozen=True)
class LeftSideState:
    hint: SummaryHintKind = SummaryHintKind.NONE
    show_cycle_hint: bool = False


@dataclass(frozen=True)
class SummaryLeft:
    kind: str
    line: Optional[str] = None

    @classmethod
    def Default(cls) -> "SummaryLeft":
        return cls("Default")

    @classmethod
    def Custom(cls, line: str) -> "SummaryLeft":
        return cls("Custom", line)

    @classmethod
    def None_(cls) -> "SummaryLeft":
        return cls("None")


@dataclass(frozen=True)
class ShortcutsState:
    use_shift_enter_hint: bool = False
    esc_backtrack_hint: bool = False
    is_wsl: bool = False
    collaboration_modes_enabled: bool = False
    key_hints: FooterKeyHints = FooterKeyHints.default_bindings()


class ShortcutId(Enum):
    COMMANDS = "Commands"
    SHELL_COMMANDS = "ShellCommands"
    PASTE_IMAGE = "PasteImage"
    INSERT_NEWLINE = "InsertNewline"
    QUEUE_MESSAGE_TAB = "QueueMessageTab"
    FILE_PATHS = "FilePaths"
    EXTERNAL_EDITOR = "ExternalEditor"
    EDIT_PREVIOUS = "EditPrevious"
    SHOW_TRANSCRIPT = "ShowTranscript"
    HISTORY_SEARCH = "HistorySearch"
    QUIT = "Quit"
    CHANGE_MODE = "ChangeMode"
    REASONING_DOWN = "ReasoningDown"
    REASONING_UP = "ReasoningUp"


@dataclass(frozen=True)
class ShortcutBinding:
    key: KeyBinding

    def matches(self, key: Union[KeyBinding, str]) -> bool:
        return str(self.key) == str(key)


class DisplayCondition(Enum):
    ALWAYS = "Always"
    SHIFT_ENTER_HINT = "ShiftEnterHint"
    ESC_BACKTRACK_HINT = "EscBacktrackHint"
    COLLABORATION_MODES_ENABLED = "CollaborationModesEnabled"


@dataclass(frozen=True)
class ShortcutDescriptor:
    id: ShortcutId
    description: str

    def binding_for(self, state: ShortcutsState) -> Optional[ShortcutBinding]:
        if self.id is ShortcutId.INSERT_NEWLINE:
            key = shift("Enter") if state.use_shift_enter_hint else state.key_hints.insert_newline
            return None if key is None else ShortcutBinding(key)
        if self.id is ShortcutId.PASTE_IMAGE:
            return ShortcutBinding(ctrl_alt("v") if state.is_wsl else ctrl("v"))
        if self.id is ShortcutId.CHANGE_MODE and not state.collaboration_modes_enabled:
            return None
        mapping = {
            ShortcutId.COMMANDS: plain("/"),
            ShortcutId.SHELL_COMMANDS: plain("!"),
            ShortcutId.QUEUE_MESSAGE_TAB: state.key_hints.queue,
            ShortcutId.FILE_PATHS: plain("@"),
            ShortcutId.EXTERNAL_EDITOR: state.key_hints.external_editor,
            ShortcutId.EDIT_PREVIOUS: state.key_hints.edit_previous,
            ShortcutId.SHOW_TRANSCRIPT: state.key_hints.show_transcript,
            ShortcutId.HISTORY_SEARCH: state.key_hints.history_search,
            ShortcutId.QUIT: ctrl("c"),
            ShortcutId.CHANGE_MODE: shift("Tab"),
            ShortcutId.REASONING_DOWN: state.key_hints.reasoning_down,
            ShortcutId.REASONING_UP: state.key_hints.reasoning_up,
        }
        key = mapping.get(self.id)
        return None if key is None else ShortcutBinding(key)

    def overlay_entry(self, state: ShortcutsState) -> Optional[str]:
        binding = self.binding_for(state)
        if binding is None:
            return None
        if self.id is ShortcutId.EDIT_PREVIOUS:
            return f"{_display_key(binding.key)} again to edit previous message"
        return f"{_display_key(binding.key)} {self.description}".rstrip()


SHORTCUTS = [
    ShortcutDescriptor(ShortcutId.COMMANDS, "for commands"),
    ShortcutDescriptor(ShortcutId.SHELL_COMMANDS, "for shell commands"),
    ShortcutDescriptor(ShortcutId.INSERT_NEWLINE, "for newline"),
    ShortcutDescriptor(ShortcutId.QUEUE_MESSAGE_TAB, "to queue message"),
    ShortcutDescriptor(ShortcutId.FILE_PATHS, "for file paths"),
    ShortcutDescriptor(ShortcutId.PASTE_IMAGE, "to paste images"),
    ShortcutDescriptor(ShortcutId.EXTERNAL_EDITOR, "to edit in external editor"),
    ShortcutDescriptor(ShortcutId.EDIT_PREVIOUS, ""),
    ShortcutDescriptor(ShortcutId.HISTORY_SEARCH, "search history"),
    ShortcutDescriptor(ShortcutId.QUIT, "to exit"),
    ShortcutDescriptor(ShortcutId.REASONING_DOWN, "reasoning down"),
    ShortcutDescriptor(ShortcutId.REASONING_UP, "reasoning up"),
    ShortcutDescriptor(ShortcutId.CHANGE_MODE, "to change mode"),
    ShortcutDescriptor(ShortcutId.SHOW_TRANSCRIPT, "to view transcript"),
]


def toggle_shortcut_mode(current: FooterMode, ctrl_c_hint: bool, is_empty: bool) -> FooterMode:
    current = FooterMode(current)
    if ctrl_c_hint and current is FooterMode.QUIT_SHORTCUT_REMINDER:
        return current
    base_mode = FooterMode.COMPOSER_EMPTY if is_empty else FooterMode.COMPOSER_HAS_DRAFT
    if current in {FooterMode.SHORTCUT_OVERLAY, FooterMode.QUIT_SHORTCUT_REMINDER}:
        return base_mode
    return FooterMode.SHORTCUT_OVERLAY


def esc_hint_mode(current: FooterMode, is_task_running: bool) -> FooterMode:
    return FooterMode(current) if is_task_running else FooterMode.ESC_HINT


def reset_mode_after_activity(current: FooterMode) -> FooterMode:
    current = FooterMode(current)
    if current in {
        FooterMode.ESC_HINT,
        FooterMode.SHORTCUT_OVERLAY,
        FooterMode.QUIT_SHORTCUT_REMINDER,
        FooterMode.HISTORY_SEARCH,
        FooterMode.COMPOSER_HAS_DRAFT,
    }:
        return FooterMode.COMPOSER_EMPTY
    return current


def footer_height(props: FooterProps) -> int:
    show_shortcuts_hint = props.mode is FooterMode.COMPOSER_EMPTY
    show_queue_hint = props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running
    return len(
        footer_from_props_lines(
            props,
            collaboration_mode_indicator=None,
            show_cycle_hint=False,
            show_shortcuts_hint=show_shortcuts_hint,
            show_queue_hint=show_queue_hint,
        )
    )


def render_footer_line(area: Any, buf: Any, line: str) -> str:
    rendered = " " * FOOTER_INDENT_COLS + str(line)
    if isinstance(buf, list):
        buf.append(rendered)
    return rendered


def render_footer_from_props(
    area: Any,
    buf: Any,
    props: FooterProps,
    collaboration_mode_indicator: Optional[CollaborationModeIndicator] = None,
    show_cycle_hint: bool = False,
    show_shortcuts_hint: bool = False,
    show_queue_hint: bool = False,
) -> List[str]:
    del area
    lines = footer_from_props_lines(
        props,
        collaboration_mode_indicator,
        show_cycle_hint,
        show_shortcuts_hint,
        show_queue_hint,
    )
    rendered = [render_footer_line(None, None, line) for line in lines]
    if isinstance(buf, list):
        buf.extend(rendered)
    return rendered


def left_fits(area: Any, left_width: int) -> bool:
    return int(left_width) <= max(_area_width(area) - FOOTER_INDENT_COLS, 0)


def left_side_line(
    collaboration_mode_indicator: Optional[CollaborationModeIndicator],
    state: LeftSideState,
    key_hints: FooterKeyHints,
) -> str:
    parts: List[str] = []
    if state.hint is SummaryHintKind.SHORTCUTS and key_hints.toggle_shortcuts:
        parts.append(f"{key_hints.toggle_shortcuts} for shortcuts")
    elif state.hint is SummaryHintKind.QUEUE_MESSAGE and key_hints.queue:
        parts.append(f"{key_hints.queue} to queue message")
    elif state.hint is SummaryHintKind.QUEUE_SHORT and key_hints.queue:
        parts.append(f"{key_hints.queue} to queue")
    if collaboration_mode_indicator is not None:
        if parts:
            parts.append("-")
        parts.append(collaboration_mode_indicator.label(state.show_cycle_hint))
    return " ".join(parts)


def single_line_footer_layout(
    area: Any,
    context_width: int,
    collaboration_mode_indicator: Optional[CollaborationModeIndicator],
    show_cycle_hint: bool,
    show_shortcuts_hint: bool,
    show_queue_hint: bool,
    key_hints: FooterKeyHints,
) -> Tuple[SummaryLeft, bool]:
    hint = SummaryHintKind.QUEUE_MESSAGE if show_queue_hint else (
        SummaryHintKind.SHORTCUTS if show_shortcuts_hint else SummaryHintKind.NONE
    )
    line = left_side_line(collaboration_mode_indicator, LeftSideState(hint, show_cycle_hint), key_hints)
    if line and can_show_left_with_context(area, len(line), context_width):
        return SummaryLeft.Default(), True
    if line and left_fits(area, len(line)):
        return SummaryLeft.Default(), False
    if collaboration_mode_indicator is not None:
        compact = collaboration_mode_indicator.label(False)
        if left_fits(area, len(compact)):
            return SummaryLeft.Custom(compact), False
    return SummaryLeft.None_(), can_show_left_with_context(area, 0, context_width)


def mode_indicator_line(indicator: CollaborationModeIndicator, show_cycle_hint: bool = False) -> str:
    return CollaborationModeIndicator(indicator).label(show_cycle_hint)


def goal_status_indicator_line(indicator: GoalStatusIndicator) -> str:
    # Rust source: codex-tui/src/bottom_pane/footer.rs::goal_status_indicator_line.
    if indicator.kind == "Active":
        return f"Pursuing goal ({indicator.usage})" if indicator.usage else "Pursuing goal"
    if indicator.kind == "Paused":
        return "Goal paused (/goal resume)"
    if indicator.kind == "Blocked":
        return "Goal blocked (/goal resume)"
    if indicator.kind == "UsageLimited":
        return "Goal hit usage limits (/goal resume)"
    if indicator.kind == "BudgetLimited":
        return f"Goal unmet ({indicator.usage})" if indicator.usage else "Goal abandoned"
    if indicator.kind == "Complete":
        return f"Goal achieved ({indicator.usage})" if indicator.usage else "Goal achieved"
    return indicator.kind


def status_line_right_indicator_line(
    status_line: Optional[str],
    active_agent_label: Optional[str] = None,
    goal_status_indicator: Optional[GoalStatusIndicator] = None,
) -> Optional[str]:
    right_indicator = active_agent_label or (
        goal_status_indicator_line(goal_status_indicator) if goal_status_indicator is not None else None
    )
    if status_line and right_indicator:
        return f"{status_line} · {right_indicator}"
    return status_line or right_indicator


def side_conversation_context_line(side_label: Optional[str] = None) -> Optional[str]:
    return None if not side_label else f"Side: {side_label}"


def right_aligned_x(area: Any, width: int) -> int:
    return max(_area_width(area) - int(width), 0)


def max_left_width_for_right(area: Any, right_width: int) -> int:
    return max(_area_width(area) - FOOTER_CONTEXT_GAP_COLS - int(right_width), 0)


def can_show_left_with_context(area: Any, left_width: int, context_width: int) -> bool:
    if context_width <= 0:
        return left_fits(area, left_width)
    return int(left_width) + FOOTER_CONTEXT_GAP_COLS + int(context_width) <= max(_area_width(area) - FOOTER_INDENT_COLS, 0)


def render_context_right(area: Any, buf: Any, context_line: str) -> tuple[int, str]:
    x = right_aligned_x(area, len(context_line))
    if isinstance(buf, list):
        buf.append((x, context_line))
    return x, context_line


def inset_footer_hint_area(area: Any) -> dict:
    return {"width": max(_area_width(area) - FOOTER_INDENT_COLS, 0), "height": _area_height(area)}


def render_footer_hint_items(items: Iterable[str]) -> str:
    return footer_hint_items_line(items)


def footer_from_props_lines(
    props: FooterProps,
    collaboration_mode_indicator: Optional[CollaborationModeIndicator] = None,
    show_cycle_hint: bool = False,
    show_shortcuts_hint: bool = False,
    show_queue_hint: bool = False,
) -> List[str]:
    if props.mode is FooterMode.HISTORY_SEARCH:
        return ["Search history"]
    if props.mode is FooterMode.QUIT_SHORTCUT_REMINDER:
        return [quit_shortcut_reminder_line(props)]
    if props.mode is FooterMode.ESC_HINT:
        return [esc_hint_line(props)]
    if props.mode is FooterMode.SHORTCUT_OVERLAY:
        return shortcut_overlay_lines(
            ShortcutsState(
                use_shift_enter_hint=props.use_shift_enter_hint,
                esc_backtrack_hint=props.esc_backtrack_hint,
                is_wsl=props.is_wsl,
                collaboration_modes_enabled=props.collaboration_modes_enabled,
                key_hints=props.key_hints,
            )
        )

    if shows_passive_footer_line(props, show_queue_hint):
        line = passive_footer_status_line(props)
        if line:
            return [line]

    state = LeftSideState(
        SummaryHintKind.QUEUE_MESSAGE if show_queue_hint else (
            SummaryHintKind.SHORTCUTS if show_shortcuts_hint else SummaryHintKind.NONE
        ),
        show_cycle_hint,
    )
    line = left_side_line(collaboration_mode_indicator, state, props.key_hints)
    return [line] if line else [""]


def passive_footer_status_line(props: FooterProps) -> Optional[str]:
    return status_line_right_indicator_line(
        props.status_line_value if props.status_line_enabled else None,
        props.active_agent_label,
    )


def terminal_idle_footer_text(data: TerminalIdleFooterData) -> str:
    """Return the terminal product path's passive footer text.

    Rust ownership: ``codex-tui::bottom_pane::footer`` formats passive footer
    status lines from caller-provided state.  The scrollback terminal runner
    supplies already-resolved model/cwd fields and leaves formatting here.
    """

    model_part = str(data.model_with_reasoning)
    if data.show_fast_status and " fast" not in f" {model_part.lower()} ":
        model_part = f"{model_part} fast"
    cwd_part = f"~\\{Path(data.cwd).name}" if data.cwd else ""
    return " · ".join(part for part in (model_part, cwd_part) if part)


def terminal_idle_footer_data_from_runtime(
    app_runtime: Any,
    *,
    model_with_reasoning: Callable[[Any], str],
    cwd: Callable[[Any], str | Path | None],
    show_fast_status: Callable[[Any], bool],
) -> TerminalIdleFooterData:
    """Build terminal idle footer inputs from runtime providers."""

    return TerminalIdleFooterData(
        model_with_reasoning=model_with_reasoning(app_runtime),
        cwd=cwd(app_runtime),
        show_fast_status=show_fast_status(app_runtime),
    )


def run_terminal_idle_footer_text(
    app_runtime: Any,
    *,
    model_with_reasoning: Callable[[Any], str],
    cwd: Callable[[Any], str | Path | None],
    show_fast_status: Callable[[Any], bool],
) -> str:
    """Return the terminal product path's idle footer text from runtime state.

    Rust ownership: ``bottom_pane::footer`` owns passive footer formatting;
    the terminal runner supplies provider callbacks rather than assembling
    footer data itself.
    """

    return terminal_idle_footer_text(
        terminal_idle_footer_data_from_runtime(
            app_runtime,
            model_with_reasoning=model_with_reasoning,
            cwd=cwd,
            show_fast_status=show_fast_status,
        )
    )


def run_terminal_idle_footer_text_from_runtime(app_runtime: Any) -> str:
    """Return passive footer text using the canonical TUI runtime providers."""

    from ..textual_runtime import (
        _runtime_cwd,
        _runtime_model_with_reasoning,
        _runtime_show_fast_status,
    )

    return run_terminal_idle_footer_text(
        app_runtime,
        model_with_reasoning=_runtime_model_with_reasoning,
        cwd=_runtime_cwd,
        show_fast_status=_runtime_show_fast_status,
    )


def shows_passive_footer_line(props: FooterProps, show_queue_hint: bool = False) -> bool:
    if show_queue_hint:
        return False
    return props.mode in {FooterMode.COMPOSER_EMPTY, FooterMode.COMPOSER_HAS_DRAFT} and bool(
        passive_footer_status_line(props)
    )


def uses_passive_footer_status_layout(props: FooterProps, show_queue_hint: bool = False) -> bool:
    return shows_passive_footer_line(props, show_queue_hint)


def footer_line_width(line: str) -> int:
    return len(str(line))


def footer_hint_items_width(items: Iterable[str]) -> int:
    return len(footer_hint_items_line(items))


def footer_hint_items_line(items: Iterable[str]) -> str:
    return "  ".join(str(item) for item in items if item)


def quit_shortcut_reminder_line(props: FooterProps) -> str:
    action = "interrupt" if props.is_task_running else "quit"
    return f"Press {props.quit_shortcut_key} again to {action}"


def esc_hint_line(props: FooterProps) -> str:
    if props.esc_backtrack_hint:
        return "esc again to edit previous message"
    return "esc esc to edit previous message"


def shortcut_overlay_lines(state: ShortcutsState) -> List[str]:
    entries = [entry for descriptor in SHORTCUTS if (entry := descriptor.overlay_entry(state)) is not None]
    return build_columns(entries) + ["", "customize shortcuts with /keymap"]


def build_columns(items: Iterable[str], columns: int = COLUMNS) -> list[str]:
    entries = [str(item) for item in items]
    if not entries:
        return []
    columns = max(int(columns), 1)
    rows = (len(entries) + columns - 1) // columns
    target_len = rows * columns
    entries.extend([""] * (target_len - len(entries)))
    widths = [0 for _ in range(columns)]
    for idx, entry in enumerate(entries):
        widths[idx % columns] = max(widths[idx % columns], len(entry))
    padding = [COLUMN_PADDING[idx] if idx < len(COLUMN_PADDING) else COLUMN_PADDING[-1] for idx in range(columns)]
    widths = [width + padding[idx] for idx, width in enumerate(widths)]
    lines: list[str] = []
    for row in range(rows):
        parts: list[str] = []
        for col in range(columns):
            idx = row * columns + col
            entry = entries[idx]
            parts.append(entry)
            if col < columns - 1:
                parts.append(" " * (max(widths[col] - len(entry), 0) + COLUMN_GAP))
        lines.append("".join(parts).rstrip())
    return lines


def _display_key(key: Union[KeyBinding, str]) -> str:
    if isinstance(key, KeyBinding):
        if not key.modifiers:
            return key.code.lower() if key.code == "Esc" else key.code
        return " + ".join((*key.modifiers, key.code))
    return str(key)


def context_window_line(percent: Optional[int] = None, used_tokens: Optional[int] = None) -> str:
    if percent is not None:
        return f"{percent}% context left"
    if used_tokens is not None:
        return f"{format_tokens_compact(used_tokens)} tokens"
    return ""


def format_tokens_compact(tokens: int) -> str:
    tokens = int(tokens)
    if abs(tokens) >= 1_000_000:
        return f"{tokens // 1_000_000}M"
    if abs(tokens) >= 1_000:
        return f"{tokens // 1_000}K"
    return str(tokens)


def _area_width(area: Any) -> int:
    if isinstance(area, int):
        return max(area, 0)
    if isinstance(area, dict):
        return max(int(area.get("width", 0)), 0)
    return max(int(getattr(area, "width", 0)), 0)


def _area_height(area: Any) -> int:
    if isinstance(area, dict):
        return max(int(area.get("height", 0)), 0)
    return max(int(getattr(area, "height", 1)), 0)


def _truncate_text(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if len(text) <= max_width:
        return text
    if max_width == 1:
        return "?"
    return text[: max_width - 1] + "?"


def _line_with_context(width: int, left: str, right: str) -> str:
    width = max(int(width), 0)
    if not right:
        return _truncate_text(left, width)
    if len(right) >= width:
        return _truncate_text(right, width)
    left_width = max(width - len(right) - FOOTER_CONTEXT_GAP_COLS, 0)
    left = _truncate_text(left, left_width)
    gap = " " * max(width - len(left) - len(right), FOOTER_CONTEXT_GAP_COLS)
    return (left + gap + right)[:width]


def snapshot_footer(name: str, props: FooterProps, width: int = 120) -> str:
    del name
    return "\n".join(render_footer_from_props({"width": width}, [], props, None, False, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running))


def snapshot_footer_with_context(name: str, props: FooterProps, percent: Optional[int] = None, used_tokens: Optional[int] = None, width: int = 120) -> str:
    del name
    left = snapshot_footer("", props, width).strip()
    return _line_with_context(width, left, context_window_line(percent, used_tokens))


def draw_footer_frame(terminal: Any, height: int, props: FooterProps, collaboration_mode_indicator: Optional[CollaborationModeIndicator], ide_context_active: bool, context_line: str) -> List[str]:
    del terminal, height
    left = footer_from_props_lines(props, collaboration_mode_indicator, True, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running)[0]
    right = ("IDE" if ide_context_active else context_line)
    return [_line_with_context(120, left, right)]


def snapshot_footer_with_mode_indicator(name: str, width: int, props: FooterProps, collaboration_mode_indicator: Optional[CollaborationModeIndicator]) -> str:
    del name
    left, show_context = single_line_footer_layout({"width": width}, 0, collaboration_mode_indicator, True, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running, props.key_hints)
    if left.kind == "Default":
        text = footer_from_props_lines(props, collaboration_mode_indicator, True, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running)[0]
    else:
        text = left.line or ""
    return _line_with_context(width, text, "" if show_context else "")


def snapshot_footer_with_mode_indicator_and_context(name: str, width: int, props: FooterProps, collaboration_mode_indicator: Optional[CollaborationModeIndicator], context_line_value: str) -> str:
    del name
    return render_footer_with_mode_indicator_and_context(width, props, collaboration_mode_indicator, context_line_value)


def render_footer_with_mode_indicator_and_context(width: int, props: FooterProps, collaboration_mode_indicator: Optional[CollaborationModeIndicator], context_line_value: str) -> str:
    left, show_context = single_line_footer_layout({"width": width}, len(context_line_value), collaboration_mode_indicator, True, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running, props.key_hints)
    context = context_line_value if show_context else ""
    status = passive_footer_status_line(props)
    if status and collaboration_mode_indicator is not None:
        left_width = max_left_width_for_right({"width": width}, len(context))
        text = _line_with_context(left_width, status, collaboration_mode_indicator.label(False))
        return _line_with_context(width, text, context)
    if left.kind == "Default":
        text = footer_from_props_lines(props, collaboration_mode_indicator, True, props.mode is FooterMode.COMPOSER_EMPTY, props.mode is FooterMode.COMPOSER_HAS_DRAFT and props.is_task_running)[0]
    else:
        text = left.line or ""
    return _line_with_context(width, text, context)


def snapshot_footer_with_indicators(name: str, width: int, props: FooterProps, collaboration_mode_indicator: Optional[CollaborationModeIndicator], ide_context_active: bool) -> str:
    del name
    return "\n".join(draw_footer_frame(None, 1, props, collaboration_mode_indicator, ide_context_active, context_window_line(None, None)))[:width]


def footer_snapshots(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    return bool(snapshot_footer("footer_shortcuts_default", FooterProps()))


def footer_status_line_truncates_to_keep_mode_indicator(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    props = FooterProps(
        mode=FooterMode.COMPOSER_EMPTY,
        collaboration_modes_enabled=True,
        status_line_value="Status line content that is definitely too long to fit alongside the mode label",
        status_line_enabled=True,
    )
    rendered = render_footer_with_mode_indicator_and_context(80, props, CollaborationModeIndicator.PLAN, context_window_line(50, None))
    return "Plan mode" in rendered and MODE_CYCLE_HINT not in rendered and "?" in rendered


def paste_image_shortcut_prefers_ctrl_alt_v_under_wsl(*args: Any, **kwargs: Any) -> bool:
    del args, kwargs
    descriptor = next(item for item in SHORTCUTS if item.id is ShortcutId.PASTE_IMAGE)
    return descriptor.binding_for(ShortcutsState(is_wsl=True)).key == ctrl_alt("v") and descriptor.binding_for(ShortcutsState(is_wsl=False)).key == ctrl("v")


__all__ = [
    "COLUMNS",
    "COLUMN_GAP",
    "COLUMN_PADDING",
    "CollaborationModeIndicator",
    "DisplayCondition",
    "FOOTER_CONTEXT_GAP_COLS",
    "FooterKeyHints",
    "FooterMode",
    "FooterProps",
    "GoalStatusIndicator",
    "KeyBinding",
    "LeftSideState",
    "MODE_CYCLE_HINT",
    "RUST_MODULE",
    "SHORTCUTS",
    "ShortcutBinding",
    "ShortcutDescriptor",
    "ShortcutId",
    "ShortcutsState",
    "SummaryHintKind",
    "SummaryLeft",
    "TerminalIdleFooterData",
    "alt",
    "build_columns",
    "can_show_left_with_context",
    "context_window_line",
    "ctrl",
    "ctrl_alt",
    "draw_footer_frame",
    "esc_hint_line",
    "esc_hint_mode",
    "footer_from_props_lines",
    "footer_height",
    "footer_hint_items_line",
    "footer_hint_items_width",
    "footer_line_width",
    "footer_snapshots",
    "footer_status_line_truncates_to_keep_mode_indicator",
    "goal_status_indicator_line",
    "inset_footer_hint_area",
    "left_fits",
    "left_side_line",
    "max_left_width_for_right",
    "mode_indicator_line",
    "passive_footer_status_line",
    "paste_image_shortcut_prefers_ctrl_alt_v_under_wsl",
    "plain",
    "quit_shortcut_reminder_line",
    "render_context_right",
    "render_footer_from_props",
    "render_footer_hint_items",
    "render_footer_line",
    "render_footer_with_mode_indicator_and_context",
    "reset_mode_after_activity",
    "right_aligned_x",
    "shift",
    "shortcut_overlay_lines",
    "shows_passive_footer_line",
    "side_conversation_context_line",
    "single_line_footer_layout",
    "snapshot_footer",
    "snapshot_footer_with_context",
    "snapshot_footer_with_indicators",
    "snapshot_footer_with_mode_indicator",
    "snapshot_footer_with_mode_indicator_and_context",
    "status_line_right_indicator_line",
    "terminal_idle_footer_data_from_runtime",
    "terminal_idle_footer_text",
    "run_terminal_idle_footer_text",
    "run_terminal_idle_footer_text_from_runtime",
    "toggle_shortcut_mode",
    "uses_passive_footer_status_layout",
]

