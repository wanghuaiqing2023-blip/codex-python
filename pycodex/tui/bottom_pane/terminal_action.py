"""Terminal bottom-pane action/state planning for the hybrid backend.

This module prepares bottom-pane clear/render actions before the frame layer
projects them into a ratatui-like buffer. It keeps TTY/layout gating and frame
input state outside terminal adapters so ``chatwidget.rendering`` can remain
focused on Frame/Buffer content projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from .selection_popup_common import TerminalPopupLine as TerminalBottomPanePopupLine
from ..chatwidget.status_surfaces import TerminalLiveStatusSurface


@dataclass(frozen=True)
class TerminalBottomPaneState:
    draft: str = ""
    footer_text: str = ""
    live_status_text: str | None = None
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = ()

    @property
    def live_status_active(self) -> bool:
        return bool(self.live_status_text)

    @property
    def popup_height(self) -> int:
        return len(self.popup_lines)


@dataclass(frozen=True)
class TerminalBottomPaneActionPlan:
    """Terminal side-effect plan for clear/render bottom-pane actions."""

    action: str
    check_resize: bool = False
    state: TerminalBottomPaneState | None = None
    live_status_active: bool = False
    flush: bool = False

    @property
    def should_run(self) -> bool:
        return self.action != "skip"


@dataclass(frozen=True)
class TerminalBottomPaneProjectionCleanup:
    """Bottom-pane cleanup metadata consumed by terminal projection adapters."""

    clear_popup_height: int = 0
    clear_live_status_active: bool = False
    clear_external_blank_rows: bool = False


class TerminalBottomPaneRenderContextProtocol(Protocol):
    """Bottom-pane render context consumed by terminal request builders."""

    draft: str
    popup_lines: tuple[TerminalBottomPanePopupLine, ...]
    cursor_visible: bool


class TerminalBottomPaneRenderPassProtocol(Protocol):
    """Resize-owned render pass consumed by terminal request builders."""

    check_resize: bool
    clear_popup_height: int
    clear_live_status_active: bool


@dataclass(frozen=True)
class TerminalBottomPaneClearRequest:
    """Bottom-pane-owned request for clearing the terminal live pane."""

    stdin_is_terminal: bool
    layout_active: bool
    live_status: TerminalLiveStatusSurface
    check_resize: bool = True

    def action_plan(self) -> TerminalBottomPaneActionPlan:
        return terminal_bottom_pane_clear_plan(
            stdin_is_terminal=self.stdin_is_terminal,
            layout_active=self.layout_active,
            check_resize=self.check_resize,
            live_status=self.live_status,
        )

    def projection_cleanup(self) -> TerminalBottomPaneProjectionCleanup:
        return TerminalBottomPaneProjectionCleanup()

    def projection_cursor_visible(self) -> bool | None:
        return None


@dataclass(frozen=True)
class TerminalBottomPaneRenderRequest:
    """Bottom-pane-owned request for rendering the terminal live pane."""

    stdin_is_terminal: bool
    layout_active: bool
    draft: str
    footer_text: str
    live_status: TerminalLiveStatusSurface
    check_resize: bool = True
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = ()
    cursor_visible: bool = True
    clear_popup_height: int = 0
    clear_live_status_active: bool = False
    clear_external_blank_rows: bool = False

    def action_plan(self) -> TerminalBottomPaneActionPlan:
        return terminal_bottom_pane_render_plan(
            stdin_is_terminal=self.stdin_is_terminal,
            layout_active=self.layout_active,
            check_resize=self.check_resize,
            draft=self.draft,
            footer_text=self.footer_text,
            popup_lines=self.popup_lines,
            live_status=self.live_status,
        )

    def projection_cleanup(self) -> TerminalBottomPaneProjectionCleanup:
        return TerminalBottomPaneProjectionCleanup(
            clear_popup_height=self.clear_popup_height,
            clear_live_status_active=self.clear_live_status_active,
            clear_external_blank_rows=self.clear_external_blank_rows,
        )

    def projection_cursor_visible(self) -> bool | None:
        return self.cursor_visible


TerminalBottomPaneRequest: TypeAlias = TerminalBottomPaneClearRequest | TerminalBottomPaneRenderRequest


def terminal_bottom_pane_clear_request(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    live_status: TerminalLiveStatusSurface,
    check_resize: bool = True,
) -> TerminalBottomPaneClearRequest:
    """Build the bottom-pane-owned clear request consumed by terminal adapters."""

    return TerminalBottomPaneClearRequest(
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=check_resize,
        live_status=live_status,
    )


def terminal_bottom_pane_render_request(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    render_context: TerminalBottomPaneRenderContextProtocol,
    footer_text: str,
    live_status: TerminalLiveStatusSurface,
    check_resize: bool = True,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    clear_external_blank_rows: bool = False,
) -> TerminalBottomPaneRenderRequest:
    """Build the bottom-pane-owned render request from render context.

    Rust owner: ``codex-tui::bottom_pane`` owns the active-view/popup render
    context and cursor policy. Terminal controllers should pass the observed
    context here instead of unpacking it into the surface adapter.
    """

    return TerminalBottomPaneRenderRequest(
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=check_resize,
        draft=str(render_context.draft),
        footer_text=footer_text,
        popup_lines=tuple(render_context.popup_lines),
        live_status=live_status,
        cursor_visible=bool(render_context.cursor_visible),
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
        clear_external_blank_rows=clear_external_blank_rows,
    )


def terminal_bottom_pane_render_request_for_pass(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    render_context: TerminalBottomPaneRenderContextProtocol,
    footer_text: str,
    live_status: TerminalLiveStatusSurface,
    render_pass: TerminalBottomPaneRenderPassProtocol,
    clear_external_blank_rows: bool = False,
) -> TerminalBottomPaneRenderRequest:
    """Build a render request from a resize-owned render pass.

    Rust owners: ``codex-tui::app::resize_reflow`` owns the render-pass
    timing fields, while ``codex-tui::bottom_pane`` owns the render request.
    Terminal controllers should pass the pass object through this owner helper
    instead of unpacking pass fields locally.
    """

    return terminal_bottom_pane_render_request(
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=bool(render_pass.check_resize),
        render_context=render_context,
        footer_text=footer_text,
        live_status=live_status,
        clear_popup_height=int(render_pass.clear_popup_height),
        clear_live_status_active=bool(render_pass.clear_live_status_active),
        clear_external_blank_rows=clear_external_blank_rows,
    )


def terminal_bottom_pane_clear_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan clearing the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="clear",
        check_resize=check_resize,
        live_status_active=live_status.footprint_active,
        flush=True,
    )


def terminal_bottom_pane_render_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    draft: str,
    footer_text: str,
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = (),
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan rendering the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="render",
        check_resize=check_resize,
        flush=True,
        state=TerminalBottomPaneState(
            draft=draft,
            footer_text=footer_text,
            live_status_text=live_status.render_text,
            popup_lines=tuple(popup_lines),
        ),
    )


__all__ = [
    "TerminalBottomPaneActionPlan",
    "TerminalBottomPaneClearRequest",
    "TerminalBottomPaneProjectionCleanup",
    "TerminalBottomPaneRenderContextProtocol",
    "TerminalBottomPaneRenderPassProtocol",
    "TerminalBottomPaneRenderRequest",
    "TerminalBottomPaneRequest",
    "TerminalBottomPaneState",
    "terminal_bottom_pane_clear_request",
    "terminal_bottom_pane_clear_plan",
    "terminal_bottom_pane_render_request",
    "terminal_bottom_pane_render_request_for_pass",
    "terminal_bottom_pane_render_plan",
]
