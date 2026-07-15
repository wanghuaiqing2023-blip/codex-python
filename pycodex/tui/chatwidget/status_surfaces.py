"""Status-surface pure helpers for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/status_surfaces.rs``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
import os
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO, TypeVar

from .._porting import RustTuiModule
from ..bottom_pane.status_line_setup import StatusLineItem
from ..bottom_pane.title_setup import TerminalTitleItem
from ..custom_terminal import clear_inline_status_line, write_inline_status_line
from ..status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay
from ..terminal_title import clear_terminal_title, set_terminal_title
from .rate_limits import get_limits_duration
from .status_state import TerminalTitleStatusKind

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::status_surfaces",
    source="codex/codex-rs/tui/src/chatwidget/status_surfaces.rs",
    status="complete",
)

DEFAULT_STATUS_LINE_ITEMS = ("model-with-reasoning", "current-dir")
DEFAULT_TERMINAL_TITLE_ITEMS = ("activity", "project-name")
TERMINAL_LIVE_STATUS_PREFIX = "\u2022 "
TERMINAL_LIVE_STATUS_DETAIL_PREFIX = " \u2514 "
TERMINAL_TURN_INTERRUPT_HINT = "esc to interrupt"

TERMINAL_TITLE_SPINNER_FRAMES = ("⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈", "⠐", "⠠")
TERMINAL_TITLE_SPINNER_INTERVAL = timedelta(milliseconds=100)
TERMINAL_TITLE_ACTION_REQUIRED_INTERVAL = timedelta(seconds=1)
TERMINAL_TITLE_ACTION_REQUIRED_PREFIX = "[ ! ] Action Required"
TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN = "[ . ] Action Required"

T = TypeVar("T")


@dataclass(frozen=True)
class StatusSurfaceSelections:
    """Parsed status-surface configuration for one refresh pass."""

    status_line_items: tuple[StatusLineItem, ...] = ()
    invalid_status_line_items: tuple[str, ...] = ()
    terminal_title_items: tuple[TerminalTitleItem, ...] = ()
    invalid_terminal_title_items: tuple[str, ...] = ()

    def uses_git_branch(self) -> bool:
        return (
            StatusLineItem.GIT_BRANCH in self.status_line_items
            or TerminalTitleItem.GIT_BRANCH in self.terminal_title_items
        )

    def uses_git_summary(self) -> bool:
        return (
            StatusLineItem.PULL_REQUEST_NUMBER in self.status_line_items
            or StatusLineItem.BRANCH_CHANGES in self.status_line_items
        )


@dataclass(frozen=True)
class CachedProjectRootName:
    cwd: Path
    root_name: str | None


def parse_status_line_items_with_invalids(ids: Iterable[Any]) -> tuple[list[StatusLineItem], list[str]]:
    return parse_items_with_invalids(ids, StatusLineItem.parse)


def parse_terminal_title_items_with_invalids(ids: Iterable[Any]) -> tuple[list[TerminalTitleItem], list[str]]:
    return parse_items_with_invalids(ids, TerminalTitleItem.from_id)


def status_surface_selections(
    status_line_ids: Iterable[Any] | None = None,
    terminal_title_ids: Iterable[Any] | None = None,
) -> StatusSurfaceSelections:
    status_items, invalid_status = parse_status_line_items_with_invalids(
        DEFAULT_STATUS_LINE_ITEMS if status_line_ids is None else status_line_ids
    )
    title_items, invalid_title = parse_terminal_title_items_with_invalids(
        DEFAULT_TERMINAL_TITLE_ITEMS if terminal_title_ids is None else terminal_title_ids
    )
    return StatusSurfaceSelections(
        status_line_items=tuple(status_items),
        invalid_status_line_items=tuple(invalid_status),
        terminal_title_items=tuple(title_items),
        invalid_terminal_title_items=tuple(invalid_title),
    )


def five_hour_status_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    return (
        find_primary_codex_window(snapshot, "5h")
        or secondary_window_with_label_when_weekly_is_available(snapshot, "5h")
        or non_weekly_primary_window(snapshot)
        or non_weekly_secondary_window_when_primary_is_weekly(snapshot)
    )


def weekly_status_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    return find_codex_window(snapshot, "weekly") or (
        (snapshot.secondary, True) if snapshot.secondary is not None else None
    )


def find_codex_window(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is not None and matches_window_label(snapshot.primary, label):
        return (snapshot.primary, False)
    if snapshot.secondary is not None and matches_window_label(snapshot.secondary, label):
        return (snapshot.secondary, True)
    return None


def find_primary_codex_window(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is not None and matches_window_label(snapshot.primary, label):
        return (snapshot.primary, False)
    return None


def secondary_window_with_label_when_weekly_is_available(
    snapshot: RateLimitSnapshotDisplay,
    label: str,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if find_codex_window(snapshot, "weekly") is None:
        return None
    if snapshot.secondary is not None and matches_window_label(snapshot.secondary, label):
        return (snapshot.secondary, True)
    return None


def non_weekly_primary_window(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is None or matches_window_label(snapshot.primary, "weekly"):
        return None
    return (snapshot.primary, False)


def non_weekly_secondary_window_when_primary_is_weekly(
    snapshot: RateLimitSnapshotDisplay,
) -> tuple[RateLimitWindowDisplay, bool] | None:
    if snapshot.primary is None or not matches_window_label(snapshot.primary, "weekly"):
        return None
    if snapshot.secondary is None or matches_window_label(snapshot.secondary, "weekly"):
        return None
    return (snapshot.secondary, True)


def matches_window_label(window: RateLimitWindowDisplay, label: str) -> bool:
    minutes = window.window_minutes
    if minutes is None:
        return False
    return get_limits_duration(minutes) == label


def truncate_terminal_title_part(value: str, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if max_chars == 0:
        return ""
    graphemes = _graphemes(value)
    head = "".join(graphemes[:max_chars])
    if len(graphemes) <= max_chars or max_chars <= 3:
        return head
    return "".join(graphemes[: max_chars - 3]) + "..."


def terminal_title_spinner_frame_at(elapsed: timedelta) -> str:
    frame_index = int(elapsed.total_seconds() * 1000) // int(
        TERMINAL_TITLE_SPINNER_INTERVAL.total_seconds() * 1000
    )
    return TERMINAL_TITLE_SPINNER_FRAMES[frame_index % len(TERMINAL_TITLE_SPINNER_FRAMES)]


def action_required_terminal_title_prefix_at(
    elapsed: timedelta,
    animations: bool = True,
) -> str:
    if not animations:
        return TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
    phase = int(elapsed.total_seconds()) % 2
    return (
        TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
        if phase == 0
        else TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN
    )


def run_state_status_text(
    terminal_title_status_kind: TerminalTitleStatusKind | str,
    *,
    task_running: bool,
    mcp_startup_active: bool = False,
) -> str:
    """Compute Rust ``ChatWidget::run_state_status_text``.

    Rust source: ``codex-tui/src/chatwidget/status_surfaces.rs``. Startup
    takes precedence, idle state renders ``Ready``, and running state maps the
    compact terminal-title bucket to the status-line label.
    """

    if mcp_startup_active:
        return "Starting"
    kind = _terminal_title_status_kind(terminal_title_status_kind)
    if not task_running:
        return "Ready"
    if kind is TerminalTitleStatusKind.WaitingForBackgroundTerminal:
        return "Waiting"
    if kind is TerminalTitleStatusKind.Thinking:
        return "Thinking"
    return "Working"


def terminal_live_status_text(header: str, details: str | None = None) -> str:
    """Build the transient terminal status surface text.

    Rust ``chatwidget::status_surfaces`` owns the status text presented by the
    bottom pane/status indicator; terminal runtime only decides where to write
    the live surface.
    """

    text = f"{TERMINAL_LIVE_STATUS_PREFIX}{header}"
    if details:
        text = f"{text}{TERMINAL_LIVE_STATUS_DETAIL_PREFIX}{details}"
    return text


@dataclass(frozen=True)
class TerminalLiveStatusSurface:
    """Runtime live-status state for the real-terminal bottom pane.

    Rust ``chatwidget::status_surfaces`` owns the status text and refresh
    state.  The Python terminal adapter may ask this state for bottom-pane
    footprint rows, but it must not own the live-status transition semantics.
    """

    active: bool = False
    text: str | None = None

    @classmethod
    def inactive(cls) -> "TerminalLiveStatusSurface":
        return cls(False, None)

    @classmethod
    def active_status(cls, text: str | None = None) -> "TerminalLiveStatusSurface":
        return cls(True, text)

    @property
    def footprint_active(self) -> bool:
        return bool(self.active and self.text)

    @property
    def render_text(self) -> str | None:
        return self.text if self.active else None

    def rows_for_size(self, size: os.terminal_size) -> list[int]:
        from ..bottom_pane.terminal_footprint import bottom_pane_rows_for_size

        return bottom_pane_rows_for_size(size, live_status_active=self.footprint_active)


@dataclass(frozen=True)
class TerminalLiveStatusTransition:
    previous: TerminalLiveStatusSurface
    current: TerminalLiveStatusSurface


@dataclass(frozen=True)
class TerminalLiveStatusProjection:
    """Terminal row projection for a live-status string."""

    line: str | None


@dataclass(frozen=True)
class TerminalLiveStatusActionPlan:
    """Terminal side-effect plan for live-status surface changes."""

    transition: TerminalLiveStatusTransition
    check_resize: bool = False
    render_bottom_pane: bool = False
    flush_writer: bool = False
    inline_status_text: str | None = None
    clear_inline_status: bool = False

    @property
    def changed(self) -> bool:
        return self.transition.previous != self.transition.current


def terminal_live_status_projection(
    text: str | None,
    columns: int,
) -> TerminalLiveStatusProjection:
    """Project live status text into the terminal bottom-pane row."""

    if text is None:
        return TerminalLiveStatusProjection(None)
    return TerminalLiveStatusProjection(str(text)[: max(0, int(columns) - 1)])


def terminal_live_status_transition_to_status(
    previous: TerminalLiveStatusSurface,
    text: str | None = None,
) -> TerminalLiveStatusTransition:
    """Return the live-status transition for showing status."""

    return TerminalLiveStatusTransition(
        previous=previous,
        current=TerminalLiveStatusSurface.active_status(text),
    )


def terminal_live_status_transition_to_inactive(
    previous: TerminalLiveStatusSurface,
) -> TerminalLiveStatusTransition:
    """Return the live-status transition for hiding status."""

    return TerminalLiveStatusTransition(
        previous=previous,
        current=TerminalLiveStatusSurface.inactive(),
    )


def terminal_live_status_show_plan(
    previous: TerminalLiveStatusSurface,
    text: str,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
) -> TerminalLiveStatusActionPlan:
    """Plan live-status show/update side effects for the terminal product path."""

    transition = terminal_live_status_transition_to_status(previous, text)
    if stdin_is_terminal:
        return TerminalLiveStatusActionPlan(
            transition=transition,
            check_resize=layout_active,
            render_bottom_pane=True,
        )
    return TerminalLiveStatusActionPlan(
        transition=transition,
        inline_status_text=text,
        flush_writer=True,
    )


def terminal_live_status_hide_plan(
    previous: TerminalLiveStatusSurface,
    *,
    stdin_is_terminal: bool,
    redraw_bottom_pane: bool = True,
) -> TerminalLiveStatusActionPlan:
    """Plan live-status hide side effects for the terminal product path."""

    transition = terminal_live_status_transition_to_inactive(previous)
    if not previous.active:
        return TerminalLiveStatusActionPlan(transition=transition)
    if stdin_is_terminal:
        return TerminalLiveStatusActionPlan(
            transition=transition,
            render_bottom_pane=redraw_bottom_pane,
            flush_writer=not redraw_bottom_pane,
        )
    return TerminalLiveStatusActionPlan(
        transition=transition,
        clear_inline_status=True,
        flush_writer=True,
    )


def run_terminal_live_status_action_plan(
    writer: TextIO,
    plan: TerminalLiveStatusActionPlan,
    *,
    render_bottom_pane: Callable[[], None],
) -> None:
    """Execute terminal side effects selected by a live-status action plan."""

    if plan.render_bottom_pane:
        render_bottom_pane()
        return
    if plan.inline_status_text is not None:
        write_inline_status_line(writer, plan.inline_status_text)
    if plan.clear_inline_status:
        clear_inline_status_line(writer)
    if plan.flush_writer:
        _flush_writer(writer)


def run_terminal_live_status_show(
    writer: TextIO,
    previous: TerminalLiveStatusSurface,
    text: str,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: Callable[[], None],
    render_bottom_pane: Callable[[], None],
    apply_state: Callable[[TerminalLiveStatusSurface], None] | None = None,
) -> TerminalLiveStatusSurface:
    """Show/update live status and return the new bottom-pane surface state."""

    plan = terminal_live_status_show_plan(
        previous,
        text,
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
    )
    if plan.check_resize:
        check_resize()
    if apply_state is not None:
        apply_state(plan.transition.current)
    run_terminal_live_status_action_plan(
        writer,
        plan,
        render_bottom_pane=render_bottom_pane,
    )
    return plan.transition.current


def run_terminal_live_status_hide(
    writer: TextIO,
    previous: TerminalLiveStatusSurface,
    *,
    stdin_is_terminal: bool,
    redraw_bottom_pane: bool = True,
    render_bottom_pane: Callable[[], None],
    apply_state: Callable[[TerminalLiveStatusSurface], None] | None = None,
) -> TerminalLiveStatusSurface:
    """Hide live status and return the new bottom-pane surface state."""

    plan = terminal_live_status_hide_plan(
        previous,
        stdin_is_terminal=stdin_is_terminal,
        redraw_bottom_pane=redraw_bottom_pane,
    )
    if not plan.changed:
        return plan.transition.current
    if apply_state is not None:
        apply_state(plan.transition.current)
    run_terminal_live_status_action_plan(
        writer,
        plan,
        render_bottom_pane=render_bottom_pane,
    )
    return plan.transition.current


def run_terminal_live_status_text_show(
    writer: TextIO,
    previous: TerminalLiveStatusSurface,
    header: str,
    details: str | None = None,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: Callable[[], None],
    render_bottom_pane: Callable[[], None],
    apply_state: Callable[[TerminalLiveStatusSurface], None] | None = None,
) -> TerminalLiveStatusSurface:
    """Build and show a transient live-status surface.

    Rust ``chatwidget::status_surfaces`` owns the status text refresh boundary;
    ``bottom_pane`` still owns the terminal footprint and repaint effects.
    """

    return run_terminal_live_status_show(
        writer,
        previous,
        terminal_live_status_text(header, details),
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=check_resize,
        render_bottom_pane=render_bottom_pane,
        apply_state=apply_state,
    )


def terminal_turn_status_header(elapsed_seconds: int) -> str:
    """Return the active-turn status header used by the terminal product path."""

    return f"Working ({max(0, int(elapsed_seconds))}s \u2022 {TERMINAL_TURN_INTERRUPT_HINT})"


def terminal_turn_elapsed_seconds(started_at: float, *, now: float | None = None) -> int:
    """Return monotonic elapsed seconds for the terminal active-turn status."""

    if not started_at:
        return 0
    current = time.monotonic() if now is None else float(now)
    return max(0, int(current - float(started_at)))


def should_render_terminal_turn_status(
    *,
    active: bool,
    last_second: int | None,
    elapsed_seconds: int,
    suppressed: bool,
    force: bool = False,
) -> bool:
    """Mirror the Rust status tick gate for the scrollback terminal runner."""

    if suppressed:
        return False
    if force:
        return True
    return not (active and last_second == elapsed_seconds)


@dataclass(frozen=True)
class TerminalTurnStatusState:
    """State for the terminal product path's active-turn status tick.

    Rust ``chatwidget::status_surfaces`` owns the status surface refresh
    decision; the terminal runner stores this state and performs the actual
    terminal write.
    """

    active: bool = False
    last_second: int | None = None
    suppressed: bool = False

    @classmethod
    def inactive(cls) -> "TerminalTurnStatusState":
        return cls()

    def should_render(self, elapsed_seconds: int, *, force: bool = False) -> bool:
        return should_render_terminal_turn_status(
            active=self.active,
            last_second=self.last_second,
            elapsed_seconds=elapsed_seconds,
            suppressed=self.suppressed,
            force=force,
        )

    def after_render(self, elapsed_seconds: int) -> "TerminalTurnStatusState":
        return TerminalTurnStatusState(active=True, last_second=int(elapsed_seconds), suppressed=self.suppressed)

    def should_refresh(self) -> bool:
        return self.active and not self.suppressed

    def cleared(self) -> "TerminalTurnStatusState":
        return TerminalTurnStatusState.inactive()

    def suppress(self) -> "TerminalTurnStatusState":
        return TerminalTurnStatusState(
            active=self.active,
            last_second=self.last_second,
            suppressed=True,
        )


@dataclass
class TerminalStatusSurfaceWriter:
    """Stateful adapter for terminal live-status and active-turn status.

    Rust ``chatwidget::status_surfaces`` owns status text and refresh state,
    while ``tui`` owns inline-viewport effects. The terminal runner supplies
    only environment callbacks for terminal activity, resize, and bottom-pane
    rendering.
    """

    writer: TextIO
    live_status: TerminalLiveStatusSurface = field(default_factory=TerminalLiveStatusSurface.inactive)
    turn_status: TerminalTurnStatusState = field(default_factory=TerminalTurnStatusState.inactive)
    turn_started_at: float = 0.0
    stdin_is_terminal: Callable[[], bool] = lambda: False
    layout_active: Callable[[], bool] = lambda: False
    check_resize: Callable[[], None] = lambda: None
    render_bottom_pane: Callable[[], None] = lambda: None
    terminal_title_requires_action: bool = False

    @property
    def turn_active(self) -> bool:
        """Return whether an agent turn owns the active bottom-pane status."""

        return self.turn_status.active

    def composer_cursor_visible(self) -> bool:
        """Return whether the bottom-pane composer cursor should be visible."""

        return not self.turn_active

    def bind_render_bottom_pane(self, render_bottom_pane: Callable[[], None]) -> None:
        """Bind the bottom-pane render callback after terminal components are wired."""

        self.render_bottom_pane = render_bottom_pane

    def set_terminal_title_requires_action(self, required: bool) -> None:
        """Project the active view's Rust action-required title contract."""

        required = bool(required)
        if required == self.terminal_title_requires_action:
            return
        self.terminal_title_requires_action = required
        if required:
            set_terminal_title(TERMINAL_TITLE_ACTION_REQUIRED_PREFIX, stdout=self.writer)
        else:
            clear_terminal_title(stdout=self.writer)

    def start_turn(self, started_at: float) -> None:
        self.turn_started_at = float(started_at)

    def show_live_status(self, header: str, details: str | None = None) -> None:
        self.live_status = run_terminal_live_status_text_show(
            self.writer,
            self.live_status,
            header,
            details,
            stdin_is_terminal=self.stdin_is_terminal(),
            layout_active=self.layout_active(),
            check_resize=self.check_resize,
            render_bottom_pane=self.render_bottom_pane,
            apply_state=self._apply_live_status,
        )

    def show_guardian_status(self, header: str, details: str | None = None) -> None:
        """Let guardian review temporarily own the active-turn status row."""

        self.suppress_turn_status()
        self.show_live_status(header, details)

    def restore_turn_status(self, header: str = "Working") -> None:
        """Release guardian ownership and restore the active turn status tick."""

        was_active = self.turn_status.active
        self.turn_status = TerminalTurnStatusState(
            active=was_active,
            last_second=self.turn_status.last_second,
            suppressed=False,
        )
        if was_active:
            self.render_turn_status(force=True)
        else:
            self.show_live_status(header)

    def render_turn_status(self, *, force: bool = False, now: float | None = None) -> None:
        self.turn_status = run_terminal_turn_status_render(
            self.turn_status,
            started_at=self.turn_started_at,
            force=force,
            now=now,
            write_live_status=self.show_live_status,
        )

    def render_turn_status_force(self) -> None:
        """Render active-turn status immediately for turn start."""

        self.render_turn_status(force=True)

    def refresh_turn_status_if_due(self, *, now: float | None = None) -> None:
        self.turn_status = run_terminal_turn_status_refresh(
            self.turn_status,
            started_at=self.turn_started_at,
            now=now,
            write_live_status=self.show_live_status,
        )

    def clear_turn_status(self) -> None:
        self.turn_status = terminal_turn_status_cleared(self.turn_status)

    def suppress_turn_status(self) -> None:
        self.turn_status = terminal_turn_status_suppressed(self.turn_status)

    def hide_inline_status(self, *, redraw_bottom_pane: bool = True) -> None:
        self.live_status = run_terminal_live_status_hide(
            self.writer,
            self.live_status,
            stdin_is_terminal=self.stdin_is_terminal(),
            redraw_bottom_pane=redraw_bottom_pane,
            render_bottom_pane=self.render_bottom_pane,
            apply_state=self._apply_live_status,
        )

    def hide_live_status(self) -> None:
        """Hide protocol-owned live status and redraw the bottom pane."""

        self.hide_inline_status(redraw_bottom_pane=True)

    def clear_live_status(self) -> None:
        self.hide_live_status()

    def _apply_live_status(self, state: TerminalLiveStatusSurface) -> None:
        self.live_status = state


@dataclass(frozen=True)
class TerminalTurnStatusRenderPlan:
    """Prepared terminal turn-status render result."""

    header: str | None
    state: TerminalTurnStatusState


def terminal_turn_status_render_plan(
    state: TerminalTurnStatusState,
    *,
    started_at: float,
    force: bool = False,
    now: float | None = None,
) -> TerminalTurnStatusRenderPlan:
    """Prepare the next active-turn status surface and state transition.

    Rust ``chatwidget::status_surfaces`` owns the status text and refresh gate;
    the terminal runner applies the returned terminal side effect.
    """

    elapsed = terminal_turn_elapsed_seconds(started_at, now=now)
    if not state.should_render(elapsed, force=force):
        return TerminalTurnStatusRenderPlan(header=None, state=state)
    return TerminalTurnStatusRenderPlan(
        header=terminal_turn_status_header(elapsed),
        state=state.after_render(elapsed),
    )


def run_terminal_turn_status_render(
    state: TerminalTurnStatusState,
    *,
    started_at: float,
    force: bool = False,
    now: float | None = None,
    write_live_status: Callable[[str], None],
) -> TerminalTurnStatusState:
    """Render active-turn status when needed and return the advanced state."""

    plan = terminal_turn_status_render_plan(
        state,
        started_at=started_at,
        force=force,
        now=now,
    )
    if plan.header is not None:
        write_live_status(plan.header)
    return plan.state


def run_terminal_turn_status_refresh(
    state: TerminalTurnStatusState,
    *,
    started_at: float,
    now: float | None = None,
    write_live_status: Callable[[str], None],
) -> TerminalTurnStatusState:
    """Refresh active-turn status when the status surface owns an active tick."""

    if not state.should_refresh():
        return state
    return run_terminal_turn_status_render(
        state,
        started_at=started_at,
        now=now,
        write_live_status=write_live_status,
    )


def terminal_turn_status_cleared(state: TerminalTurnStatusState) -> TerminalTurnStatusState:
    """Return the cleared active-turn status state."""

    return state.cleared()


def terminal_turn_status_suppressed(state: TerminalTurnStatusState) -> TerminalTurnStatusState:
    """Return the suppressed active-turn status state."""

    return state.suppress()


def parse_items_with_invalids(
    ids: Iterable[Any],
    parser: Any | None = None,
) -> tuple[list[Any], list[str]]:
    parse_one = parser if parser is not None else _parse_status_or_title_item
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    items: list[Any] = []
    for item_id in ids:
        text = str(item_id)
        try:
            items.append(parse_one(item_id))
        except Exception:
            if text not in invalid_seen:
                invalid_seen.add(text)
                invalid.append(f'"{text}"')
    return items, invalid


def permissions_display(config: Any) -> str:
    """Return the status-line permissions label used by Rust Codex.

    Rust first preserves a named active permission profile unless the id is an
    internal ``:`` profile, then summarizes the effective profile into the
    user-facing labels shown in the TUI.
    """

    permissions = _read_field(config, "permissions")
    active_profile = _call_or_value(_read_field(permissions, "active_permission_profile"))
    active_id = _read_field(active_profile, "id")
    if isinstance(active_id, str) and active_id and not active_id.startswith(":"):
        return active_id

    permission_profile = _call_or_value(
        _read_field(permissions, "effective_permission_profile")
    )
    summary = _permission_profile_summary(permission_profile, config)
    details = _strip_prefix(summary, "read-only")
    if details is not None and "(network access enabled)" not in details:
        return "Read Only"
    details = _strip_prefix(summary, "workspace-write")
    if details is not None and "(network access enabled)" not in details:
        return "Workspace"
    if _permission_profile_is_disabled(permission_profile):
        return "Full Access"
    return "Custom permissions"


def approval_mode_display(config: Any) -> str:
    permissions = _read_field(config, "permissions")
    approval_policy = _approval_policy_value(_read_field(permissions, "approval_policy"))
    reviewer = _canonical_token(_read_field(config, "approvals_reviewer"))
    if approval_policy == "on-request" and reviewer == "auto-review":
        return "auto-review"
    return approval_policy


def _parse_status_or_title_item(value: Any) -> Any:
    try:
        return StatusLineItem.parse(value)
    except ValueError:
        return TerminalTitleItem.from_id(value)


def _read_field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _call_or_value(value: Any) -> Any:
    if callable(value):
        return value()
    return value


def _strip_prefix(value: str, prefix: str) -> str | None:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return None


def _canonical_token(value: Any) -> str:
    value = _call_or_value(value)
    enum_value = _read_field(value, "value")
    if enum_value is not None:
        value = _call_or_value(enum_value)
    enum_name = _read_field(value, "name")
    if enum_name is not None:
        value = enum_name
    text = str(value).strip()
    if "::" in text:
        text = text.rsplit("::", 1)[-1]
    return text.replace("_", "-").lower()


def _approval_policy_value(value: Any) -> str:
    value = _call_or_value(value)
    nested = _read_field(value, "value")
    if nested is not None:
        value = _call_or_value(nested)
    return _canonical_token(value)


def _permission_profile_summary(profile: Any, config: Any) -> str:
    summary = _read_field(profile, "summary")
    if isinstance(summary, str):
        return summary
    summary = _read_field(config, "permission_profile_summary")
    if isinstance(summary, str):
        return summary

    token = _canonical_token(profile)
    network_enabled = _permission_profile_network_enabled(profile)
    if token in {"read-only", "readonly"}:
        return "read-only (network access enabled)" if network_enabled else "read-only"
    if token in {"workspace-write", "workspacewrite"}:
        return (
            "workspace-write (network access enabled)"
            if network_enabled
            else "workspace-write"
        )
    if token in {"disabled", "full-access", "fullaccess"}:
        return "disabled"
    return token


def _permission_profile_network_enabled(profile: Any) -> bool:
    for name in (
        "network_access",
        "network_access_enabled",
        "experimental_network_access",
    ):
        value = _read_field(profile, name)
        if isinstance(value, bool):
            return value
    text = str(profile).lower()
    return "(network access enabled)" in text or "network_access=true" in text


def _permission_profile_is_disabled(profile: Any) -> bool:
    token = _canonical_token(profile)
    return token in {"disabled", "full-access", "fullaccess"}


def _graphemes(text: str) -> list[str]:
    clusters: list[str] = []
    for ch in text:
        if clusters and _is_combining_mark(ch):
            clusters[-1] += ch
        else:
            clusters.append(ch)
    return clusters


def _is_combining_mark(ch: str) -> bool:
    import unicodedata

    return bool(unicodedata.combining(ch))


def _terminal_title_status_kind(value: TerminalTitleStatusKind | str) -> TerminalTitleStatusKind:
    if isinstance(value, TerminalTitleStatusKind):
        return value
    text = str(value)
    for candidate in TerminalTitleStatusKind:
        if text in {candidate.name, candidate.value}:
            return candidate
    normalized = text.replace("-", "_").lower()
    for candidate in TerminalTitleStatusKind:
        if normalized in {candidate.name.lower(), candidate.value}:
            return candidate
    return TerminalTitleStatusKind.Working


def _flush_writer(writer: TextIO) -> None:
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


__all__ = [
    "CachedProjectRootName",
    "DEFAULT_STATUS_LINE_ITEMS",
    "DEFAULT_TERMINAL_TITLE_ITEMS",
    "RUST_MODULE",
    "StatusSurfaceSelections",
    "TERMINAL_TITLE_ACTION_REQUIRED_INTERVAL",
    "TERMINAL_TITLE_ACTION_REQUIRED_PREFIX",
    "TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN",
    "TERMINAL_TITLE_SPINNER_FRAMES",
    "TERMINAL_TITLE_SPINNER_INTERVAL",
    "TERMINAL_LIVE_STATUS_DETAIL_PREFIX",
    "TERMINAL_LIVE_STATUS_PREFIX",
    "TERMINAL_TURN_INTERRUPT_HINT",
    "TerminalLiveStatusActionPlan",
    "TerminalLiveStatusProjection",
    "TerminalLiveStatusSurface",
    "TerminalLiveStatusTransition",
    "TerminalTurnStatusRenderPlan",
    "TerminalTurnStatusState",
    "TerminalStatusSurfaceWriter",
    "action_required_terminal_title_prefix_at",
    "approval_mode_display",
    "find_codex_window",
    "find_primary_codex_window",
    "five_hour_status_window",
    "matches_window_label",
    "non_weekly_primary_window",
    "non_weekly_secondary_window_when_primary_is_weekly",
    "parse_items_with_invalids",
    "parse_status_line_items_with_invalids",
    "parse_terminal_title_items_with_invalids",
    "permissions_display",
    "run_state_status_text",
    "run_terminal_live_status_action_plan",
    "run_terminal_live_status_hide",
    "run_terminal_live_status_show",
    "run_terminal_live_status_text_show",
    "run_terminal_turn_status_refresh",
    "run_terminal_turn_status_render",
    "secondary_window_with_label_when_weekly_is_available",
    "should_render_terminal_turn_status",
    "status_surface_selections",
    "terminal_turn_status_cleared",
    "terminal_turn_status_suppressed",
    "terminal_live_status_hide_plan",
    "terminal_live_status_projection",
    "terminal_live_status_show_plan",
    "terminal_live_status_text",
    "terminal_live_status_transition_to_inactive",
    "terminal_live_status_transition_to_status",
    "terminal_turn_elapsed_seconds",
    "terminal_turn_status_header",
    "terminal_turn_status_render_plan",
    "terminal_title_spinner_frame_at",
    "truncate_terminal_title_part",
    "weekly_status_window",
]
