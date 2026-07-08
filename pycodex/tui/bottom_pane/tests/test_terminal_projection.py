import io
import os

from pycodex.tui.bottom_pane.chat_composer import terminal_composer_line_text
from pycodex.tui.bottom_pane.selection_popup_common import TerminalPopupLine
from pycodex.tui.bottom_pane.terminal_action import (
    TerminalBottomPaneActionPlan,
    TerminalBottomPaneClearRequest,
    TerminalBottomPaneRenderRequest,
    TerminalBottomPaneState,
)
from pycodex.tui.bottom_pane.terminal_projection import (
    TerminalBottomPaneRequestRunner,
    terminal_bottom_pane_cursor_move,
    terminal_bottom_pane_frame_live_viewport_update,
    terminal_bottom_pane_frame_projection,
    terminal_bottom_pane_live_viewport_request,
    terminal_bottom_pane_live_viewport_projection_cycle,
    terminal_bottom_pane_live_viewport_update,
    terminal_bottom_pane_live_viewport_update_for_cursor_policy,
    terminal_bottom_pane_request_live_viewport_update,
)
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface
from pycodex.tui.chatwidget.rendering import terminal_bottom_pane_frame, terminal_bottom_pane_frame_buffer
from pycodex.tui.custom_terminal import (
    LiveViewportCursorMove,
    LiveViewportRenderer,
    LiveViewportProjectionCycle,
    LiveViewportProjectionPolicy,
    apply_live_viewport_update,
)
from pycodex.tui.ratatui_bridge import Position as RatatuiPosition
from pycodex.tui.ratatui_bridge import Rect as RatatuiRect


class FlushTrackingStringIO(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def _render_frame_update(
    writer: io.StringIO,
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    move_cursor=None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    live_viewport: LiveViewportRenderer | None = None,
    cursor_visible: bool = True,
    previous_buffer=None,
):
    frame = terminal_bottom_pane_frame(
        size,
        state,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
    )
    buffer = terminal_bottom_pane_frame_buffer(size, frame)
    projection = terminal_bottom_pane_frame_live_viewport_update(
        frame,
        buffer=buffer,
        include_cursor_position=move_cursor is None and cursor_visible,
    )
    apply_live_viewport_update(
        writer,
        projection.update,
        live_viewport=live_viewport,
        previous_buffer=previous_buffer,
    )
    if move_cursor is not None and cursor_visible and projection.cursor_move is not None:
        move_cursor(projection.cursor_move.row, projection.cursor_move.column)
    return buffer


def test_terminal_projection_projects_bottom_pane_action_to_live_viewport_update() -> None:
    # Rust owners: bottom_pane owns the clear/render action plan,
    # chatwidget::rendering owns frame projection, and custom_terminal consumes
    # the generic live viewport update. Terminal adapters should not interpret
    # the plan or call backend clear/render/flush helpers directly.
    size = os.terminal_size((40, 12))
    clear = terminal_bottom_pane_live_viewport_update(
        size,
        TerminalBottomPaneActionPlan(action="clear", live_status_active=False, flush=True),
    )

    assert clear is not None
    assert clear.update.kind == "clear"
    assert clear.update.flush is True
    assert clear.update.clear_request is not None
    assert clear.update.clear_request.rows == (9, 10, 11, 12)
    assert clear.cursor_move is None

    render = terminal_bottom_pane_live_viewport_update(
        size,
        TerminalBottomPaneActionPlan(
            action="render",
            state=TerminalBottomPaneState(draft="hi", footer_text="gpt-test high"),
            flush=True,
        ),
        include_cursor_position=False,
    )

    assert render is not None
    assert render.update.kind == "render"
    assert render.update.flush is True
    assert render.update.render_request is not None
    assert render.update.render_request.cursor_position is None
    assert render.cursor_move is not None
    assert render.cursor_move.row == 10
    assert render.cursor_move.column == len(terminal_composer_line_text("hi")) + 1


def test_terminal_projection_pairs_frame_and_buffer() -> None:
    # Rust owner: codex-tui::chatwidget::rendering owns the bottom-pane
    # frame/buffer content projection. terminal_projection is the Python-only
    # adapter that pairs frame rows with that buffer projection.
    size = os.terminal_size((40, 12))
    state = TerminalBottomPaneState(draft="hi", footer_text="gpt-test high")

    projection = terminal_bottom_pane_frame_projection(size, state)

    assert projection.frame == terminal_bottom_pane_frame(size, state)
    assert projection.buffer.area == RatatuiRect.new(0, 8, 40, 4)
    assert "\u203a hi" in projection.buffer.to_plain_text()


def test_terminal_projection_builds_live_viewport_render_request() -> None:
    # Rust owners: chatwidget::rendering owns bottom-pane frame geometry, while
    # custom_terminal consumes the generic live-viewport request. The terminal
    # surface should not recompute row widths, blank rows, or cursor position.
    size = os.terminal_size((32, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="hi", footer_text="gpt-test high"),
        clear_popup_height=5,
    )
    buffer = terminal_bottom_pane_frame_buffer(size, frame)

    request = terminal_bottom_pane_live_viewport_request(
        frame,
        buffer=buffer,
        include_cursor_position=True,
        clear_external_blank_rows=True,
    )

    assert request.clear_rows == frame.clear_rows
    assert request.buffer is buffer
    assert request.cursor_position == RatatuiPosition.new(len(terminal_composer_line_text("hi")), 9)
    assert request.minimum_row_widths == {
        9: len(terminal_composer_line_text("hi")),
        11: len("gpt-test high"),
    }
    assert request.external_blank_rows == (6, 7, 8, 9, 11)

    update = terminal_bottom_pane_frame_live_viewport_update(
        frame,
        buffer=buffer,
        include_cursor_position=False,
        clear_external_blank_rows=True,
        flush=True,
    )
    assert update.update.kind == "render"
    assert update.update.flush is True
    assert update.update.render_request is not None
    assert update.update.render_request.cursor_position is None
    assert update.update.render_request.external_blank_rows == (6, 7, 8, 9, 11)
    assert update.cursor_move is not None
    assert isinstance(update.cursor_move, LiveViewportCursorMove)
    assert update.cursor_move.row == frame.cursor_row
    assert terminal_bottom_pane_cursor_move(frame) == LiveViewportCursorMove(
        row=frame.cursor_row,
        column=frame.cursor_column,
    )


def test_terminal_projection_request_delegates_cursor_position_to_custom_terminal_owner() -> None:
    # Rust owners: chatwidget::rendering owns composer cursor placement, while
    # custom_terminal owns the zero-based frame cursor consumed during draw.
    # The projection adapter should expose only the prepared render request.
    frame = terminal_bottom_pane_frame(
        os.terminal_size((32, 12)),
        TerminalBottomPaneState(draft="/m", footer_text="gpt-test high"),
    )
    buffer = terminal_bottom_pane_frame_buffer(os.terminal_size((32, 12)), frame)

    request = terminal_bottom_pane_live_viewport_request(frame, buffer=buffer)
    assert request.cursor_position == RatatuiPosition.new(
        len(terminal_composer_line_text("/m")),
        9,
    )


def test_terminal_projection_applies_terminal_cursor_routing_policy() -> None:
    # Rust owners: chatwidget::rendering owns frame cursor placement and
    # custom_terminal consumes it during backend draw. The terminal surface
    # should not duplicate the policy that disables backend cursor placement
    # when an external compatibility cursor callback is present.
    size = os.terminal_size((32, 12))
    plan = TerminalBottomPaneActionPlan(
        action="render",
        state=TerminalBottomPaneState(draft="hi", footer_text="gpt-test high"),
    )

    backend_cursor = terminal_bottom_pane_live_viewport_update_for_cursor_policy(size, plan)
    external_cursor = terminal_bottom_pane_live_viewport_update_for_cursor_policy(
        size,
        plan,
        projection_policy=LiveViewportProjectionPolicy(external_cursor_move=True),
    )
    hidden_cursor = terminal_bottom_pane_live_viewport_update_for_cursor_policy(
        size,
        plan,
        projection_policy=LiveViewportProjectionPolicy(cursor_visible=False),
    )

    assert backend_cursor is not None
    assert backend_cursor.update.render_request is not None
    assert backend_cursor.update.render_request.cursor_position == RatatuiPosition.new(
        len(terminal_composer_line_text("hi")),
        9,
    )

    assert external_cursor is not None
    assert external_cursor.update.render_request is not None
    assert external_cursor.update.render_request.cursor_position is None

    assert hidden_cursor is not None
    assert hidden_cursor.update.render_request is not None
    assert hidden_cursor.update.render_request.cursor_position is None


def test_terminal_projection_projects_bottom_pane_request_without_surface_unpacking() -> None:
    # Rust owners: bottom_pane owns request semantics and custom_terminal owns
    # live-viewport update metadata. Terminal adapters should pass the request to
    # this projection bridge without unpacking cleanup or cursor-policy fields.
    size = os.terminal_size((32, 12))
    clear = terminal_bottom_pane_request_live_viewport_update(
        size,
        TerminalBottomPaneClearRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=False,
            live_status=TerminalLiveStatusSurface.inactive(),
        ),
    )
    render = terminal_bottom_pane_request_live_viewport_update(
        size,
        TerminalBottomPaneRenderRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=False,
            draft="hi",
            footer_text="gpt-test high",
            live_status=TerminalLiveStatusSurface.inactive(),
            clear_popup_height=5,
            clear_external_blank_rows=True,
        ),
        projection_policy=LiveViewportProjectionPolicy(external_cursor_move=True),
    )

    assert clear is not None
    assert clear.update.kind == "clear"
    assert clear.update.clear_request is not None
    assert clear.update.clear_request.rows == (9, 10, 11, 12)

    assert render is not None
    assert render.update.kind == "render"
    assert render.update.render_request is not None
    assert render.update.render_request.cursor_position is None
    assert render.update.render_request.external_blank_rows == (6, 7, 8, 9, 11)
    assert render.cursor_move is not None
    assert render.cursor_move.row == 10


def test_terminal_projection_prepares_live_viewport_cycle_from_request() -> None:
    # Rust owners: bottom_pane owns request gating and custom_terminal owns the
    # live-viewport lifecycle. Terminal adapters should consume this cycle
    # object instead of calling action_plan or reading request cursor fields.
    size = os.terminal_size((32, 12))
    clear_request = TerminalBottomPaneClearRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=TerminalLiveStatusSurface.inactive(),
    )
    render_request = TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=True,
        draft="hi",
        footer_text="gpt-test high",
        live_status=TerminalLiveStatusSurface.inactive(),
        cursor_visible=False,
        clear_popup_height=5,
        clear_external_blank_rows=True,
    )

    clear_cycle = terminal_bottom_pane_live_viewport_projection_cycle(clear_request)
    render_cycle = terminal_bottom_pane_live_viewport_projection_cycle(render_request)

    assert isinstance(clear_cycle, LiveViewportProjectionCycle)
    assert clear_cycle.should_run is True
    assert clear_cycle.check_resize is False
    assert clear_cycle.cursor_visible is None
    clear_projection = clear_cycle.project(size, LiveViewportProjectionPolicy())
    assert clear_projection is not None
    assert clear_projection.update.kind == "clear"

    assert isinstance(render_cycle, LiveViewportProjectionCycle)
    assert render_cycle.should_run is True
    assert render_cycle.check_resize is True
    assert render_cycle.cursor_visible is False
    render_projection = render_cycle.project(size, LiveViewportProjectionPolicy(cursor_visible=False))
    assert render_projection is not None
    assert render_projection.update.kind == "render"
    assert render_projection.update.render_request is not None
    assert render_projection.update.render_request.cursor_position is None
    assert render_projection.update.render_request.external_blank_rows == (6, 7, 8, 9, 11)


def test_terminal_projection_frame_update_diff_uses_custom_terminal_owner() -> None:
    # Rust owners: chatwidget::rendering owns bottom-pane frame/buffer content,
    # terminal_projection bridges that frame into custom_terminal, and
    # custom_terminal owns previous/current buffer diffing. Terminal adapters
    # should not carry this frame-diff proof.
    size = os.terminal_size((32, 12))
    previous_frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="hello", footer_text="gpt-test high"),
    )
    current_frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="hello", footer_text="gpt-test"),
    )
    previous_buffer = terminal_bottom_pane_frame_buffer(size, previous_frame)
    current_buffer = terminal_bottom_pane_frame_buffer(size, current_frame)
    writer = io.StringIO()

    projection = terminal_bottom_pane_frame_live_viewport_update(
        current_frame,
        buffer=current_buffer,
        include_cursor_position=False,
    )
    apply_live_viewport_update(
        writer,
        previous_buffer=previous_buffer,
        update=projection.update,
    )

    output = writer.getvalue()
    assert "\x1b[10;1H\u203a hello" not in output
    assert "\x1b[12;1H\x1b[2K" not in output
    assert "\x1b[12;1Hgpt-test" not in output
    assert "\x1b[12;9H\x1b[0K" in output


def test_terminal_projection_paints_status_composer_footer_and_cursor() -> None:
    # Rust owners: chatwidget::rendering owns row composition, terminal_projection
    # bridges the frame into a live-viewport update, and custom_terminal owns
    # the resulting ANSI repaint/cursor side effects.
    writer = io.StringIO()
    cursor: list[tuple[int, int]] = []
    size = os.terminal_size((40, 12))

    _render_frame_update(
        writer,
        size,
        TerminalBottomPaneState(
            draft="hello",
            footer_text="gpt-test high \u00b7 ~\\repo",
            live_status_text="\u2022 Working",
        ),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    output = writer.getvalue()
    assert "\x1b[r" in output
    assert "\x1b[7;1H\x1b[2K" in output
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hello" in output
    assert "\x1b[12;1Hgpt-test high \u00b7 ~\\repo" in output
    assert cursor == [(10, len(terminal_composer_line_text("hello")) + 1)]


def test_terminal_projection_uses_bridge_cursor_lifecycle_by_default() -> None:
    # Rust owner: codex-tui::custom_terminal applies Frame cursor position
    # through the backend after drawing the buffer. The projection bridge should
    # pass the frame cursor into ratatui_bridge instead of owning cursor movement
    # in terminal adapters.
    writer = io.StringIO()
    size = os.terminal_size((40, 12))

    _render_frame_update(
        writer,
        size,
        TerminalBottomPaneState(draft="hello", footer_text="gpt-test high"),
    )

    assert writer.getvalue().endswith(f"\x1b[10;{len(terminal_composer_line_text('hello')) + 1}H")


def test_terminal_projection_paints_slash_popup_below_composer_with_highlight() -> None:
    # Rust owners: command_popup/selection_popup_common own popup row content,
    # chatwidget::rendering places those rows below the composer, and
    # terminal_projection passes the selected-row style through custom_terminal.
    writer = io.StringIO()
    cursor: list[tuple[int, int]] = []
    size = os.terminal_size((72, 12))

    _render_frame_update(
        writer,
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(
                TerminalPopupLine("/model            choose what model and reasoning effort to use", True),
                TerminalPopupLine("/memories         configure memory use and generation", False),
            ),
        ),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    output = writer.getvalue()
    assert "\x1b[9;1H\u203a /m" in output
    assert "\x1b[10;1H\x1b[94m/model" in output
    assert "\x1b[7m/model" not in output
    assert "\x1b[11;1H/memories" in output
    assert "\x1b[12;1Hgpt-test high" in output
    assert cursor == [(9, len(terminal_composer_line_text("/m")) + 1)]


def test_terminal_projection_buffer_state_skips_unchanged_second_render() -> None:
    # Rust owner: codex-tui::custom_terminal keeps current/previous buffers so
    # unchanged live-pane frames do not repaint. Terminal adapters consume that
    # owner lifecycle through a request runner; it must not own buffer state.
    writer = io.StringIO()
    live_viewport = LiveViewportRenderer(writer)
    size = os.terminal_size((32, 12))
    pane = TerminalBottomPaneState(draft="hello", footer_text="gpt-test high")

    _render_frame_update(writer, size, pane, live_viewport=live_viewport)
    writer.seek(0)
    writer.truncate(0)
    _render_frame_update(writer, size, pane, live_viewport=live_viewport)

    output = writer.getvalue()
    assert "\x1b[10;1H\u203a hello" not in output
    assert "\x1b[12;1Hgpt-test high" not in output
    assert "\x1b[10;" in output


def test_terminal_projection_clears_external_blank_row_without_footer_repaint() -> None:
    # Rust owner: codex-tui::custom_terminal owns frame diffing while the hybrid
    # terminal adapter may need to repair live rows dirtied by ordinary
    # scrollback writes. That repair must target blank frame rows instead of
    # falling back to a full footer repaint.
    writer = io.StringIO()
    size = os.terminal_size((32, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="hello", footer_text="gpt-test high"),
    )
    buffer = terminal_bottom_pane_frame_buffer(size, frame)

    first_projection = terminal_bottom_pane_frame_live_viewport_update(
        frame,
        buffer=buffer,
        include_cursor_position=False,
    )
    apply_live_viewport_update(
        writer,
        first_projection.update,
        previous_buffer=None,
    )
    writer.seek(0)
    writer.truncate(0)
    second_projection = terminal_bottom_pane_frame_live_viewport_update(
        frame,
        buffer=buffer,
        include_cursor_position=False,
        clear_external_blank_rows=True,
    )
    apply_live_viewport_update(
        writer,
        second_projection.update,
        previous_buffer=buffer,
    )

    output = writer.getvalue()
    assert "\x1b[9;1H\x1b[2K" in output
    assert "\x1b[11;1H\x1b[2K" in output
    assert "\x1b[10;1H\u203a hello" not in output
    assert "\x1b[12;1Hgpt-test high" not in output


def test_terminal_projection_can_suppress_frame_cursor() -> None:
    # Rust owner: codex-tui::custom_terminal::try_draw hides the cursor when a
    # frame does not provide cursor_position. During active turns the terminal
    # adapter must still draw the bottom pane but not hand off a composer cursor.
    writer = io.StringIO()
    live_viewport = LiveViewportRenderer(writer)
    size = os.terminal_size((32, 12))
    pane = TerminalBottomPaneState(draft="hello", footer_text="gpt-test high")

    _render_frame_update(writer, size, pane, live_viewport=live_viewport)
    writer.seek(0)
    writer.truncate(0)
    _render_frame_update(writer, size, pane, live_viewport=live_viewport, cursor_visible=False)

    output = writer.getvalue()
    assert "\x1b[10;1H\u203a hello" not in output
    assert "\x1b[12;1Hgpt-test high" not in output
    assert f"\x1b[10;{len(terminal_composer_line_text('hello')) + 1}H" not in output


def test_terminal_projection_preserves_empty_composer_prompt_space_through_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal renders the live composer prompt
    # through a buffer without losing semantic trailing spaces in the viewport.
    writer = io.StringIO()

    _render_frame_update(
        writer,
        os.terminal_size((32, 12)),
        TerminalBottomPaneState(draft="", footer_text="gpt-test high"),
        move_cursor=lambda _row, _column: None,
    )

    assert "\x1b[10;1H\u203a " in writer.getvalue()


def test_terminal_projection_clears_previous_larger_popup_footprint() -> None:
    # Rust owners: chatwidget::rendering and custom_terminal jointly define the
    # rows cleared when the live bottom pane shrinks from a larger popup.
    writer = io.StringIO()
    size = os.terminal_size((72, 12))

    _render_frame_update(
        writer,
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(TerminalPopupLine("/model choose", True),),
        ),
        clear_popup_height=3,
    )

    output = writer.getvalue()
    assert "\x1b[8;1H\x1b[2K" in output
    assert "\x1b[9;1H\x1b[2K" in output
    assert "\x1b[10;1H\x1b[2K" in output
    assert "\x1b[11;1H\x1b[2K" in output
    assert "\x1b[12;1H\x1b[2K" in output
    assert "\x1b[10;1H\x1b[94m/model choose\x1b[0m" in output


def test_terminal_projection_frame_update_does_not_flush_without_policy() -> None:
    # Rust owner: codex-tui::custom_terminal owns frame repaint side effects,
    # while controller/runtime boundaries decide when to flush product output.
    writer = FlushTrackingStringIO()
    size = os.terminal_size((40, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="hi", footer_text="gpt-test high"),
    )
    buffer = terminal_bottom_pane_frame_buffer(size, frame)
    projection = terminal_bottom_pane_frame_live_viewport_update(
        frame,
        buffer=buffer,
        flush=False,
    )

    apply_live_viewport_update(writer, projection.update)

    assert writer.flush_count == 0
    output = writer.getvalue()
    assert "\x1b[10;1H\u203a hi" in output
    assert "\x1b[12;1Hgpt-test high" in output


def test_terminal_bottom_pane_request_runner_executes_clear_and_render() -> None:
    # Rust owners: bottom_pane owns the prepared action, chatwidget::rendering
    # owns frame/buffer projection, and custom_terminal owns terminal repaint.
    # The surface adapter should pass the owner projection factory into
    # custom_terminal's live-viewport lifecycle; controller wrappers must not
    # rebuild frames themselves.
    clear_writer = FlushTrackingStringIO()
    render_writer = FlushTrackingStringIO()
    size = os.terminal_size((40, 12))
    clear_runner = TerminalBottomPaneRequestRunner(
        clear_writer,
        terminal_size=lambda: size,
        resize=lambda: None,
    )
    render_runner = TerminalBottomPaneRequestRunner(
        render_writer,
        terminal_size=lambda: size,
        resize=lambda: None,
    )
    ran_clear = clear_runner.run(
        TerminalBottomPaneClearRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=False,
            live_status=TerminalLiveStatusSurface.inactive(),
        ),
    )
    ran_render = render_runner.run(
        TerminalBottomPaneRenderRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=False,
            draft="hi",
            footer_text="gpt-test high",
            live_status=TerminalLiveStatusSurface.inactive(),
        ),
    )

    assert ran_clear is True
    assert ran_render is True
    assert clear_writer.flush_count == 1
    assert "\x1b[9;1H\x1b[2K" in clear_writer.getvalue()
    assert render_writer.flush_count == 1
    assert "\x1b[10;1H\u203a hi" in render_writer.getvalue()
    assert "\x1b[12;1Hgpt-test high" in render_writer.getvalue()


def test_terminal_bottom_pane_request_runner_builds_clear_and_render_pass_requests() -> None:
    # Rust owners: codex-tui::bottom_pane owns clear/render request semantics,
    # app::resize_reflow owns render-pass timing, and custom_terminal owns the
    # projection lifecycle. terminal_controller should call this runner boundary
    # instead of importing request builders or render-pass protocols.
    class RenderContext:
        draft = "hi"
        popup_lines = ()
        cursor_visible = True

    class RenderPass:
        check_resize = False
        clear_popup_height = 0
        clear_live_status_active = False

    clear_writer = FlushTrackingStringIO()
    render_writer = FlushTrackingStringIO()
    size = os.terminal_size((40, 12))
    clear_runner = TerminalBottomPaneRequestRunner(
        clear_writer,
        terminal_size=lambda: size,
        resize=lambda: None,
    )
    render_runner = TerminalBottomPaneRequestRunner(
        render_writer,
        terminal_size=lambda: size,
        resize=lambda: None,
    )

    ran_clear = clear_runner.run_clear(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=TerminalLiveStatusSurface.inactive(),
    )
    ran_render = render_runner.run_render_pass(
        stdin_is_terminal=True,
        layout_active=True,
        render_context=RenderContext(),
        footer_text="gpt-test high",
        live_status=TerminalLiveStatusSurface.inactive(),
        render_pass=RenderPass(),
    )

    assert ran_clear is True
    assert ran_render is True
    assert "\x1b[9;1H\x1b[2K" in clear_writer.getvalue()
    assert "\x1b[10;1H\u203a hi" in render_writer.getvalue()
    assert "\x1b[12;1Hgpt-test high" in render_writer.getvalue()


def test_terminal_bottom_pane_request_runner_builds_resize_reflow_clear_callback() -> None:
    # Rust owners: app::resize_reflow owns clear-cycle remembered footprint
    # state, bottom_pane owns clear request semantics, and custom_terminal owns
    # the request lifecycle. The projection runner should package terminal
    # environment values into the callback so terminal_controller does not
    # define a local clear-request closure.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    callback = runner.clear_callback(
        stdin_is_terminal=lambda: calls.append("tty") or True,
        layout_active=lambda: calls.append("layout") or True,
        check_resize=True,
        live_status=TerminalLiveStatusSurface.inactive(),
    )

    assert callback() is True
    assert calls == ["tty", "layout", "resize"]
    assert "\x1b[9;1H\x1b[2K" in writer.getvalue()
    assert writer.flush_count == 1


def test_terminal_bottom_pane_request_runner_builds_resize_reflow_clear_factory() -> None:
    # Rust owners: app::resize_reflow owns clear-cycle timing and asks for a
    # live-status/check-resize clear factory; terminal_projection owns packaging
    # that factory into bottom-pane requests so terminal_controller stays glue.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    clear_factory = runner.clear_factory_callback(
        stdin_is_terminal=lambda: calls.append("tty") or True,
        layout_active=lambda: calls.append("layout") or True,
    )

    clear = clear_factory(TerminalLiveStatusSurface.inactive(), False)

    assert clear() is True
    assert calls == ["tty", "layout"]
    assert "\x1b[9;1H\x1b[2K" in writer.getvalue()
    assert writer.flush_count == 1


def test_terminal_bottom_pane_request_runner_builds_resize_reflow_render_callback() -> None:
    # Rust owners: app::resize_reflow owns render-pass timing, bottom_pane owns
    # render context, and custom_terminal owns the request lifecycle. The
    # projection runner should package those values into a callback so
    # terminal_controller does not define pass/context unpacking closures.
    class RenderContext:
        draft = "hi"
        popup_lines = ()
        cursor_visible = True

    class RenderPass:
        check_resize = False
        clear_popup_height = 0
        clear_live_status_active = False

    writer = FlushTrackingStringIO()
    calls: list[str] = []
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    callback = runner.render_pass_callback(
        stdin_is_terminal=lambda: calls.append("tty") or True,
        layout_active=lambda: calls.append("layout") or True,
        footer_text=lambda: calls.append("footer") or "gpt-test high",
        live_status=TerminalLiveStatusSurface.inactive(),
    )

    assert callback(RenderPass(), RenderContext()) is True
    assert calls == ["tty", "layout", "footer"]
    assert "\x1b[10;1H\u203a hi" in writer.getvalue()
    assert "\x1b[12;1Hgpt-test high" in writer.getvalue()


def test_terminal_bottom_pane_request_runner_builds_resize_reflow_render_factory() -> None:
    # Rust owners: app::resize_reflow owns render-pass timing and asks for a
    # live-status/external-blank-row render factory; terminal_projection owns
    # packaging that factory into bottom-pane render requests.
    class RenderContext:
        draft = "hi"
        popup_lines = ()
        cursor_visible = True

    class RenderPass:
        check_resize = False
        clear_popup_height = 0
        clear_live_status_active = False

    writer = FlushTrackingStringIO()
    calls: list[str] = []
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    render_factory = runner.render_pass_factory_callback(
        stdin_is_terminal=lambda: calls.append("tty") or True,
        layout_active=lambda: calls.append("layout") or True,
        footer_text=lambda: calls.append("footer") or "gpt-test high",
    )

    render = render_factory(TerminalLiveStatusSurface.inactive(), True)

    assert render(RenderPass(), RenderContext()) is True
    assert calls == ["tty", "layout", "footer"]
    assert "\x1b[10;1H\u203a hi" in writer.getvalue()
    assert "\x1b[12;1Hgpt-test high" in writer.getvalue()


def test_terminal_bottom_pane_request_runner_owns_live_viewport_lifecycle() -> None:
    # Rust owner: codex-tui::custom_terminal owns previous/current buffer
    # invalidation around external terminal writes. The bottom-pane adapter may bind
    # callbacks into that lifecycle, while terminal_controller should only call
    # the runner.
    writer = FlushTrackingStringIO()
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
    )
    request = TerminalBottomPaneRenderRequest(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hello",
        footer_text="gpt-test high",
        live_status=TerminalLiveStatusSurface.inactive(),
    )

    assert runner.run(request) is True
    assert "\x1b[10;1H\u203a hello" in writer.getvalue()

    writer.seek(0)
    writer.truncate(0)
    assert runner.run(request) is True
    assert "\x1b[10;1H\u203a hello" not in writer.getvalue()

    calls: list[str] = []
    result = runner.run_external_repaint(lambda: calls.append("repaint") or "done")

    writer.seek(0)
    writer.truncate(0)
    assert runner.run(request) is True
    assert result == "done"
    assert calls == ["repaint"]
    assert "\x1b[10;1H\u203a hello" in writer.getvalue()


def test_terminal_bottom_pane_request_runner_skips_when_terminal_adapter_inactive() -> None:
    # Rust owner: codex-tui::bottom_pane owns whether the pane should draw; the
    # terminal runner only supplies state and callbacks.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    ran = runner.run(
        TerminalBottomPaneClearRequest(
            stdin_is_terminal=False,
            layout_active=True,
            live_status=TerminalLiveStatusSurface.active_status("\u2022 Working"),
        ),
    )

    assert ran is False
    assert calls == []
    assert writer.getvalue() == ""
    assert writer.flush_count == 0


def test_terminal_bottom_pane_clear_request_checks_resize_then_executes_plan() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    ran = runner.run(
        TerminalBottomPaneClearRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=True,
            live_status=TerminalLiveStatusSurface.inactive(),
        ),
    )

    assert ran is True
    assert calls == ["resize", "size"]
    assert writer.flush_count == 1
    assert "\x1b[9;1H\x1b[2K" in writer.getvalue()


def test_terminal_bottom_pane_render_request_checks_resize_then_executes_plan() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    cursor: list[tuple[int, int]] = []

    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )
    ran = runner.run(
        TerminalBottomPaneRenderRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=True,
            draft="hi",
            footer_text="gpt-test high",
            live_status=TerminalLiveStatusSurface.active_status("\u2022 Working"),
        ),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    assert ran is True
    assert calls == ["resize", "size"]
    assert writer.flush_count == 1
    output = writer.getvalue()
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hi" in output
    assert "\x1b[12;1Hgpt-test high" in output
    assert cursor == [(10, len(terminal_composer_line_text("hi")) + 1)]


def test_terminal_bottom_pane_request_runner_flushes_writer() -> None:
    # Rust owner: codex-tui::custom_terminal owns live-viewport clear and flush
    # side effects. The bottom-pane adapter only supplies the projection
    # factory and product-path callbacks.
    writer = FlushTrackingStringIO()
    runner = TerminalBottomPaneRequestRunner(
        writer,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
    )
    ran = runner.run(
        TerminalBottomPaneClearRequest(
            stdin_is_terminal=True,
            layout_active=True,
            check_resize=False,
            live_status=TerminalLiveStatusSurface.inactive(),
        ),
    )

    assert ran is True
    assert writer.flush_count == 1
    output = writer.getvalue()
    assert "\x1b[r" in output
    assert "\x1b[9;1H\x1b[2K" in output
    assert "\x1b[12;1H\x1b[2K" in output

