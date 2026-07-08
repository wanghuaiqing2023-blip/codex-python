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
    TerminalCommandPopupState,
    run_terminal_command_popup_input_action,
    terminal_popup_key,
)
from .command_popup import CommandPopup
from .bottom_pane_view import (
    BottomPaneView,
    ViewCompletion,
    clear_dismiss_after_child_accept as clear_view_dismiss_after_child_accept,
    completion as view_completion,
    dismiss_after_child_accept as view_dismiss_after_child_accept,
    handle_key_event as view_handle_key_event,
    is_complete as view_is_complete,
    terminal_lines as view_terminal_lines,
)
from .list_selection_view import (
    ListSelectionView,
    SelectionViewParams,
)
from .selection_popup_common import TerminalPopupLine

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


TerminalSelectionEventHandler: TypeAlias = Callable[[tuple[object, ...]], SelectionViewParams | None]
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
        view_handle_key_event(view, key)
        self.drain_selection_events(
            selection_events,
            on_selection_events=on_selection_events,
        )
        self.pop_completed_views()
        return True

    def drain_selection_events(
        self,
        selection_events: list[object],
        *,
        on_selection_events: TerminalSelectionEventHandler | None = None,
    ) -> None:
        if not selection_events:
            return
        events = tuple(selection_events)
        selection_events.clear()
        next_params = on_selection_events(events) if on_selection_events is not None else None
        if next_params is not None:
            self.push_selection_view(next_params, selection_events)

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
class TerminalBottomPaneComposerKeyResult:
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
    popup_lines: tuple[TerminalPopupLine, ...] = ()
    popup_height: int = 0
    popup_is_active_view: bool = False
    cursor_visible: bool = True


@dataclass
class TerminalBottomPaneViewState:
    """Owns terminal-path bottom-pane view and command-popup state.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` owns the active view
    stack, composer command-popup suppression, selection-event transitions,
    and cursor visibility policy. Terminal adapters may hold this object, but
    should not split those pieces into independent local state.
    """

    draft: str = ""
    view_stack: BottomPaneViewStack = field(default_factory=BottomPaneViewStack)
    command_popup_state: TerminalCommandPopupState = field(default_factory=TerminalCommandPopupState.new)
    selection_events: list[object] = field(default_factory=list)

    @classmethod
    def new(cls) -> "TerminalBottomPaneViewState":
        return cls()

    @property
    def active_view(self) -> BottomPaneView | None:
        return self.view_stack.active_view()

    @property
    def views(self) -> list[BottomPaneView]:
        return self.view_stack.views

    @property
    def command_popup(self) -> CommandPopup:
        return self.command_popup_state.popup

    @property
    def command_popup_visible(self) -> bool:
        return self.command_popup_state.visible

    def apply_draft(self, draft: str) -> None:
        self.draft = str(draft)
        terminal_bottom_pane_sync_command_popup(
            self.view_stack,
            self.command_popup_state,
            self.draft,
        )

    def handle_composer_key(
        self,
        draft: str,
        event_kind: str,
        event_text: str = "",
        *,
        on_selection_events: TerminalSelectionEventHandler | None = None,
        open_command_view: TerminalCommandViewFactory | None = None,
    ) -> str | None:
        self.apply_draft(draft)
        return terminal_bottom_pane_handle_composer_key(
            self.view_stack,
            self.command_popup_state,
            draft,
            event_kind,
            event_text,
            selection_events=self.selection_events,
            on_selection_events=on_selection_events,
            open_command_view=open_command_view,
        ).draft

    def show_selection_view(self, params: SelectionViewParams) -> None:
        terminal_bottom_pane_show_selection_view(
            self.view_stack,
            self.command_popup_state,
            params,
            self.selection_events,
        )

    def popup_projection_for_size(self, size: os.terminal_size) -> TerminalBottomPanePopupProjection:
        return terminal_bottom_pane_popup_projection_for_size(
            self.view_stack,
            self.command_popup_state,
            size,
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
        return TerminalBottomPaneRenderContext(
            draft=self.draft,
            popup_lines=popup_projection.lines,
            popup_height=popup_projection.height,
            popup_is_active_view=popup_projection.is_active_view,
            cursor_visible=self.cursor_visible(composer_cursor_visible),
        )


def terminal_bottom_pane_active_view_input(
    view_stack: BottomPaneViewStack,
    key: str,
    event_kind: str,
    draft: str,
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


def terminal_bottom_pane_handle_composer_key(
    view_stack: BottomPaneViewStack,
    command_popup_state: TerminalCommandPopupState,
    draft: str,
    event_kind: str,
    event_text: str = "",
    *,
    selection_events: list[object],
    on_selection_events: TerminalSelectionEventHandler | None = None,
    open_command_view: TerminalCommandViewFactory | None = None,
) -> TerminalBottomPaneComposerKeyResult:
    """Route one terminal composer key through bottom-pane owned precedence.

    Rust owner: ``codex-tui::bottom_pane::BottomPane`` gives active
    ``BottomPaneView`` instances first chance at input, then
    ``chat_composer`` owns slash-command popup key handling before normal
    draft mutation. Terminal controllers provide callbacks but must not split
    that precedence into local branches.
    """

    key = terminal_popup_key(event_kind, event_text)
    active_view_input = terminal_bottom_pane_active_view_input(
        view_stack,
        key,
        event_kind,
        draft,
        selection_events=selection_events,
        on_selection_events=on_selection_events,
    )
    if active_view_input.active:
        return TerminalBottomPaneComposerKeyResult(active_view_input.draft)

    def show_selection_view(params: SelectionViewParams) -> None:
        terminal_bottom_pane_show_selection_view(
            view_stack,
            command_popup_state,
            params,
            selection_events,
        )

    return TerminalBottomPaneComposerKeyResult(
        run_terminal_command_popup_input_action(
            command_popup_state,
            draft,
            key,
            open_command_view=open_command_view,
            show_selection_view=show_selection_view,
        )
    )


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

    Rust owner: active ``BottomPaneView`` instances do not expose the primary
    composer text cursor; ``custom_terminal`` then hides the cursor when the
    rendered frame does not request a cursor position.
    """

    if view_stack.active_view() is not None:
        return False
    return bool(composer_cursor_visible())


def _completion_is_accepted(value: ViewCompletion | None) -> bool:
    return value is ViewCompletion.ACCEPTED


def _completion_is_cancelled(value: ViewCompletion | None) -> bool:
    return value is ViewCompletion.CANCELLED


__all__ = [
    "BottomPaneViewStack",
    "RUST_MODULE",
    "TerminalBottomPaneActiveViewInputResult",
    "TerminalBottomPaneComposerKeyResult",
    "TerminalCommandPopupStateProtocol",
    "TerminalBottomPanePopupProjection",
    "TerminalBottomPaneRenderContext",
    "TerminalBottomPaneViewState",
    "TerminalCommandViewFactory",
    "TerminalSelectionEventHandler",
    "terminal_bottom_pane_active_view_input",
    "terminal_bottom_pane_cursor_visible",
    "terminal_bottom_pane_handle_composer_key",
    "terminal_bottom_pane_popup_lines",
    "terminal_bottom_pane_popup_projection",
    "terminal_bottom_pane_popup_projection_for_size",
    "terminal_bottom_pane_show_selection_view",
    "terminal_bottom_pane_sync_command_popup",
]
