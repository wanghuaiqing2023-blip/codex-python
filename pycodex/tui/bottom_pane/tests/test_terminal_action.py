from pycodex.tui.bottom_pane.selection_popup_common import TerminalPopupLine as TerminalBottomPanePopupLine
from pycodex.tui.bottom_pane.terminal_action import (
    TerminalBottomPaneClearRequest,
    TerminalBottomPaneProjectionCleanup,
    TerminalBottomPaneRenderRequest,
    TerminalBottomPaneRequest,
    TerminalBottomPaneState,
    terminal_bottom_pane_clear_request,
    terminal_bottom_pane_clear_plan,
    terminal_bottom_pane_render_request,
    terminal_bottom_pane_render_request_for_pass,
    terminal_bottom_pane_render_plan,
)
from pycodex.tui.bottom_pane.view_stack import TerminalBottomPaneRenderContext
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface


def _request_action_name(request: TerminalBottomPaneRequest) -> str:
    return request.action_plan().action


def test_terminal_action_plans_skip_or_prepare_clear_and_render() -> None:
    # Rust owners: codex-tui::bottom_pane decides whether the bottom pane is
    # active and what state should be drawn. chatwidget.rendering should receive a
    # prepared state instead of owning TTY/layout gating.
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    skip = terminal_bottom_pane_render_plan(
        stdin_is_terminal=False,
        layout_active=True,
        check_resize=True,
        draft="hi",
        footer_text="footer",
        live_status=active,
    )
    clear = terminal_bottom_pane_clear_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=True,
        live_status=active,
    )
    render = terminal_bottom_pane_render_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hi",
        footer_text="footer",
        popup_lines=(TerminalBottomPanePopupLine("/model", True),),
        live_status=active,
    )

    assert not skip.should_run
    assert skip.flush is False
    assert clear.action == "clear"
    assert clear.check_resize is True
    assert clear.live_status_active is True
    assert clear.flush is True
    assert render.action == "render"
    assert render.check_resize is False
    assert render.flush is True
    assert render.state == TerminalBottomPaneState(
        draft="hi",
        footer_text="footer",
        live_status_text="\u2022 Working",
        popup_lines=(TerminalBottomPanePopupLine("/model", True),),
    )


def test_terminal_bottom_pane_state_tracks_live_status_and_popup_height() -> None:
    # Rust owners: codex-tui::bottom_pane::chat_composer and active
    # BottomPaneView state determine whether status/popup rows should
    # participate in the next frame.
    idle = TerminalBottomPaneState()
    active = TerminalBottomPaneState(
        live_status_text="\u2022 Working",
        popup_lines=(
            TerminalBottomPanePopupLine("/model", True),
            TerminalBottomPanePopupLine("/memories", False),
        ),
    )

    assert not idle.live_status_active
    assert idle.popup_height == 0
    assert active.live_status_active
    assert active.popup_height == 2


def test_terminal_adapter_requests_project_to_owner_action_plans() -> None:
    # Rust owners: codex-tui::bottom_pane owns the semantic clear/render
    # request, while terminal adapters should only consume the prepared request
    # and bridge it into custom_terminal.
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")
    popup = (TerminalBottomPanePopupLine("/model", True),)

    clear = TerminalBottomPaneClearRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=active,
    )
    render = TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="/m",
        footer_text="gpt-test high",
        popup_lines=popup,
        live_status=active,
        cursor_visible=False,
        clear_popup_height=2,
        clear_live_status_active=True,
        clear_external_blank_rows=True,
    )

    clear_plan = clear.action_plan()
    render_plan = render.action_plan()

    assert clear_plan.action == "clear"
    assert clear_plan.check_resize is False
    assert clear_plan.live_status_active is True
    assert render_plan.action == "render"
    assert render_plan.check_resize is False
    assert render_plan.state == TerminalBottomPaneState(
        draft="/m",
        footer_text="gpt-test high",
        live_status_text="\u2022 Working",
        popup_lines=popup,
    )
    assert render.cursor_visible is False
    assert clear.projection_cleanup() == TerminalBottomPaneProjectionCleanup()
    assert render.projection_cleanup() == TerminalBottomPaneProjectionCleanup(
        clear_popup_height=2,
        clear_live_status_active=True,
        clear_external_blank_rows=True,
    )
    assert clear.projection_cursor_visible() is None
    assert render.projection_cursor_visible() is False


def test_terminal_bottom_pane_request_alias_covers_clear_and_render_requests() -> None:
    # Rust owner: codex-tui::bottom_pane owns the semantic request boundary
    # consumed by terminal adapters and terminal_projection. Adapters should use
    # this owner alias instead of spelling out a clear/render union.
    active = TerminalLiveStatusSurface.inactive()
    clear = TerminalBottomPaneClearRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=active,
    )
    render = TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hi",
        footer_text="gpt-test high",
        live_status=active,
    )

    assert _request_action_name(clear) == "clear"
    assert _request_action_name(render) == "render"


def test_terminal_action_builds_surface_requests_from_bottom_pane_context() -> None:
    # Rust owner: codex-tui::bottom_pane owns the render context and cursor
    # policy. terminal_controller should pass that context to this owner helper
    # instead of unpacking draft/popup/cursor fields into terminal adapters.
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")
    popup = (TerminalBottomPanePopupLine("/model", True),)
    context = TerminalBottomPaneRenderContext(
        draft="/m",
        popup_lines=popup,
        popup_height=1,
        popup_is_active_view=False,
        cursor_visible=False,
    )

    clear = terminal_bottom_pane_clear_request(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=active,
    )
    render = terminal_bottom_pane_render_request(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        render_context=context,
        footer_text="gpt-test high",
        live_status=active,
        clear_popup_height=3,
        clear_live_status_active=True,
        clear_external_blank_rows=True,
    )

    assert clear == TerminalBottomPaneClearRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=active,
    )
    assert render == TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="/m",
        footer_text="gpt-test high",
        popup_lines=popup,
        live_status=active,
        cursor_visible=False,
        clear_popup_height=3,
        clear_live_status_active=True,
        clear_external_blank_rows=True,
    )


def test_terminal_action_builds_render_request_from_resize_pass() -> None:
    # Rust owners: codex-tui::app::resize_reflow owns the render-pass timing
    # fields, and codex-tui::bottom_pane owns the render request. The terminal
    # controller should pass the pass object through this helper rather than
    # unpacking clear/check fields itself.
    class PassState:
        check_resize = False
        clear_popup_height = 4
        clear_live_status_active = True

    active = TerminalLiveStatusSurface.active_status("\u2022 Working")
    context = TerminalBottomPaneRenderContext(
        draft="hi",
        cursor_visible=True,
    )

    render = terminal_bottom_pane_render_request_for_pass(
        stdin_is_terminal=True,
        layout_active=True,
        render_context=context,
        footer_text="gpt-test high",
        live_status=active,
        render_pass=PassState(),
        clear_external_blank_rows=True,
    )

    assert render == TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hi",
        footer_text="gpt-test high",
        live_status=active,
        cursor_visible=True,
        clear_popup_height=4,
        clear_live_status_active=True,
        clear_external_blank_rows=True,
    )
