"""Semantic footer helpers for Rust ``bottom_pane/footer.rs``.

The Rust module is mostly pure formatting plus ratatui rendering.  Python keeps
the formatting/state-machine contract as strings and lightweight dataclasses;
exact cell rendering and the full width-collapse algorithm stay renderer
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::footer",
    source="codex/codex-rs/tui/src/bottom_pane/footer.rs",
)

MODE_CYCLE_HINT = "shift+tab to cycle"
FOOTER_CONTEXT_GAP_COLS = 1
FOOTER_INDENT_COLS = 2
COLUMNS = 3
COLUMN_PADDING = 2
COLUMN_GAP = 2


@dataclass(frozen=True)
class KeyBinding:
    code: str
    modifiers: tuple[str, ...] = ()

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
    usage: str | None = None

    @classmethod
    def Active(cls, usage: str | None = None) -> "GoalStatusIndicator":
        return cls("Active", usage)

    @classmethod
    def BudgetLimited(cls, usage: str | None = None) -> "GoalStatusIndicator":
        return cls("BudgetLimited", usage)

    @classmethod
    def Complete(cls, usage: str | None = None) -> "GoalStatusIndicator":
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
    toggle_shortcuts: KeyBinding | None = None
    queue: KeyBinding | None = None
    insert_newline: KeyBinding | None = None
    external_editor: KeyBinding | None = None
    edit_previous: KeyBinding | None = None
    show_transcript: KeyBinding | None = None
    history_search: KeyBinding | None = None
    reasoning_down: KeyBinding | None = None
    reasoning_up: KeyBinding | None = None

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
    status_line_value: str | None = None
    status_line_enabled: bool = False
    key_hints: FooterKeyHints = FooterKeyHints.default_bindings()
    active_agent_label: str | None = None


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
    line: str | None = None

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
    PASTE_IMAGE = "PasteImage"
    INSERT_NEWLINE = "InsertNewline"
    EXTERNAL_EDITOR = "ExternalEditor"
    EDIT_PREVIOUS = "EditPrevious"
    SHOW_TRANSCRIPT = "ShowTranscript"
    HISTORY_SEARCH = "HistorySearch"


@dataclass(frozen=True)
class ShortcutBinding:
    key: KeyBinding

    def matches(self, key: KeyBinding | str) -> bool:
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

    def binding_for(self, state: ShortcutsState) -> ShortcutBinding | None:
        if self.id is ShortcutId.PASTE_IMAGE:
            return ShortcutBinding(ctrl_alt("v") if state.is_wsl else ctrl("v"))
        if self.id is ShortcutId.INSERT_NEWLINE:
            key = shift("Enter") if state.use_shift_enter_hint else state.key_hints.insert_newline
            return None if key is None else ShortcutBinding(key)
        mapping = {
            ShortcutId.EXTERNAL_EDITOR: state.key_hints.external_editor,
            ShortcutId.EDIT_PREVIOUS: state.key_hints.edit_previous,
            ShortcutId.SHOW_TRANSCRIPT: state.key_hints.show_transcript,
            ShortcutId.HISTORY_SEARCH: state.key_hints.history_search,
        }
        key = mapping.get(self.id)
        return None if key is None else ShortcutBinding(key)

    def overlay_entry(self, state: ShortcutsState) -> str | None:
        binding = self.binding_for(state)
        if binding is None:
            return None
        return f"{binding.key} {self.description}"


SHORTCUTS = [
    ShortcutDescriptor(ShortcutId.PASTE_IMAGE, "paste image"),
    ShortcutDescriptor(ShortcutId.INSERT_NEWLINE, "insert newline"),
    ShortcutDescriptor(ShortcutId.EXTERNAL_EDITOR, "open editor"),
    ShortcutDescriptor(ShortcutId.EDIT_PREVIOUS, "edit previous message"),
    ShortcutDescriptor(ShortcutId.SHOW_TRANSCRIPT, "show transcript"),
    ShortcutDescriptor(ShortcutId.HISTORY_SEARCH, "search history"),
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
    collaboration_mode_indicator: CollaborationModeIndicator | None = None,
    show_cycle_hint: bool = False,
    show_shortcuts_hint: bool = False,
    show_queue_hint: bool = False,
) -> list[str]:
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
    collaboration_mode_indicator: CollaborationModeIndicator | None,
    state: LeftSideState,
    key_hints: FooterKeyHints,
) -> str:
    parts: list[str] = []
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
    collaboration_mode_indicator: CollaborationModeIndicator | None,
    show_cycle_hint: bool,
    show_shortcuts_hint: bool,
    show_queue_hint: bool,
    key_hints: FooterKeyHints,
) -> tuple[SummaryLeft, bool]:
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
    usage = f" {indicator.usage}" if indicator.usage else ""
    labels = {
        "Active": "Goal active",
        "Paused": "Goal paused",
        "Blocked": "Goal blocked",
        "UsageLimited": "Goal usage limited",
        "BudgetLimited": "Goal budget limited",
        "Complete": "Goal complete",
    }
    return labels.get(indicator.kind, indicator.kind) + usage


def status_line_right_indicator_line(status_line: str | None, active_agent_label: str | None = None) -> str | None:
    if status_line and active_agent_label:
        return f"{status_line} - {active_agent_label}"
    return status_line or active_agent_label


def side_conversation_context_line(side_label: str | None = None) -> str | None:
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


def inset_footer_hint_area(area: Any) -> dict[str, int]:
    return {"width": max(_area_width(area) - FOOTER_INDENT_COLS, 0), "height": _area_height(area)}


def render_footer_hint_items(items: Iterable[str]) -> str:
    return footer_hint_items_line(items)


def footer_from_props_lines(
    props: FooterProps,
    collaboration_mode_indicator: CollaborationModeIndicator | None = None,
    show_cycle_hint: bool = False,
    show_shortcuts_hint: bool = False,
    show_queue_hint: bool = False,
) -> list[str]:
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


def passive_footer_status_line(props: FooterProps) -> str | None:
    return status_line_right_indicator_line(
        props.status_line_value if props.status_line_enabled else None,
        props.active_agent_label,
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
        return "Press Esc again to go back"
    return "Press Esc again to clear"


def shortcut_overlay_lines(state: ShortcutsState) -> list[str]:
    return [entry for descriptor in SHORTCUTS if (entry := descriptor.overlay_entry(state)) is not None]


def build_columns(items: Iterable[str], columns: int = COLUMNS) -> list[list[str]]:
    out = [[] for _ in range(max(columns, 1))]
    for idx, item in enumerate(items):
        out[idx % len(out)].append(str(item))
    return out


def context_window_line(percent: int | None = None, used_tokens: int | None = None) -> str:
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


def snapshot_footer(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "snapshot_footer")


def snapshot_footer_with_context(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "snapshot_footer_with_context")


def draw_footer_frame(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "draw_footer_frame")


def snapshot_footer_with_mode_indicator(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "snapshot_footer_with_mode_indicator")


def snapshot_footer_with_mode_indicator_and_context(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "snapshot_footer_with_mode_indicator_and_context")


def render_footer_with_mode_indicator_and_context(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_footer_with_mode_indicator_and_context")


def snapshot_footer_with_indicators(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "snapshot_footer_with_indicators")


def footer_snapshots(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "footer_snapshots")


def footer_status_line_truncates_to_keep_mode_indicator(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "footer_status_line_truncates_to_keep_mode_indicator")


def paste_image_shortcut_prefers_ctrl_alt_v_under_wsl(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "paste_image_shortcut_prefers_ctrl_alt_v_under_wsl")


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
    "toggle_shortcut_mode",
    "uses_passive_footer_status_layout",
]
