"""View-stack behavior for Rust ``codex-tui::bottom_pane::BottomPane``.

Rust keeps the active ``BottomPaneView`` stack in ``bottom_pane/mod.rs``.  This
module carries that owner boundary for Python terminal adapters so they do not
hand-roll child-view completion rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Callable, Protocol, TypeAlias

from .._porting import RustTuiModule
from .chat_composer import (
    ChatComposer,
    InputResult,
    TerminalCommandPopupState,
    TerminalComposerInputAction,
    terminal_popup_key,
)
from .command_popup import CommandPopup, CommandPopupFlags
from .bottom_pane_view import (
    BottomPaneView,
    CancellationEvent,
    ViewCompletion,
    clear_dismiss_after_child_accept as clear_view_dismiss_after_child_accept,
    completion as view_completion,
    cursor_pos as view_cursor_pos,
    dismiss_app_server_request as view_dismiss_app_server_request,
    dismiss_after_child_accept as view_dismiss_after_child_accept,
    handle_key_event as view_handle_key_event,
    handle_paste as view_handle_paste,
    is_complete as view_is_complete,
    on_ctrl_c as view_on_ctrl_c,
    terminal_lines as view_terminal_lines,
    terminal_title_requires_action as view_terminal_title_requires_action,
    try_consume_approval_request as view_try_consume_approval_request,
    try_consume_mcp_server_elicitation_request as view_try_consume_mcp_request,
    try_consume_user_input_request as view_try_consume_user_input_request,
    view_id as bottom_pane_view_id,
)
from .list_selection_view import (
    ListSelectionView,
    SelectionViewParams,
)
from .selection_popup_common import TerminalPopupLine
from .request_user_input import RequestUserInputOverlay
from .mcp_server_elicitation import McpServerElicitationOverlay
from .pending_thread_approvals import PendingThreadApprovals

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane",
    source="codex/codex-rs/tui/src/bottom_pane/mod.rs",
)


class TerminalCommandPopupStateProtocol(Protocol):
    """Command-popup state shape consumed by the bottom-pane view stack."""

    visible: bool

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        ...

    def sync_draft(self, draft: str, *, active_view_present: bool = False) -> bool:
        ...

    def hide(self) -> None:
        ...


@dataclass(frozen=True)
class TerminalSelectionTransition:
    """Rust-like result of dispatching active-view AppEvents.

    ``next_view`` is pushed after completed-view cleanup. ``after_pop`` then
    runs with the stale modal footprint removed.
    """

    next_view: object = None
    after_pop: Callable[[], object] | None = None
    replace_view_ids: tuple[str, ...] = ()


TerminalSelectionEventHandler: TypeAlias = Callable[
    [tuple[object, ...]], SelectionViewParams | BottomPaneView | TerminalSelectionTransition | None
]
TerminalCommandViewFactory: TypeAlias = Callable[[str], SelectionViewParams | None]


@dataclass
class BottomPaneViewStack:
    """Owns active bottom-pane views and Rust child-completion rules."""

    _views: list[BottomPaneView] = field(default_factory=list)

    @property
    def views(self) -> list[BottomPaneView]:
        return self._views

    def active_view(self) -> BottomPaneView | None:
        return self._views[-1] if self._views else None

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        view = self.active_view()
        if view is None:
            return []
        return view_terminal_lines(view, width=width)

    def replace_with(self, view: BottomPaneView) -> None:
        self._views = [view]

    def replace_with_selection_view(self, params: SelectionViewParams, events: list[object]) -> None:
        events.clear()
        self.replace_with(ListSelectionView.new(params, events))

    def push(self, view: BottomPaneView) -> None:
        self._views.append(view)

    def push_selection_view(self, params: SelectionViewParams, events: list[object]) -> None:
        self.push(ListSelectionView.new(params, events))

    def clear(self) -> None:
        self._views.clear()

    def dismiss_app_server_request(self, request: object) -> bool:
        """Dismiss a resolved request from the owning active/queued view."""

        for view in reversed(self._views):
            if view_dismiss_app_server_request(view, request):
                self.pop_completed_views()
                return True
        return False

    def handle_active_key(
        self,
        key: str,
        *,
        selection_events: list[object],
        on_selection_events: TerminalSelectionEventHandler | None = None,
    ) -> bool:
        """Route a key to the active view and apply Rust stack completion rules."""

        view = self.active_view()
        if view is None or not key:
            return False
        prefer_esc = bool(getattr(view, "prefer_esc_to_handle_key_event", lambda: False)())
        if str(key).lower() == "esc" and not prefer_esc:
            cancellation = getattr(view, "on_ctrl_c", lambda: CancellationEvent.NOT_HANDLED)()
            handled = (
                cancellation is CancellationEvent.HANDLED
                or str(getattr(cancellation, "value", cancellation)).lower() == "handled"
            )
            if not (handled and view_is_complete(view)):
                view_handle_key_event(view, key)
        else:
            view_handle_key_event(view, key)
        transition = self.drain_selection_events(
            selection_events,
            on_selection_events=on_selection_events,
        )
        self.pop_completed_views()
        if transition is not None:
            if transition.replace_view_ids:
                while self._views and bottom_pane_view_id(self._views[-1]) in transition.replace_view_ids:
                    self._views.pop()
            next_view = transition.next_view
            if isinstance(next_view, SelectionViewParams):
                self.push_selection_view(next_view, selection_events)
            elif next_view is not None:
                self.push(next_view)
            if transition.after_pop is not None:
                transition.after_pop()
        return True

    def handle_active_paste(self, pasted: str) -> bool:
        """Route paste/committed text to the active view like Rust BottomPane."""

        view = self.active_view()
        if view is None:
            return False
        needs_redraw = view_handle_paste(view, str(pasted))
        view_complete = view_is_complete(view)
        if view_complete:
            # Rust tears down the entire modal flow when paste completes the
            # active view; it does not apply ordinary child-pop semantics.
            self.clear()
        return bool(needs_redraw or view_complete)

    def cursor_pos(self, area: object) -> tuple[int, int] | None:
        view = self.active_view()
        return None if view is None else view_cursor_pos(view, area)

    def handle_ctrl_c(self) -> bool:
        """Give the active view first refusal on Ctrl+C like Rust BottomPane."""

        view = self.active_view()
        if view is None:
            return False
        cancellation = view_on_ctrl_c(view)
        handled = (
            cancellation is CancellationEvent.HANDLED
            or str(getattr(cancellation, "value", cancellation)).lower() == "handled"
        )
        if handled:
            self.pop_completed_views()
        return handled

    def drain_selection_events(
        self,
        selection_events: list[object],
        *,
        on_selection_events: TerminalSelectionEventHandler | None = None,
    ) -> TerminalSelectionTransition | None:
        events = tuple(selection_events)
        selection_events.clear()
        raw_result = on_selection_events(events) if on_selection_events is not None else None
        transition = raw_result if isinstance(raw_result, TerminalSelectionTransition) else TerminalSelectionTransition(raw_result)
        return transition

    def pop_completed_views(self) -> None:
        """Pop completed views using Rust ``pop_active_view_with_completion`` rules."""

        while self._views and view_is_complete(self._views[-1]):
            completed = self._views.pop()
            completion = view_completion(completed)
            if _completion_is_accepted(completion):
                while self._views and view_dismiss_after_child_accept(self._views[-1]):
                    self._views.pop()
            elif _completion_is_cancelled(completion) and self._views:
                clear_view_dismiss_after_child_accept(self._views[-1])


@dataclass(frozen=True)
class TerminalBottomPaneActiveViewInputResult:
    active: bool
    draft: str | None = None


@dataclass(frozen=True)
class TerminalBottomPanePopupProjection:
    lines: tuple[TerminalPopupLine, ...] = ()
    is_active_view: bool = False

    @property
    def height(self) -> int:
        return len(self.lines)


@dataclass(frozen=True)
class TerminalBottomPaneRenderContext:
    """Bottom-pane-owned values needed by the terminal render adapter."""

    draft: str
    composer_projection: object | None = None
    popup_lines: tuple[TerminalPopupLine, ...] = ()
    popup_height: int = 0
    popup_is_active_view: bool = False
    cursor_visible: bool = True
    popup_cursor: tuple[int, int] | None = None
    active_tail_lines: tuple[str, ...] = ()
    composer_height: int = 1

    @property
    def active_tail_height(self) -> int:
        return len(self.active_tail_lines)


@dataclass
class TerminalBottomPaneViewState:
    """Owns terminal-path bottom-pane view and command-popup state.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns the active view
    stack, composer command-popup suppression, selection-event transitions,
    and cursor visibility policy. Terminal adapters may hold this object, but
    should not split those pieces into independent local state.
    """

    composer: ChatComposer = field(default_factory=ChatComposer)
    view_stack: BottomPaneViewStack = field(default_factory=BottomPaneViewStack)
    selection_events: list[object] = field(default_factory=list)
    active_tail_lines: tuple[str, ...] = ()
    pending_thread_approvals: PendingThreadApprovals = field(
        default_factory=PendingThreadApprovals.new
    )
    @classmethod
    def new(cls, command_popup_flags: CommandPopupFlags | None = None) -> "TerminalBottomPaneViewState":
        return cls(composer=ChatComposer(command_popup_flags=command_popup_flags))

    @property
    def draft(self) -> str:
        return self.composer.current_text()

    @property
    def command_popup_state(self) -> TerminalCommandPopupState:
        return self.composer.command_popup_state

    @property
    def history(self) -> object:
        return self.composer.history

    @property
    def active_view(self) -> BottomPaneView | None:
        return self.view_stack.active_view()

    @property
    def status_indicator_visible(self) -> bool:
        """Match Rust ``BottomPane::as_renderable`` active-view precedence."""

        return self.active_view is None

    @property
    def views(self) -> list[BottomPaneView]:
        return self.view_stack.views

    @property
    def command_popup(self) -> CommandPopup:
        return self.command_popup_state.popup

    def terminal_title_requires_action(self) -> bool:
        active = self.view_stack.active_view()
        return bool(active is not None and view_terminal_title_requires_action(active))

    @property
    def command_popup_visible(self) -> bool:
        return self.command_popup_state.visible

    def apply_draft(self, draft: str) -> None:
        source = str(draft)
        if source != self.composer.current_text():
            self.composer.set_text_content(source)
        else:
            self.composer.sync_popups(active_view_present=self.active_view is not None)

    def record_submission(self, text: str) -> None:
        """Record one canonical local composer submission for Up/Down recall."""

        self.composer.record_submission(text)

    def configure_history(
        self,
        thread_id: object,
        log_id: int,
        entry_count: int,
        lookup: Callable[[int, int], object | None] | None,
    ) -> None:
        """Install the fixed persistent-history snapshot for this session."""

        self.composer.configure_history(thread_id, log_id, entry_count, lookup)

    def apply_active_tail(self, lines: tuple[str, ...]) -> None:
        self.active_tail_lines = tuple(str(line) for line in lines)

    def apply_pending_thread_approvals(self, approvals: list[str]) -> None:
        self.pending_thread_approvals.set_threads(list(approvals))

    def handle_composer_event(
        self,
        event_kind: str,
        event_text: str = "",
        *,
        now: float | None = None,
        detect_paste_bursts: bool = False,
        on_selection_events: TerminalSelectionEventHandler | None = None,
        open_command_view: TerminalCommandViewFactory | None = None,
    ) -> TerminalComposerInputAction | InputResult:
        key = terminal_popup_key(event_kind, event_text)
        active = terminal_bottom_pane_active_view_input(
            self.view_stack,
            key,
            event_kind,
            self.composer.current_text(),
            event_text,
            selection_events=self.selection_events,
            on_selection_events=on_selection_events,
        )
        if active.active and active.draft is not None:
            return TerminalComposerInputAction("render", self.composer.current_text())

        return self.composer.handle_terminal_event(
            event_kind,
            event_text,
            now=now,
            detect_paste_bursts=detect_paste_bursts,
            active_view_present=self.active_view is not None,
            open_command_view=open_command_view,
            show_selection_view=self.show_selection_view,
        )

    def show_selection_view(self, params: SelectionViewParams) -> None:
        terminal_bottom_pane_show_selection_view(
            self.view_stack,
            self.command_popup_state,
            params,
            self.selection_events,
        )

    def show_view(self, view: object) -> BottomPaneView:
        """Push a view, first offering approval requests to the active view."""

        if isinstance(view, SelectionViewParams):
            self.show_selection_view(view)
            active_selection = self.view_stack.active_view()
            if active_selection is None:
                raise RuntimeError("selection view was not activated")
            return active_selection
        self.composer.command_popup_state.hide()
        request = getattr(view, "current_request", None)
        active = self.view_stack.active_view()
        if request is not None and active is not None:
            remaining = view_try_consume_approval_request(active, request)
            if remaining is None:
                return active
            setter = getattr(view, "set_current", None)
            if remaining is not request and callable(setter):
                setter(remaining)
        if isinstance(view, RequestUserInputOverlay) and active is not None:
            remaining = view_try_consume_user_input_request(active, view.request)
            if remaining is None:
                return active
            view.request = remaining
            view.reset_for_request()
        if isinstance(view, McpServerElicitationOverlay) and active is not None:
            remaining = view_try_consume_mcp_request(active, view.request)
            if remaining is None:
                return active
            view.request = remaining
        self.view_stack.push(view)
        return view

    def dismiss_app_server_request(self, request: object) -> bool:
        return self.view_stack.dismiss_app_server_request(request)

    def popup_projection_for_size(self, size: os.terminal_size) -> TerminalBottomPanePopupProjection:
        projection = terminal_bottom_pane_popup_projection_for_size(
            self.view_stack,
            self.command_popup_state,
            size,
        )
        if projection.lines:
            return projection
        rows = self.pending_thread_approvals.as_renderable(max(1, size.columns))
        return TerminalBottomPanePopupProjection(
            tuple(TerminalPopupLine(row.text) for row in rows),
            is_active_view=False,
        )

    def popup_height_for_size(self, size: os.terminal_size) -> int:
        return self.popup_projection_for_size(size).height

    def cursor_visible(self, composer_cursor_visible: Callable[[], bool]) -> bool:
        return terminal_bottom_pane_cursor_visible(self.view_stack, composer_cursor_visible)

    def render_context_for_size(
        self,
        size: os.terminal_size,
        composer_cursor_visible: Callable[[], bool],
    ) -> TerminalBottomPaneRenderContext:
        """Return bottom-pane-owned render inputs for the terminal adapter.

        Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns active-view
        popup precedence and primary composer cursor visibility. The terminal
        controller consumes this context without separately querying popup
        rows, popup footprint source, or cursor policy.
        """

        popup_projection = self.popup_projection_for_size(size)
        composer_projection = self.composer.terminal_projection(size.columns)
        composer_height = composer_projection.height
        popup_cursor = None
        if popup_projection.is_active_view:
            popup_cursor = self.view_stack.cursor_pos(
                {
                    "x": 0,
                    "y": 0,
                    "width": max(1, size.columns - 1),
                    "height": popup_projection.height,
                }
            )
        return TerminalBottomPaneRenderContext(
            draft=self.draft,
            composer_projection=composer_projection,
            popup_lines=popup_projection.lines,
            popup_height=popup_projection.height,
            popup_is_active_view=popup_projection.is_active_view,
            cursor_visible=(popup_cursor is not None if popup_projection.is_active_view else composer_cursor_visible()),
            popup_cursor=popup_cursor,
            active_tail_lines=self.active_tail_lines,
            composer_height=composer_height,
        )


def terminal_bottom_pane_active_view_input(
    view_stack: BottomPaneViewStack,
    key: str,
    event_kind: str,
    draft: str,
    event_text: str = "",
    *,
    selection_events: list[object],
    on_selection_events: TerminalSelectionEventHandler | None = None,
) -> TerminalBottomPaneActiveViewInputResult:
    """Route terminal input through the active bottom-pane view first.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` gives active
    ``BottomPaneView`` instances priority over composer input. Views consume
    ordinary key input while EOF/interrupt continue to the composer/runtime
    shutdown path.
    """

    if view_stack.active_view() is None:
        return TerminalBottomPaneActiveViewInputResult(False)
    kind = str(event_kind).lower()
    if kind == "release":
        return TerminalBottomPaneActiveViewInputResult(True, draft)
    if kind == "interrupt":
        return TerminalBottomPaneActiveViewInputResult(
            view_stack.handle_ctrl_c(),
            draft,
        )
    if kind == "paste":
        view_stack.handle_active_paste(event_text)
        return TerminalBottomPaneActiveViewInputResult(True, draft)
    if not key and kind in {"text", "line"} and event_text:
        if len(event_text) > 1:
            view_stack.handle_active_paste(event_text.rstrip("\r\n") if kind == "line" else event_text)
        else:
            view_stack.handle_active_key(
                event_text,
                selection_events=selection_events,
                on_selection_events=on_selection_events,
            )
        return TerminalBottomPaneActiveViewInputResult(True, draft)
    if not key and kind not in {"text", "line", "paste", "eof", "interrupt", "resize"}:
        key = kind
    if key:
        view_stack.handle_active_key(
            key,
            selection_events=selection_events,
            on_selection_events=on_selection_events,
        )
        return TerminalBottomPaneActiveViewInputResult(True, draft)
    if str(event_kind).lower() in {"eof", "interrupt"}:
        return TerminalBottomPaneActiveViewInputResult(True, None)
    return TerminalBottomPaneActiveViewInputResult(True, draft)


def terminal_bottom_pane_popup_lines(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupStateProtocol,
    *,
    width: int,
) -> list[TerminalPopupLine]:
    """Project the visible terminal popup rows for the bottom pane.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns active view
    priority over composer popups. Concrete active views and the command popup
    still own their row rendering; this helper only centralizes the bottom-pane
    precedence rule so terminal adapters do not duplicate it.
    """

    return list(
        terminal_bottom_pane_popup_projection(
            view_stack,
            command_popup_state,
            width=width,
        ).lines
    )


def terminal_bottom_pane_popup_projection(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupStateProtocol,
    *,
    width: int,
) -> TerminalBottomPanePopupProjection:
    """Project popup rows and footprint source for the terminal bottom pane.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns whether an active
    view or composer popup supplies the bottom-pane popup area. The terminal
    controller consumes the resulting projection without re-checking active
    view state.
    """

    if view_stack.active_view() is not None:
        return TerminalBottomPanePopupProjection(
            tuple(view_stack.terminal_lines(width=width)),
            is_active_view=True,
        )
    if not command_popup_state.visible:
        return TerminalBottomPanePopupProjection()
    return TerminalBottomPanePopupProjection(tuple(command_popup_state.terminal_lines(width=width)))


def terminal_bottom_pane_popup_projection_for_size(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupStateProtocol,
    size: os.terminal_size,
) -> TerminalBottomPanePopupProjection:
    """Project popup rows from terminal geometry.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns bottom-pane popup
    area layout, including the content width passed to active views or composer
    command popups. Terminal controllers should provide observed geometry, not
    duplicate the width expression.
    """

    return terminal_bottom_pane_popup_projection(
        view_stack,
        command_popup_state,
        width=max(1, size.columns - 1),
    )


def terminal_bottom_pane_sync_command_popup(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupStateProtocol,
    draft: str,
) -> bool:
    """Sync composer command-popup visibility with active-view priority.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` gives active views
    priority over composer popups, while ``chat_composer::sync_popups`` owns
    draft-driven command-popup visibility. This helper keeps that cross-owner
    precedence out of terminal adapters.
    """

    return bool(
        command_popup_state.sync_draft(
            draft,
            active_view_present=view_stack.active_view() is not None,
        )
    )


def terminal_bottom_pane_show_selection_view(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupStateProtocol,
    params: SelectionViewParams,
    events: list[object],
) -> None:
    """Replace the active bottom-pane stack with a selection view.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns active-view stack
    replacement, and active views suppress composer command popups. Terminal
    adapters provide the concrete selection params but do not own the stack
    and popup cleanup sequence.
    """

    view_stack.replace_with_selection_view(params, events)
    command_popup_state.hide()


def terminal_bottom_pane_cursor_visible(
    view_stack: BottomPaneViewStack,
    composer_cursor_visible: Callable[[], bool],
) -> bool:
    """Return the frame-level cursor policy for active bottom-pane state.

    Rust owner: active ``BottomPaneView`` instances replace the primary
    composer cursor with their own optional ``Renderable::cursor_pos``.
    ``custom_terminal`` hides the cursor only when neither owner supplies one.
    """

    if view_stack.active_view() is not None:
        return view_stack.cursor_pos({"x": 0, "y": 0, "width": 80, "height": 24}) is not None
    return bool(composer_cursor_visible())


def _completion_is_accepted(value: ViewCompletion | None) -> bool:
    return value is ViewCompletion.ACCEPTED


def _completion_is_cancelled(value: ViewCompletion | None) -> bool:
    return value is ViewCompletion.CANCELLED


__all__ = [
    "BottomPaneViewStack",
    "RUST_MODULE",
    "TerminalBottomPaneActiveViewInputResult",
    "TerminalCommandPopupStateProtocol",
    "TerminalBottomPanePopupProjection",
    "TerminalBottomPaneRenderContext",
    "TerminalBottomPaneViewState",
    "TerminalCommandViewFactory",
    "TerminalSelectionEventHandler",
    "TerminalSelectionTransition",
    "terminal_bottom_pane_active_view_input",
    "terminal_bottom_pane_cursor_visible",
    "terminal_bottom_pane_popup_lines",
    "terminal_bottom_pane_popup_projection",
    "terminal_bottom_pane_popup_projection_for_size",
    "terminal_bottom_pane_show_selection_view",
    "terminal_bottom_pane_sync_command_popup",
]
