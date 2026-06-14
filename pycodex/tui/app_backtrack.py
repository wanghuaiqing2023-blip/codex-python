"""Backtrack transcript helpers for the TUI app.

Rust reference: codex-rs/tui/src/app_backtrack.rs.

The Rust module also owns App/Tui event routing.  This Python module ports the
module-local state containers and transcript trimming behavior with semantic
cell detection so it can be used without Rust trait objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, MutableSequence

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="app_backtrack", source="codex/codex-rs/tui/src/app_backtrack.rs")

NO_PREVIOUS_MESSAGE_TO_EDIT = "No previous message to edit."
USIZE_MAX = (1 << 64) - 1
U32_MAX = (1 << 32) - 1
BACKTRACK_ROLLBACK_ALREADY_IN_PROGRESS = "Backtrack rollback already in progress."


@dataclass
class BacktrackState:
    """Aggregates backtrack-related App state."""

    primed: bool = False
    base_id: Any | None = None
    nth_user_message: int = USIZE_MAX
    overlay_preview_active: bool = False
    pending_rollback: "PendingBacktrackRollback | None" = None


@dataclass
class BacktrackSelection:
    """A user-visible backtrack choice that can become a rollback request."""

    nth_user_message: int
    prefill: str = ""
    text_elements: list[Any] = field(default_factory=list)
    local_image_paths: list[Path] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)


@dataclass
class PendingBacktrackRollback:
    selection: BacktrackSelection
    thread_id: Any | None = None


@dataclass
class BacktrackRollbackPlan:
    """Semantic side-effect plan for Rust ``apply_backtrack_rollback``."""

    num_turns: int = 0
    pending_rollback: PendingBacktrackRollback | None = None
    remote_image_urls: list[str] = field(default_factory=list)
    composer_prefill: str = ""
    text_elements: list[Any] = field(default_factory=list)
    local_image_paths: list[Path] = field(default_factory=list)
    error_message: str | None = None

    @property
    def should_submit_rollback(self) -> bool:
        return self.pending_rollback is not None and self.num_turns > 0

    @property
    def should_set_composer_text(self) -> bool:
        return bool(
            self.composer_prefill
            or self.text_elements
            or self.local_image_paths
            or self.remote_image_urls
        )


@dataclass
class BacktrackRollbackCompletion:
    """Semantic result of a rollback success/failure event."""

    changed: bool = False
    apply_thread_rollback_turns: int | None = None
    ignored_for_thread_mismatch: bool = False
    user_count_after_trim: int | None = None


@dataclass
class BacktrackPrimePlan:
    """Semantic result of priming backtrack from the main view."""

    show_hint: bool = False


@dataclass
class BacktrackCloseOverlayPlan:
    """Semantic side-effect plan for closing the transcript overlay."""

    should_flush_deferred_history: bool = False
    reset_backtrack: bool = False


@dataclass
class BacktrackOverlaySyncPlan:
    """Semantic side-effect plan after transcript cells are trimmed."""

    replace_overlay_cells: bool = False
    clear_deferred_history_lines: bool = True
    highlighted_cell_index: int | None = None


@dataclass
class BacktrackEscKeyPlan:
    """Semantic decision for Rust ``handle_backtrack_esc_key``."""

    action: str = "noop"
    prime: BacktrackPrimePlan | None = None


@dataclass
class BacktrackOverlayEventPlan:
    """Semantic decision for Rust ``handle_backtrack_overlay_event``."""

    action: str = "forward"
    handled: bool = True


@dataclass
class BacktrackPreviewPlan:
    """Semantic side-effect plan for opening a backtrack preview."""

    action: str
    info_message: str | None = None
    clear_hint: bool = False
    schedule_frame: bool = False
    highlighted_cell_index: int | None = None


@dataclass
class SemanticHistoryCell:
    """Small test/support cell mirroring the history-cell type checks used by Rust."""

    kind: str
    message: str = ""
    text_elements: list[Any] = field(default_factory=list)
    local_image_paths: list[Path] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    stream_continuation: bool = False
    lines: list[str] = field(default_factory=list)


def trim_transcript_cells_to_nth_user(transcript_cells: MutableSequence[Any], nth_user_message: int) -> bool:
    if nth_user_message == USIZE_MAX:
        return False
    cut_idx = nth_user_position(transcript_cells, nth_user_message)
    if cut_idx is None:
        return False
    original_len = len(transcript_cells)
    del transcript_cells[cut_idx:]
    return len(transcript_cells) != original_len


def trim_transcript_cells_drop_last_n_user_turns(transcript_cells: MutableSequence[Any], num_turns: int) -> bool:
    if num_turns == 0:
        return False
    positions = list(user_positions_iter(transcript_cells))
    if not positions:
        return False
    first_user_idx = positions[0]
    turns_from_end = max(0, int(num_turns))
    if turns_from_end >= len(positions):
        cut_idx = first_user_idx
    else:
        cut_idx = positions[len(positions) - turns_from_end]
    original_len = len(transcript_cells)
    del transcript_cells[cut_idx:]
    return len(transcript_cells) != original_len


def user_count(cells: Iterable[Any]) -> int:
    return sum(1 for _ in user_positions_iter(cells))


def has_backtrack_target(cells: Iterable[Any]) -> bool:
    return user_count(cells) > 0


def nth_user_position(cells: Iterable[Any], nth: int) -> int | None:
    for index, cell_idx in enumerate(user_positions_iter(cells)):
        if index == nth:
            return cell_idx
    return None


def user_positions_iter(cells: Iterable[Any]) -> Iterator[int]:
    materialized = list(cells)
    start = 0
    for index, cell in enumerate(materialized):
        if _is_session_cell(cell):
            start = index + 1
    for index, cell in enumerate(materialized[start:], start):
        if _is_user_cell(cell):
            yield index


def agent_group_count(cells: Iterable[Any]) -> int:
    return sum(1 for _ in agent_group_positions_iter(cells))


def agent_group_positions_iter(cells: Iterable[Any]) -> Iterator[int]:
    materialized = list(cells)
    start = 0
    for index, cell in enumerate(materialized):
        if _is_session_cell(cell):
            start = index + 1
    for index, cell in enumerate(materialized[start:], start):
        if _is_agent_cell(cell) and not _is_stream_continuation(cell):
            yield index


def render_lines(lines: Iterable[Any]) -> list[str]:
    rendered: list[str] = []
    for line in lines:
        spans = getattr(line, "spans", None)
        if spans is not None:
            rendered.append("".join(str(getattr(span, "content", getattr(span, "text", span))) for span in spans))
        else:
            rendered.append(str(line))
    return rendered


def trim_transcript_for_first_user_drops_user_and_newer_cells() -> bool:
    cells = [user_cell("first user"), agent_cell("assistant")]
    changed = trim_transcript_cells_to_nth_user(cells, 0)
    return changed and cells == []


def trim_transcript_preserves_cells_before_selected_user() -> bool:
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("after", stream_continuation=True)]
    changed = trim_transcript_cells_to_nth_user(cells, 0)
    return changed and len(cells) == 1 and _is_agent_cell(cells[0]) and _message(cells[0]) == "intro"


def trim_transcript_for_later_user_keeps_prior_history() -> bool:
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("between", stream_continuation=True), user_cell("second"), agent_cell("tail", stream_continuation=True)]
    changed = trim_transcript_cells_to_nth_user(cells, 1)
    return changed and [_kind(cell) for cell in cells] == ["agent", "user", "agent"] and _message(cells[1]) == "first"


def trim_drop_last_n_user_turns_applies_rollback_semantics() -> bool:
    cells = [user_cell("first"), agent_cell("after first", stream_continuation=True), user_cell("second"), agent_cell("after second", stream_continuation=True)]
    changed = trim_transcript_cells_drop_last_n_user_turns(cells, 1)
    return changed and len(cells) == 2 and _message(cells[0]) == "first"


def trim_drop_last_n_user_turns_allows_overflow() -> bool:
    cells = [agent_cell("intro"), user_cell("first"), agent_cell("after", stream_continuation=True)]
    changed = trim_transcript_cells_drop_last_n_user_turns(cells, 2**32 - 1)
    return changed and len(cells) == 1 and _message(cells[0]) == "intro"


def agent_group_count_ignores_context_compacted_marker() -> bool:
    cells = [agent_cell("first"), info_cell("Context compacted"), agent_cell("second")]
    return agent_group_count(cells) == 2


def backtrack_target_requires_user_message() -> bool:
    cells = [agent_cell("assistant"), info_cell("Context compacted")]
    before = has_backtrack_target(cells)
    cells.append(user_cell("hello"))
    after = has_backtrack_target(cells)
    return before is False and after is True


def backtrack_unavailable_info_message_snapshot() -> str:
    return NO_PREVIOUS_MESSAGE_TO_EDIT


def reset_backtrack_state(state: BacktrackState) -> None:
    """Reset the module-local backtrack state fields.

    Rust also clears the ChatWidget Esc-backtrack hint from ``App``; that UI
    side effect is intentionally kept outside this pure state helper.
    """

    state.primed = False
    state.base_id = None
    state.nth_user_message = USIZE_MAX


def backtrack_selection(
    state: BacktrackState,
    thread_id: Any | None,
    transcript_cells: Iterable[Any],
    nth_user_message: int | None = None,
) -> BacktrackSelection | None:
    """Compute a backtrack selection without App/ChatWidget side effects."""

    if state.base_id is None or thread_id != state.base_id:
        return None

    nth = state.nth_user_message if nth_user_message is None else nth_user_message
    materialized = list(transcript_cells)
    cell_index = nth_user_position(materialized, nth)
    cell = materialized[cell_index] if cell_index is not None else None
    if cell is None or not _is_user_cell(cell):
        return BacktrackSelection(nth_user_message=nth)

    return BacktrackSelection(
        nth_user_message=nth,
        prefill=_message(cell),
        text_elements=list(getattr(cell, "text_elements", []) or []),
        local_image_paths=list(getattr(cell, "local_image_paths", []) or []),
        remote_image_urls=list(getattr(cell, "remote_image_urls", []) or []),
    )


def apply_backtrack_rollback_state(
    state: BacktrackState,
    selection: BacktrackSelection,
    transcript_cells: Iterable[Any],
    thread_id: Any | None,
) -> BacktrackRollbackPlan | None:
    """Plan and record a backtrack rollback without App/ChatWidget effects."""

    user_total = user_count(transcript_cells)
    if user_total == 0:
        return None

    if state.pending_rollback is not None:
        return BacktrackRollbackPlan(error_message=BACKTRACK_ROLLBACK_ALREADY_IN_PROGRESS)

    num_turns = user_total - selection.nth_user_message
    if num_turns <= 0:
        return None
    num_turns = min(num_turns, U32_MAX)

    pending = PendingBacktrackRollback(selection=selection, thread_id=thread_id)
    state.pending_rollback = pending
    return BacktrackRollbackPlan(
        num_turns=num_turns,
        pending_rollback=pending,
        remote_image_urls=list(selection.remote_image_urls),
        composer_prefill=selection.prefill,
        text_elements=list(selection.text_elements),
        local_image_paths=list(selection.local_image_paths),
    )


def handle_backtrack_rollback_succeeded_state(
    state: BacktrackState,
    transcript_cells: MutableSequence[Any],
    active_thread_id: Any | None,
    num_turns: int,
) -> BacktrackRollbackCompletion:
    """Apply Rust rollback-success state semantics without App side effects."""

    if state.pending_rollback is None:
        changed = trim_transcript_cells_drop_last_n_user_turns(transcript_cells, num_turns)
        return BacktrackRollbackCompletion(
            changed=changed,
            apply_thread_rollback_turns=num_turns,
            user_count_after_trim=user_count(transcript_cells) if changed else None,
        )

    pending = state.pending_rollback
    state.pending_rollback = None
    if pending.thread_id != active_thread_id:
        return BacktrackRollbackCompletion(ignored_for_thread_mismatch=True)

    changed = trim_transcript_cells_to_nth_user(
        transcript_cells,
        pending.selection.nth_user_message,
    )
    return BacktrackRollbackCompletion(
        changed=changed,
        user_count_after_trim=user_count(transcript_cells) if changed else None,
    )


def handle_backtrack_rollback_failed_state(state: BacktrackState) -> None:
    """Clear the pending rollback guard after a failed rollback event."""

    state.pending_rollback = None


def next_backtrack_selection_index(current: int, user_total: int) -> int:
    """Return the next older user-message selection index."""

    if user_total <= 0:
        return current
    last_index = user_total - 1
    if current == USIZE_MAX:
        return last_index
    if current == 0:
        return 0
    return min(current - 1, last_index)


def next_forward_backtrack_selection_index(current: int, user_total: int) -> int:
    """Return the next newer user-message selection index."""

    if user_total <= 0:
        return current
    last_index = user_total - 1
    if current == USIZE_MAX:
        return last_index
    return min(current + 1, last_index)


def apply_backtrack_selection_index(
    state: BacktrackState,
    transcript_cells: Iterable[Any],
    nth_user_message: int,
) -> int | None:
    """Apply a computed selection index and return the highlighted cell index."""

    cell_index = nth_user_position(transcript_cells, nth_user_message)
    if cell_index is None:
        state.nth_user_message = USIZE_MAX
        return None
    state.nth_user_message = nth_user_message
    return cell_index


def confirm_backtrack_from_main_state(
    state: BacktrackState,
    thread_id: Any | None,
    transcript_cells: Iterable[Any],
) -> BacktrackSelection | None:
    """Confirm a primed main-view backtrack and reset local state."""

    selection = backtrack_selection(state, thread_id, transcript_cells, state.nth_user_message)
    reset_backtrack_state(state)
    return selection


def prime_backtrack_state(
    state: BacktrackState,
    thread_id: Any | None,
    transcript_cells: Iterable[Any],
) -> BacktrackPrimePlan:
    """Prime backtrack mode and report whether the composer hint should show."""

    state.primed = True
    state.nth_user_message = USIZE_MAX
    state.base_id = thread_id
    return BacktrackPrimePlan(show_hint=has_backtrack_target(transcript_cells))


def close_transcript_overlay_state(
    state: BacktrackState,
    has_deferred_history_lines: bool = False,
) -> BacktrackCloseOverlayPlan:
    """Close overlay-local backtrack state without terminal side effects."""

    was_backtrack = state.overlay_preview_active
    state.overlay_preview_active = False
    if was_backtrack:
        reset_backtrack_state(state)
    return BacktrackCloseOverlayPlan(
        should_flush_deferred_history=has_deferred_history_lines,
        reset_backtrack=was_backtrack,
    )


def sync_overlay_after_transcript_trim_state(
    state: BacktrackState,
    transcript_cells: Iterable[Any],
    overlay_open: bool = False,
) -> BacktrackOverlaySyncPlan:
    """Keep overlay/backtrack selection state aligned after transcript trim."""

    highlighted_cell_index: int | None = None
    if state.overlay_preview_active:
        total_users = user_count(transcript_cells)
        next_selection = USIZE_MAX if total_users == 0 else min(state.nth_user_message, total_users - 1)
        highlighted_cell_index = apply_backtrack_selection_index(
            state,
            transcript_cells,
            next_selection,
        )
    return BacktrackOverlaySyncPlan(
        replace_overlay_cells=overlay_open,
        clear_deferred_history_lines=True,
        highlighted_cell_index=highlighted_cell_index,
    )


def handle_backtrack_esc_key_state(
    state: BacktrackState,
    *,
    composer_is_empty: bool,
    overlay_open: bool,
    thread_id: Any | None,
    transcript_cells: Iterable[Any],
) -> BacktrackEscKeyPlan:
    """Plan the global Esc backtrack behavior without TUI side effects."""

    if not composer_is_empty:
        return BacktrackEscKeyPlan(action="noop")

    if not state.primed:
        return BacktrackEscKeyPlan(
            action="prime",
            prime=prime_backtrack_state(state, thread_id, transcript_cells),
        )

    if not overlay_open:
        return BacktrackEscKeyPlan(action="open_preview")

    if state.overlay_preview_active:
        return BacktrackEscKeyPlan(action="step_backtrack")

    return BacktrackEscKeyPlan(action="noop")


def handle_backtrack_overlay_event_state(
    state: BacktrackState,
    *,
    event_code: str,
    event_kind: str = "press",
) -> BacktrackOverlayEventPlan:
    """Plan transcript-overlay backtrack event routing without TUI effects."""

    is_press_or_repeat = event_kind in {"press", "repeat"}
    if state.overlay_preview_active:
        if event_code in {"esc", "left"} and is_press_or_repeat:
            action = "step_backtrack" if state.base_id is not None else "forward"
            return BacktrackOverlayEventPlan(action=action)
        if event_code == "right" and is_press_or_repeat:
            action = "step_forward" if state.base_id is not None else "forward"
            return BacktrackOverlayEventPlan(action=action)
        if event_code == "enter" and event_kind == "press":
            return BacktrackOverlayEventPlan(action="confirm")
        return BacktrackOverlayEventPlan(action="forward")

    if event_code == "esc" and is_press_or_repeat:
        return BacktrackOverlayEventPlan(action="begin_preview")
    return BacktrackOverlayEventPlan(action="forward")


def open_backtrack_preview_state(state: BacktrackState, transcript_cells: list[Any]) -> BacktrackPreviewPlan:
    """Plan App::backtrack behavior for opening the transcript preview overlay."""

    if not has_backtrack_target(transcript_cells):
        reset_backtrack_state(state)
        return BacktrackPreviewPlan(
            action="no_target",
            info_message=NO_PREVIOUS_MESSAGE_TO_EDIT,
            schedule_frame=True,
        )

    state.overlay_preview_active = True
    next_selection = next_backtrack_selection_index(state.nth_user_message, user_count(transcript_cells))
    highlighted_cell_index = apply_backtrack_selection_index(state, transcript_cells, next_selection)
    return BacktrackPreviewPlan(
        action="open_preview",
        clear_hint=True,
        schedule_frame=True,
        highlighted_cell_index=highlighted_cell_index,
    )


def begin_overlay_backtrack_preview_state(
    state: BacktrackState, thread_id: Any, transcript_cells: list[Any]
) -> BacktrackPreviewPlan:
    """Plan BeginBacktrack handling while the transcript overlay is active."""

    if not has_backtrack_target(transcript_cells):
        return BacktrackPreviewPlan(
            action="no_target_close_overlay",
            info_message=NO_PREVIOUS_MESSAGE_TO_EDIT,
            schedule_frame=True,
        )

    state.primed = True
    state.base_id = thread_id
    state.overlay_preview_active = True
    latest_user = user_count(transcript_cells) - 1
    highlighted_cell_index = apply_backtrack_selection_index(state, transcript_cells, latest_user)
    return BacktrackPreviewPlan(
        action="begin_preview",
        schedule_frame=True,
        highlighted_cell_index=highlighted_cell_index,
    )


def user_cell(message: str, **kwargs: Any) -> SemanticHistoryCell:
    return SemanticHistoryCell("user", message=message, **kwargs)


def agent_cell(message: str, *, stream_continuation: bool = False, **kwargs: Any) -> SemanticHistoryCell:
    return SemanticHistoryCell("agent", message=message, stream_continuation=stream_continuation, lines=[message], **kwargs)


def session_cell(message: str = "session") -> SemanticHistoryCell:
    return SemanticHistoryCell("session", message=message)


def info_cell(message: str) -> SemanticHistoryCell:
    return SemanticHistoryCell("info", message=message, lines=[message])


def _kind(cell: Any) -> str:
    explicit = getattr(cell, "kind", None) or getattr(cell, "cell_type", None) or getattr(cell, "type", None)
    if explicit is not None:
        return str(explicit).lower()
    name = cell.__class__.__name__.lower()
    if "sessioninfo" in name or name == "session":
        return "session"
    if "userhistory" in name or name.startswith("user"):
        return "user"
    if "agentmessage" in name or name.startswith("agent"):
        return "agent"
    return name


def _message(cell: Any) -> str:
    return str(getattr(cell, "message", getattr(cell, "text", "")))


def _is_session_cell(cell: Any) -> bool:
    return _kind(cell) in {"session", "sessioninfo", "session_info"}


def _is_user_cell(cell: Any) -> bool:
    return _kind(cell) in {"user", "userhistory", "user_history"}


def _is_agent_cell(cell: Any) -> bool:
    return _kind(cell) in {"agent", "agentmessage", "agent_message"}


def _is_stream_continuation(cell: Any) -> bool:
    value = getattr(cell, "stream_continuation", None)
    if value is None:
        value = getattr(cell, "is_stream_continuation", False)
    return bool(value() if callable(value) else value)


__all__ = [
    "BacktrackSelection",
    "BacktrackState",
    "BacktrackRollbackCompletion",
    "BacktrackRollbackPlan",
    "BacktrackPrimePlan",
    "BacktrackCloseOverlayPlan",
    "BacktrackOverlaySyncPlan",
    "BacktrackEscKeyPlan",
    "BacktrackOverlayEventPlan",
    "BacktrackPreviewPlan",
    "BACKTRACK_ROLLBACK_ALREADY_IN_PROGRESS",
    "NO_PREVIOUS_MESSAGE_TO_EDIT",
    "PendingBacktrackRollback",
    "RUST_MODULE",
    "SemanticHistoryCell",
    "U32_MAX",
    "USIZE_MAX",
    "agent_cell",
    "agent_group_count",
    "agent_group_count_ignores_context_compacted_marker",
    "agent_group_positions_iter",
    "apply_backtrack_rollback_state",
    "backtrack_target_requires_user_message",
    "backtrack_selection",
    "backtrack_unavailable_info_message_snapshot",
    "begin_overlay_backtrack_preview_state",
    "confirm_backtrack_from_main_state",
    "close_transcript_overlay_state",
    "sync_overlay_after_transcript_trim_state",
    "has_backtrack_target",
    "handle_backtrack_rollback_failed_state",
    "handle_backtrack_rollback_succeeded_state",
    "handle_backtrack_esc_key_state",
    "handle_backtrack_overlay_event_state",
    "info_cell",
    "apply_backtrack_selection_index",
    "nth_user_position",
    "next_backtrack_selection_index",
    "next_forward_backtrack_selection_index",
    "open_backtrack_preview_state",
    "prime_backtrack_state",
    "render_lines",
    "reset_backtrack_state",
    "session_cell",
    "trim_drop_last_n_user_turns_allows_overflow",
    "trim_drop_last_n_user_turns_applies_rollback_semantics",
    "trim_transcript_cells_drop_last_n_user_turns",
    "trim_transcript_cells_to_nth_user",
    "trim_transcript_for_first_user_drops_user_and_newer_cells",
    "trim_transcript_for_later_user_keeps_prior_history",
    "trim_transcript_preserves_cells_before_selected_user",
    "user_cell",
    "user_count",
    "user_positions_iter",
]
