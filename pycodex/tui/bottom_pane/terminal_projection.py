"""Bottom-pane frame to custom-terminal projection adapter.

Rust has no ``terminal_projection.rs`` file.  This Python-only adapter exists
because the product path keeps history in ordinary terminal scrollback while
rendering the bottom live pane through a ratatui-like buffer.  The bottom-pane
frame owner still builds content; this module only converts that frame into the
generic ``custom_terminal`` live-viewport request/update boundary.
"""

from __future__ import annotations

import os
from typing import Callable, Protocol, TextIO, TypeVar

from .terminal_action import (
    TerminalBottomPaneActionPlan,
    TerminalBottomPaneRenderContextProtocol,
    TerminalBottomPaneRenderPassProtocol,
    TerminalBottomPaneRequest,
    TerminalBottomPaneState,
    terminal_bottom_pane_clear_request,
    terminal_bottom_pane_render_request_for_pass,
)
from .terminal_footprint import terminal_bottom_pane_clear_request as _terminal_bottom_pane_clear_request
from .terminal_footprint import TerminalBottomPaneFootprint
from ..chatwidget.rendering import (
    TerminalBottomPaneFrame,
    TerminalBottomPaneFrameProjection,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_frame_buffer,
)
from ..custom_terminal import (
    LiveViewportProjectionPolicy,
    LiveViewportCursorMove,
    LiveViewportProjection,
    LiveViewportProjectionCycle,
    LiveViewportRenderRequest,
    LiveViewportUpdate,
    create_live_viewport_projection_request_runner,
    live_viewport_backend_cursor_position_enabled,
)
from ..ratatui_bridge import Buffer as RatatuiBuffer

_ExternalRepaintResult = TypeVar("_ExternalRepaintResult")


class ProjectionCleanupShape(Protocol):
    """Cleanup metadata shape consumed by the terminal projection adapter."""

    clear_popup_height: int
    clear_live_status_active: bool
    clear_external_blank_rows: bool
    clear_active_tail_height: int
    clear_composer_height: int


class TerminalBottomPaneRequestRunner:
    """Bind bottom-pane requests to the custom-terminal request lifecycle.

    Rust owner: ``codex-tui::custom_terminal`` owns the generic live-viewport
    request lifecycle. This projection adapter supplies only the bottom-pane
    request-to-cycle projection callback so controller code does not hold
    custom-terminal state directly.
    """

    def __init__(
        self,
        writer: TextIO,
        *,
        terminal_size: Callable[[], os.terminal_size],
        resize: Callable[[], None],
    ) -> None:
        self._request_runner = create_live_viewport_projection_request_runner(
            writer,
            terminal_size=terminal_size,
            resize=resize,
            project=terminal_bottom_pane_live_viewport_projection_cycle,
        )

    def terminal_size(self) -> os.terminal_size:
        return self._request_runner.terminal_size()

    def run(
        self,
        request: TerminalBottomPaneRequest,
        *,
        move_cursor: Callable[[int, int], None] | None = None,
    ) -> bool:
        return self._request_runner.run(request, move_cursor=move_cursor)

    def run_clear(
        self,
        *,
        stdin_is_terminal: bool,
        layout_active: bool,
        live_status: object,
        check_resize: bool = True,
        clear_footprint: TerminalBottomPaneFootprint | None = None,
    ) -> bool:
        """Build and run a bottom-pane clear request through this adapter."""

        footprint = clear_footprint or TerminalBottomPaneFootprint()
        return self.run(
            terminal_bottom_pane_clear_request(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                check_resize=check_resize,
                live_status=live_status,
                clear_popup_height=footprint.popup_height,
                clear_live_status_active=footprint.live_status_active,
                clear_active_tail_height=footprint.active_tail_height,
                clear_composer_height=footprint.composer_height,
            ),
        )

    def clear_callback(
        self,
        *,
        stdin_is_terminal: Callable[[], bool],
        layout_active: Callable[[], bool],
        live_status: object,
        check_resize: bool = True,
        clear_footprint: TerminalBottomPaneFootprint | None = None,
    ) -> Callable[[], bool]:
        """Return the resize-reflow clear callback bound to this runner.

        Rust owners: ``codex-tui::app::resize_reflow`` owns the clear-cycle
        remembered footprint state, while ``codex-tui::bottom_pane`` owns the
        clear request. This projection runner packages terminal environment
        callbacks into a request so terminal controllers do not define local
        clear-request closures.
        """

        def clear() -> bool:
            return self.run_clear(
                stdin_is_terminal=stdin_is_terminal(),
                layout_active=layout_active(),
                check_resize=check_resize,
                live_status=live_status,
                clear_footprint=clear_footprint,
            )

        return clear

    def clear_factory_callback(
        self,
        *,
        stdin_is_terminal: Callable[[], bool],
        layout_active: Callable[[], bool],
    ) -> Callable[[object, bool, TerminalBottomPaneFootprint], Callable[[], bool]]:
        """Return the resize-reflow clear factory bound to this runner.

        Rust owners: ``codex-tui::app::resize_reflow`` asks for a
        live-status/check-resize clear factory, while this projection adapter
        owns translating that request into bottom-pane clear requests and the
        custom-terminal lifecycle.
        """

        def clear_factory(
            live_status: object,
            check_resize: bool,
            clear_footprint: TerminalBottomPaneFootprint,
        ) -> Callable[[], bool]:
            return self.clear_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                live_status=live_status,
                check_resize=check_resize,
                clear_footprint=clear_footprint,
            )

        return clear_factory

    def run_render_pass(
        self,
        *,
        stdin_is_terminal: bool,
        layout_active: bool,
        render_context: TerminalBottomPaneRenderContextProtocol,
        footer_text: str,
        live_status: object,
        render_pass: TerminalBottomPaneRenderPassProtocol,
        clear_external_blank_rows: bool = False,
    ) -> bool:
        """Build and run a resize-owned bottom-pane render pass request."""

        return self.run(
            terminal_bottom_pane_render_request_for_pass(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                render_context=render_context,
                footer_text=footer_text,
                live_status=live_status,
                render_pass=render_pass,
                clear_external_blank_rows=clear_external_blank_rows,
            ),
        )

    def render_pass_callback(
        self,
        *,
        stdin_is_terminal: Callable[[], bool],
        layout_active: Callable[[], bool],
        footer_text: Callable[[], str],
        live_status: object,
        clear_external_blank_rows: bool = False,
    ) -> Callable[[TerminalBottomPaneRenderPassProtocol, TerminalBottomPaneRenderContextProtocol], bool]:
        """Return the resize-reflow render callback bound to this runner.

        Rust owners: ``codex-tui::app::resize_reflow`` supplies render-pass
        timing and ``codex-tui::bottom_pane`` supplies render context. This
        projection runner owns packaging those owner values into the
        custom-terminal request lifecycle so terminal controllers do not define
        local pass/context unpacking closures.
        """

        def render(
            render_pass: TerminalBottomPaneRenderPassProtocol,
            render_context: TerminalBottomPaneRenderContextProtocol,
        ) -> bool:
            return self.run_render_pass(
                stdin_is_terminal=stdin_is_terminal(),
                layout_active=layout_active(),
                render_context=render_context,
                footer_text=footer_text(),
                live_status=live_status,
                render_pass=render_pass,
                clear_external_blank_rows=clear_external_blank_rows,
            )

        return render

    def render_pass_factory_callback(
        self,
        *,
        stdin_is_terminal: Callable[[], bool],
        layout_active: Callable[[], bool],
        footer_text: Callable[[], str],
    ) -> Callable[[object, bool], Callable[[TerminalBottomPaneRenderPassProtocol, TerminalBottomPaneRenderContextProtocol], bool]]:
        """Return the resize-reflow render-pass factory bound to this runner.

        Rust owners: ``codex-tui::app::resize_reflow`` asks for a live-status
        and external-blank-row render factory, while this projection adapter
        owns translating render passes and contexts into custom-terminal
        request lifecycle calls.
        """

        def render_factory(
            live_status: object,
            clear_external_blank_rows: bool,
        ) -> Callable[[TerminalBottomPaneRenderPassProtocol, TerminalBottomPaneRenderContextProtocol], bool]:
            return self.render_pass_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                footer_text=footer_text,
                live_status=live_status,
                clear_external_blank_rows=clear_external_blank_rows,
            )

        return render_factory

    def restore_cursor(self) -> None:
        self._request_runner.restore_cursor()

    def run_external_repaint(
        self,
        repaint: Callable[[], _ExternalRepaintResult],
    ) -> _ExternalRepaintResult:
        return self._request_runner.run_external_repaint(repaint)


def terminal_bottom_pane_cursor_move(frame: TerminalBottomPaneFrame) -> LiveViewportCursorMove:
    """Return the terminal cursor move projection for compatibility callers.

    Rust owner: ``codex-tui::custom_terminal`` owns the terminal cursor side
    effect. This adapter derives the compatibility callback target from the
    bottom-pane frame without making the frame model own backend concerns.
    """

    return LiveViewportCursorMove(row=frame.cursor_row, column=frame.cursor_column)


def terminal_bottom_pane_live_viewport_request(
    frame: TerminalBottomPaneFrame,
    *,
    buffer: RatatuiBuffer,
    include_cursor_position: bool = True,
    clear_external_blank_rows: bool = False,
) -> LiveViewportRenderRequest:
    """Project a bottom-pane frame into a generic live-viewport request.

    Rust owners: ``codex-tui::chatwidget::rendering`` owns frame geometry, and
    ``codex-tui::custom_terminal`` owns the generic render request consumed by
    the backend. The request runner should bridge this request without
    recomputing row widths, blank rows, or cursor position.
    """

    return LiveViewportRenderRequest.from_writes(
        clear_rows=frame.clear_rows,
        buffer=buffer,
        writes=frame.writes,
        cursor_row=frame.cursor_row,
        cursor_column=frame.cursor_column,
        include_cursor_position=include_cursor_position,
        clear_external_blank_rows=clear_external_blank_rows,
    )


def terminal_bottom_pane_frame_live_viewport_update(
    frame: TerminalBottomPaneFrame,
    *,
    buffer: RatatuiBuffer,
    include_cursor_position: bool = True,
    clear_external_blank_rows: bool = False,
    flush: bool = False,
) -> LiveViewportProjection:
    """Project a bottom-pane frame into a generic live-viewport update."""

    request = terminal_bottom_pane_live_viewport_request(
        frame,
        buffer=buffer,
        include_cursor_position=include_cursor_position,
        clear_external_blank_rows=clear_external_blank_rows,
    )
    return LiveViewportProjection(
        update=LiveViewportUpdate.render(request, flush=flush),
        cursor_move=terminal_bottom_pane_cursor_move(frame),
    )


def terminal_bottom_pane_frame_projection(
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    clear_active_tail_height: int = 0,
    clear_composer_height: int = 1,
) -> TerminalBottomPaneFrameProjection:
    """Build the bottom-pane frame and buffer projection for custom_terminal.

    Rust owner: ``codex-tui::chatwidget::rendering`` owns the frame-to-buffer
    content projection. This Python-only adapter pairs that projection with the
    bottom-pane frame rows so the terminal surface never rebuilds frames or
    buffers itself.
    """

    frame = terminal_bottom_pane_frame(
        size,
        state,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
        clear_active_tail_height=clear_active_tail_height,
        clear_composer_height=clear_composer_height,
    )
    return TerminalBottomPaneFrameProjection(
        frame=frame,
        buffer=terminal_bottom_pane_frame_buffer(size, frame),
    )


def terminal_bottom_pane_live_viewport_update_for_cursor_policy(
    size: os.terminal_size,
    plan: TerminalBottomPaneActionPlan,
    *,
    projection_policy: LiveViewportProjectionPolicy | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    clear_external_blank_rows: bool = False,
    clear_active_tail_height: int = 0,
    clear_composer_height: int = 1,
) -> LiveViewportProjection | None:
    """Project an action plan using the terminal cursor routing policy."""

    policy = projection_policy or LiveViewportProjectionPolicy()
    return terminal_bottom_pane_live_viewport_update(
        size,
        plan,
        include_cursor_position=live_viewport_backend_cursor_position_enabled(
            external_cursor_move=policy.external_cursor_move,
            cursor_visible=policy.cursor_visible,
        ),
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
        clear_external_blank_rows=clear_external_blank_rows,
        clear_active_tail_height=clear_active_tail_height,
        clear_composer_height=clear_composer_height,
    )


def terminal_bottom_pane_request_live_viewport_update(
    size: os.terminal_size,
    request: TerminalBottomPaneRequest,
    *,
    projection_policy: LiveViewportProjectionPolicy | None = None,
) -> LiveViewportProjection | None:
    """Project a bottom-pane request into the custom-terminal update boundary.

    Rust owners: ``codex-tui::bottom_pane`` owns the clear/render request and
    ``codex-tui::custom_terminal`` owns the live viewport update contract. The
    terminal surface should bridge the prepared request without unpacking
    popup/status/cursor cleanup fields itself.
    """

    return _terminal_bottom_pane_request_live_viewport_update(
        size,
        request,
        projection_policy=projection_policy,
        plan=request.action_plan(),
        cleanup=request.projection_cleanup(),
    )


def _terminal_bottom_pane_request_live_viewport_update(
    size: os.terminal_size,
    request: TerminalBottomPaneRequest,
    *,
    projection_policy: LiveViewportProjectionPolicy | None,
    plan: TerminalBottomPaneActionPlan,
    cleanup: ProjectionCleanupShape,
) -> LiveViewportProjection | None:
    """Project a pre-planned bottom-pane request inside this adapter only."""

    return terminal_bottom_pane_live_viewport_update_for_cursor_policy(
        size,
        plan,
        projection_policy=projection_policy,
        clear_popup_height=cleanup.clear_popup_height,
        clear_live_status_active=cleanup.clear_live_status_active,
        clear_external_blank_rows=cleanup.clear_external_blank_rows,
        clear_active_tail_height=cleanup.clear_active_tail_height,
        clear_composer_height=cleanup.clear_composer_height,
    )


def terminal_bottom_pane_live_viewport_projection_cycle(
    request: TerminalBottomPaneRequest,
) -> LiveViewportProjectionCycle:
    """Prepare the custom-terminal projection-cycle inputs for a request.

    Rust owner: ``codex-tui::custom_terminal`` owns the live-viewport cycle,
    while ``codex-tui::bottom_pane`` owns request gating. This bridge packages
    both so terminal adapters do not call ``action_plan`` or inspect request
    cursor policy directly.
    """

    plan = request.action_plan()
    cleanup = request.projection_cleanup()

    def project(size: os.terminal_size, policy: LiveViewportProjectionPolicy) -> LiveViewportProjection | None:
        return _terminal_bottom_pane_request_live_viewport_update(
            size,
            request,
            projection_policy=policy,
            plan=plan,
            cleanup=cleanup,
        )

    return LiveViewportProjectionCycle(
        project=project,
        should_run=plan.should_run,
        check_resize=plan.check_resize,
        cursor_visible=request.projection_cursor_visible(),
    )


def terminal_bottom_pane_live_viewport_update(
    size: os.terminal_size,
    plan: TerminalBottomPaneActionPlan,
    *,
    include_cursor_position: bool = True,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    clear_external_blank_rows: bool = False,
    clear_active_tail_height: int = 0,
    clear_composer_height: int = 1,
) -> LiveViewportProjection | None:
    """Project a bottom-pane action plan into a generic live-viewport update."""

    if plan.action == "clear":
        return LiveViewportProjection(
            update=LiveViewportUpdate.clear(
                _terminal_bottom_pane_clear_request(
                    size,
                    live_status_active=plan.live_status_active or clear_live_status_active,
                    popup_height=clear_popup_height,
                    active_tail_height=clear_active_tail_height,
                    composer_height=clear_composer_height,
                ),
                flush=plan.flush,
            )
        )
    if plan.action == "render" and plan.state is not None:
        projection = terminal_bottom_pane_frame_projection(
            size,
            plan.state,
            clear_popup_height=clear_popup_height,
            clear_live_status_active=clear_live_status_active,
            clear_active_tail_height=clear_active_tail_height,
            clear_composer_height=clear_composer_height,
        )
        return terminal_bottom_pane_frame_live_viewport_update(
            projection.frame,
            buffer=projection.buffer,
            include_cursor_position=include_cursor_position,
            clear_external_blank_rows=clear_external_blank_rows,
            flush=plan.flush,
        )
    return None


__all__ = [
    "TerminalBottomPaneRequestRunner",
    "terminal_bottom_pane_live_viewport_projection_cycle",
]
