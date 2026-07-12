from __future__ import annotations

import os

import pycodex.tui.custom_terminal as custom_terminal
from pycodex.tui.custom_terminal import (
    AlternateScreenRenderer,
    BEL,
    ESC,
    LiveViewportClearRequest,
    LiveViewportCursorMove,
    LiveViewportProjection,
    LiveViewportProjectionCycle,
    LiveViewportProjectionCycleRunner,
    LiveViewportProjectionRequestRunner,
    LiveViewportRenderRequest,
    LiveViewportRenderer,
    LiveViewportUpdate,
    TerminalColumnProvider,
    TerminalScrollRegionResetter,
    apply_live_viewport_cursor_move,
    apply_live_viewport_projection,
    apply_live_viewport_update,
    apply_live_viewport_update_with_cursor_move,
    check_live_viewport_resize,
    clear_inline_status_line,
    clear_live_viewport,
    clear_live_viewport_request,
    clear_lines_at,
    clear_scrollback_and_visible_screen_ansi,
    create_live_viewport_renderer,
    create_live_viewport_projection_cycle_runner,
    create_live_viewport_projection_request_runner,
    display_width,
    flush_live_viewport,
    flush_writer,
    prepare_live_viewport_redraw,
    live_viewport_blank_rows,
    live_viewport_buffer_area_for_rows,
    live_viewport_backend_cursor_position_enabled,
    live_viewport_cursor_position,
    live_viewport_minimum_row_widths_for_writes,
    live_viewport_requires_full_redraw,
    render_live_viewport_buffer,
    render_live_viewport_request,
    reset_cursor_style_ansi,
    run_prepared_live_viewport_projection_cycle,
    run_live_viewport_projection_cycle,
    run_live_viewport_update_cycle,
    set_cursor_style_ansi,
    sync_live_viewport_cursor_visibility,
    terminal_clear_scrollback_cursor_position,
    terminal_viewport_clear_should_run,
    terminal_visible_history_rows_after_clear,
    terminal_visible_history_rows_after_insert,
    terminal_visible_history_rows_after_viewport_change,
    truncate_display_width,
    write_inline_status_line,
)
from pycodex.tui.ratatui_bridge import Buffer as BridgeBuffer
from pycodex.tui.ratatui_bridge import Line as BridgeLine
from pycodex.tui.ratatui_bridge import Position as BridgePosition
from pycodex.tui.ratatui_bridge import Rect as BridgeRect


class _StringWriter:
    def __init__(self) -> None:
        self.value = ""

    def write(self, text: str) -> None:
        self.value += text


def test_display_width_ignores_osc_sequences() -> None:
    assert display_width("abc") == 3
    assert display_width(f"{ESC}]8;;https://example.com{BEL}link{ESC}]8;;{BEL}") == 4
    assert display_width(f"中{ESC}]9;payload{BEL}文") == 4

def test_truncate_display_width_respects_wide_cells() -> None:
    # Rust owner: codex-tui::custom_terminal owns terminal cell display width
    # calculations consumed by frame/buffer adapters.
    assert truncate_display_width("abcd", 3) == "abc"
    assert truncate_display_width("\u4f60\u597dabc", 4) == "\u4f60\u597d"
    assert truncate_display_width("\u4f60\u597dabc", 5) == "\u4f60\u597da"


def test_live_viewport_buffer_area_for_rows_covers_primary_or_fallback_rows() -> None:
    # Rust owner: codex-tui::custom_terminal owns the ratatui buffer viewport
    # area consumed by live-pane redraw. Frame adapters should pass rows here
    # instead of deriving buffer geometry locally.
    size = os.terminal_size((80, 24))

    assert live_viewport_buffer_area_for_rows(size, (21, 22, 23, 24)) == BridgeRect.new(0, 20, 80, 4)
    assert live_viewport_buffer_area_for_rows(size, (), fallback_rows=(22, 24)) == BridgeRect.new(0, 21, 80, 3)
    assert live_viewport_buffer_area_for_rows(size, ()) == BridgeRect.new(0, 0, 80, 0)


def test_live_viewport_metadata_helpers_project_terminal_rows_and_cursor() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend redraw metadata
    # consumed by live-pane render requests. Bottom-pane projection adapters
    # should delegate row widths, blank rows, and zero-based cursor conversion.
    class Write:
        def __init__(self, row: int, column: int, text: str) -> None:
            self.row = row
            self.column = column
            self.text = text

    writes = (
        Write(3, 1, "hi"),
        Write(5, 3, "\u4f60"),
        Write(5, 8, "x"),
    )

    assert live_viewport_minimum_row_widths_for_writes(writes) == {
        2: 2,
        4: 8,
    }
    assert live_viewport_blank_rows((3, 4, 5, 6), writes) == (4, 6)
    assert live_viewport_cursor_position(5, 3) == BridgePosition.new(2, 4)


def test_live_viewport_render_request_from_writes_owns_backend_metadata() -> None:
    # Rust owner: codex-tui::custom_terminal owns live-viewport backend
    # metadata projection. Bottom-pane adapters should pass frame writes here
    # instead of composing row widths, blank rows, and cursor positions.
    class Write:
        def __init__(self, row: int, column: int, text: str) -> None:
            self.row = row
            self.column = column
            self.text = text

    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 20, 4))
    writes = (
        Write(3, 1, "hi"),
        Write(5, 4, "\u4f60"),
    )

    request = LiveViewportRenderRequest.from_writes(
        clear_rows=(3, 4, 5, 6),
        buffer=buffer,
        writes=writes,
        cursor_row=5,
        cursor_column=4,
        clear_external_blank_rows=True,
    )

    assert request.clear_rows == (3, 4, 5, 6)
    assert request.buffer is buffer
    assert request.minimum_row_widths == {2: 2, 4: 5}
    assert request.cursor_position == BridgePosition.new(3, 4)
    assert request.external_blank_rows == (4, 6)


def test_terminal_draw_applies_requested_cursor_style() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::set_cursor_style queues
    # the requested crossterm cursor style through the backend.
    writer = _StringWriter()

    set_cursor_style_ansi(writer, "SteadyBar")

    assert writer.value == "\x1b[6 q"


def test_reset_cursor_style_emits_default_user_shape() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::reset_cursor_style
    # restores crossterm's default user-configured cursor shape.
    writer = _StringWriter()

    reset_cursor_style_ansi(writer)

    assert writer.value == "\x1b[0 q"


def test_terminal_visible_history_rows_are_capped_by_viewport_top() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::{set_viewport_area,
    # note_history_rows_inserted}. Python adapters carry viewport geometry
    # separately, so the state transition is owned by custom_terminal helpers
    # rather than a local fake Terminal.
    assert terminal_visible_history_rows_after_viewport_change(10, viewport_top=3) == 3
    assert terminal_visible_history_rows_after_insert(0, 10, viewport_top=3) == 3
    assert terminal_visible_history_rows_after_insert(2, 1, viewport_top=5) == 3


def test_clear_scrollback_and_visible_screen_ansi_resets_state() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::clear_scrollback_and_visible_screen_ansi.
    # The hard clear emits a single ANSI sequence, resets visible-history
    # accounting, and homes the last-known cursor position.
    writer = _StringWriter()

    clear_scrollback_and_visible_screen_ansi(writer)

    assert writer.value == "\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H"
    assert terminal_visible_history_rows_after_clear() == 0
    assert terminal_clear_scrollback_cursor_position() == BridgePosition.new(0, 0)


def test_clear_scrollback_and_visible_screen_ansi_writer_helper_matches_rust_sequence() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::clear_scrollback_and_visible_screen_ansi.
    # The lightweight terminal product path uses the writer helper directly
    # when applying `/clear`.
    writer = _StringWriter()

    clear_scrollback_and_visible_screen_ansi(writer)

    assert writer.value == "\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H"


def test_inline_status_line_helpers_overwrite_current_line_without_scrollback() -> None:
    writer = _StringWriter()

    write_inline_status_line(writer, "\u2022 Working")
    clear_inline_status_line(writer)

    assert writer.value == "\r\x1b[2K\u2022 Working\r\x1b[2K"


def test_clear_lines_at_resets_scroll_region_and_clears_each_row() -> None:
    # Rust owner: codex-tui::custom_terminal owns viewport clear side effects.
    # Python's hybrid live pane delegates row-clearing loops here.
    writer = _StringWriter()

    clear_lines_at(writer, (2, 5))

    assert writer.value == "\x1b[r\x1b[2;1H\x1b[2K\x1b[5;1H\x1b[2K"


def test_flush_writer_calls_terminal_writer_flush_when_available() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend writer flushing.
    class Flushable:
        def __init__(self) -> None:
            self.calls = 0

        def flush(self) -> None:
            self.calls += 1

    writer = Flushable()

    flush_writer(writer)  # type: ignore[arg-type]
    flush_writer(object())  # type: ignore[arg-type]

    assert writer.calls == 1


def test_flush_live_viewport_uses_live_renderer_when_available() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend flush boundaries for
    # the hybrid live viewport. Bottom-pane adapters should call this owner API
    # instead of inspecting writer.flush directly.
    class Flushable(_StringWriter):
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0

        def flush(self) -> None:
            self.flush_count += 1

    direct_writer = Flushable()
    flush_live_viewport(direct_writer)
    assert direct_writer.flush_count == 1

    renderer_writer = Flushable()
    renderer = LiveViewportRenderer(renderer_writer)
    fallback_writer = Flushable()
    flush_live_viewport(fallback_writer, live_viewport=renderer)

    assert renderer_writer.flush_count == 1
    assert fallback_writer.flush_count == 0


def test_live_viewport_renderer_owns_cursor_visibility_primitives() -> None:
    # Rust owner: codex-tui::custom_terminal owns cursor hide/show backend
    # side effects. Terminal controllers should express cursor policy through
    # LiveViewportRenderer instead of importing raw ANSI primitives.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)

    renderer.hide_cursor()
    renderer.show_cursor()

    assert writer.value == "\x1b[?25l\x1b[?25h"


def test_create_live_viewport_renderer_keeps_renderer_state_construction_in_owner() -> None:
    # Rust owner: codex-tui::custom_terminal owns live viewport renderer state
    # construction; terminal controllers should request the owner-managed
    # renderer instead of instantiating backend state directly.
    writer = _StringWriter()

    renderer = create_live_viewport_renderer(writer)

    assert isinstance(renderer, LiveViewportRenderer)
    renderer.hide_cursor()
    assert writer.value == "\x1b[?25l"


def test_live_viewport_renderer_syncs_cursor_visibility_state() -> None:
    # Rust owner: codex-tui::custom_terminal owns cursor hide/show lifecycle
    # state. Terminal controllers should send desired frame policy and let the
    # live viewport suppress duplicate backend cursor writes.
    class Flushable(_StringWriter):
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0

        def flush(self) -> None:
            self.flush_count += 1

    writer = Flushable()
    renderer = LiveViewportRenderer(writer)

    assert renderer.sync_cursor_visibility(False) is True
    assert renderer.sync_cursor_visibility(False) is False
    assert writer.value == "\x1b[?25l"

    assert renderer.sync_cursor_visibility(True, active=False) is False
    assert writer.value == "\x1b[?25l"

    assert renderer.restore_cursor() is True
    assert writer.value == "\x1b[?25l\x1b[?25h"
    assert writer.flush_count == 1

    assert renderer.restore_cursor() is False
    assert writer.flush_count == 1


def test_sync_live_viewport_cursor_visibility_uses_owner_boundary() -> None:
    # Rust owner: codex-tui::custom_terminal owns terminal cursor visibility
    # side effects. Terminal controllers should provide desired policy, not
    # call renderer hide/show synchronization directly.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)

    assert sync_live_viewport_cursor_visibility(None, visible=False) is False
    assert sync_live_viewport_cursor_visibility(renderer, visible=False, active=False) is False
    assert writer.value == ""

    assert sync_live_viewport_cursor_visibility(renderer, visible=False) is True
    assert sync_live_viewport_cursor_visibility(renderer, visible=False) is False

    assert writer.value == "\x1b[?25l"


def test_terminal_size_uses_product_path_default(monkeypatch) -> None:
    # Rust owner: codex-tui::custom_terminal owns terminal sizing before
    # live-viewport draw; Python should expose the same concrete size shape.
    calls: list[tuple[int, int]] = []

    def fake_get_terminal_size(default: tuple[int, int]) -> os.terminal_size:
        calls.append(default)
        return os.terminal_size((101, 31))

    monkeypatch.setattr(custom_terminal.shutil, "get_terminal_size", fake_get_terminal_size)

    assert custom_terminal.terminal_size() == os.terminal_size((101, 31))
    assert calls == [(80, 24)]


def test_terminal_column_provider_binds_size_source_for_runtime_callbacks() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend terminal sizing.
    # terminal_runtime should pass this bound provider into history/resize
    # owners instead of rebuilding terminal_size().columns lambdas locally.
    calls: list[str] = []
    provider = TerminalColumnProvider(lambda: calls.append("size") or os.terminal_size((132, 40)))

    assert provider.columns() == 132
    assert calls == ["size"]


def test_clear_empty_viewport_is_noop() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::clear. Empty
    # viewports must not issue backend clear operations.
    assert terminal_viewport_clear_should_run(width=0, height=5) is False
    assert terminal_viewport_clear_should_run(width=5, height=0) is False
    assert terminal_viewport_clear_should_run(width=5, height=2) is True


def test_prepare_live_viewport_redraw_resets_region_and_clears_only_full_redraw() -> None:
    # Rust owner: codex-tui::custom_terminal owns scroll-region reset and
    # live viewport clearing before frame redraw.
    writer = _StringWriter()

    prepare_live_viewport_redraw(writer, [3, 4], full_redraw=False)
    assert writer.value == "\x1b[r"

    writer.value = ""
    prepare_live_viewport_redraw(writer, [3, 4], full_redraw=True)
    assert writer.value == "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K"


def test_terminal_scroll_region_resetter_binds_writer_callback() -> None:
    # Rust owner: codex-tui::custom_terminal owns scroll-region reset side
    # effects. terminal_runtime should pass a bound custom_terminal callback
    # into resize_reflow instead of rebuilding reset_scroll_region lambdas.
    writer = _StringWriter()
    resetter = TerminalScrollRegionResetter(writer)

    resetter.reset()

    assert writer.value == "\x1b[r"


def test_clear_live_viewport_resets_region_and_clears_rows() -> None:
    # Rust owner: codex-tui::custom_terminal owns live viewport clearing. The
    # bottom-pane surface should pass rows into this owner instead of spelling
    # out reset/clear ordering.
    writer = _StringWriter()

    clear_live_viewport(writer, [3, 4])

    assert writer.value == "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K"


def test_clear_live_viewport_request_wraps_clear_rows() -> None:
    # Rust owner: codex-tui::custom_terminal owns live viewport clearing from
    # a prepared backend request. Surface adapters should not inspect row
    # collections after the bottom-pane owner has projected them.
    writer = _StringWriter()
    request = LiveViewportClearRequest.new([3, 4])

    clear_live_viewport_request(writer, request)

    assert writer.value == "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K"


def test_render_live_viewport_buffer_owns_full_redraw_diff_and_cursor_handoff() -> None:
    # Rust owner: codex-tui::custom_terminal owns the live viewport
    # previous/current buffer compatibility check, full redraw clear, diff
    # redraw, and frame cursor handoff. Terminal adapters only supply the
    # frame-derived rows and cursor position.
    full_writer = _StringWriter()
    current = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    current.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)

    render_live_viewport_buffer(
        full_writer,
        clear_rows=(3, 4),
        buffer=current,
        previous_buffer=None,
        minimum_row_widths={2: 2},
        cursor_position=BridgePosition.new(2, 2),
    )

    assert "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K" in full_writer.value
    assert "\x1b[3;1Hhi" in full_writer.value
    assert full_writer.value.endswith("\x1b[3;3H")

    diff_writer = _StringWriter()
    previous = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    previous.set_line(0, 2, BridgeLine.raw("abcdef"), max_width=8)
    changed = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    changed.set_line(0, 2, BridgeLine.raw("ab"), max_width=8)

    render_live_viewport_buffer(
        diff_writer,
        clear_rows=(3, 4),
        buffer=changed,
        previous_buffer=previous,
        cursor_position=BridgePosition.new(2, 2),
    )

    assert "\x1b[3;1H\x1b[2K" not in diff_writer.value
    assert "\x1b[3;1Ha" not in diff_writer.value
    assert "\x1b[3;3H\x1b[0K" in diff_writer.value
    assert diff_writer.value.endswith("\x1b[3;3H")


def test_live_viewport_requires_full_redraw_for_changed_wide_rows() -> None:
    # Rust owner: codex-tui::custom_terminal owns previous/current frame
    # invalidation. Python's hybrid ANSI backend must conservatively invalidate
    # changed live-pane rows containing wide cells, matching Rust's backend
    # ownership without leaking the policy into composer or surface adapters.
    previous_ascii = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    previous_ascii.set_line(0, 2, BridgeLine.raw("> hello"), max_width=12)
    current_ascii = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    current_ascii.set_line(0, 2, BridgeLine.raw("> help"), max_width=12)

    assert live_viewport_requires_full_redraw(previous_ascii, current_ascii) is False

    previous_wide = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    previous_wide.set_line(0, 2, BridgeLine.raw("\u203a \u4f60"), max_width=12)
    current_wide = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    current_wide.set_line(0, 2, BridgeLine.raw("\u203a \u4f60\u597d"), max_width=12)

    assert live_viewport_requires_full_redraw(previous_wide, current_wide) is True


def test_render_live_viewport_buffer_redraws_changed_wide_rows_for_ime_prompt() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend redraw policy. This
    # protects Windows Terminal/IME prompt rendering where appending a committed
    # wide character must not be emitted as a lone cell diff.
    writer = _StringWriter()
    previous = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    previous.set_line(0, 2, BridgeLine.raw("\u203a \u4f60"), max_width=12)
    current = BridgeBuffer.empty(BridgeRect.new(0, 2, 12, 1))
    current.set_line(0, 2, BridgeLine.raw("\u203a \u4f60\u597d"), max_width=12)

    render_live_viewport_buffer(
        writer,
        clear_rows=(3,),
        buffer=current,
        previous_buffer=previous,
        cursor_position=BridgePosition.new(6, 2),
    )

    assert writer.value.startswith("\x1b[r\x1b[3;1H\x1b[2K")
    assert "\x1b[3;1H\u203a \u4f60" in writer.value
    assert "\x1b[3;5H\u597d" in writer.value
    assert writer.value.endswith("\x1b[3;7H")


def test_render_live_viewport_request_wraps_backend_draw_parameters() -> None:
    # Rust owner: codex-tui::custom_terminal consumes a frame buffer plus
    # viewport metadata during draw. Surface adapters should pass a prepared
    # request instead of unpacking row widths, cursor, and blank-row details.
    writer = _StringWriter()
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    request = LiveViewportRenderRequest.new(
        clear_rows=(3, 4),
        buffer=buffer,
        minimum_row_widths={2: 2},
        cursor_position=BridgePosition.new(2, 2),
        external_blank_rows=(4,),
    )

    render_live_viewport_request(writer, request)

    assert "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K" in writer.value
    assert "\x1b[3;1Hhi" in writer.value
    assert writer.value.endswith("\x1b[3;3H")


def test_apply_live_viewport_update_owns_clear_render_and_flush_policy() -> None:
    # Rust owner: codex-tui::custom_terminal owns applying live viewport clear
    # and render updates, including the backend flush policy. Terminal surface
    # adapters should pass a generic update instead of calling each primitive.
    class Flushable(_StringWriter):
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0

        def flush(self) -> None:
            self.flush_count += 1

    clear_writer = Flushable()
    apply_live_viewport_update(
        clear_writer,
        LiveViewportUpdate.clear(LiveViewportClearRequest.new([3]), flush=True),
    )

    assert clear_writer.value == "\x1b[r\x1b[3;1H\x1b[2K"
    assert clear_writer.flush_count == 1

    render_writer = Flushable()
    renderer = LiveViewportRenderer(render_writer)
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    update = LiveViewportUpdate.render(
        LiveViewportRenderRequest.new(
            clear_rows=(3,),
            buffer=buffer,
            cursor_position=BridgePosition.new(2, 2),
        ),
        flush=True,
    )

    apply_live_viewport_update(Flushable(), update, live_viewport=renderer)

    assert "\x1b[3;1Hhi" in render_writer.value
    assert render_writer.value.endswith("\x1b[3;3H")
    assert render_writer.flush_count == 1


def test_apply_live_viewport_cursor_move_owns_optional_cursor_callback() -> None:
    # Rust owner: codex-tui::custom_terminal owns terminal cursor side effects
    # after drawing a frame. Bottom-pane adapters should pass the projected
    # typed target through this owner instead of reading row/column fields.
    calls: list[tuple[int, int]] = []

    assert apply_live_viewport_cursor_move(
        lambda row, column: calls.append((row, column)),
        LiveViewportCursorMove(row=4, column=7),
    ) is True
    assert calls == [(4, 7)]

    assert apply_live_viewport_cursor_move(
        lambda row, column: calls.append((row, column)),
        LiveViewportCursorMove(row=1, column=1),
        cursor_visible=False,
    ) is False
    assert apply_live_viewport_cursor_move(None, LiveViewportCursorMove(row=1, column=1)) is False
    assert apply_live_viewport_cursor_move(lambda row, column: calls.append((row, column)), None) is False
    assert calls == [(4, 7)]


def test_live_viewport_backend_cursor_position_policy_is_custom_terminal_owned() -> None:
    # Rust owner: codex-tui::custom_terminal consumes frame cursor placement
    # during backend draw. Hybrid adapters should send policy inputs here
    # instead of owning the cursor-position expression themselves.
    assert live_viewport_backend_cursor_position_enabled() is True
    assert live_viewport_backend_cursor_position_enabled(cursor_visible=False) is False
    assert live_viewport_backend_cursor_position_enabled(external_cursor_move=True) is False


def test_apply_live_viewport_update_with_cursor_move_applies_draw_then_cursor() -> None:
    # Rust owner: codex-tui::custom_terminal owns the combined live viewport
    # update and terminal cursor side-effect boundary used by hybrid adapters.
    writer = _StringWriter()
    calls: list[tuple[int, int]] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    update = LiveViewportUpdate.render(
        LiveViewportRenderRequest.new(
            clear_rows=(3,),
            buffer=buffer,
        )
    )

    moved = apply_live_viewport_update_with_cursor_move(
        writer,
        update,
        move_cursor=lambda row, column: calls.append((row, column)),
        cursor_move=LiveViewportCursorMove(row=3, column=4),
    )

    assert moved is True
    assert "\x1b[3;1Hhi" in writer.value
    assert calls == [(3, 4)]


def test_apply_live_viewport_projection_owns_projection_unpacking() -> None:
    # Rust owner: codex-tui::custom_terminal owns applying prepared live
    # viewport projections. Terminal adapters should pass projection objects
    # through this owner instead of unpacking update/cursor fields themselves.
    writer = _StringWriter()
    calls: list[tuple[int, int]] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    projection = LiveViewportProjection(
        LiveViewportUpdate.render(
            LiveViewportRenderRequest.new(
                clear_rows=(3,),
                buffer=buffer,
            )
        ),
        cursor_move=LiveViewportCursorMove(row=3, column=4),
    )

    assert apply_live_viewport_projection(
        writer,
        projection,
        move_cursor=lambda row, column: calls.append((row, column)),
    ) is True
    assert "\x1b[3;1Hhi" in writer.value
    assert calls == [(3, 4)]

    writer.value = ""
    assert apply_live_viewport_projection(writer, None) is False
    assert writer.value == ""


def test_live_viewport_renderer_owns_previous_buffer_state_and_invalidation() -> None:
    # Rust owner: codex-tui::custom_terminal owns current/previous frame buffer
    # state and invalidation after external live-viewport side effects. The
    # bottom-pane controller should hold this renderer, not the raw bridge state.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)

    renderer.render_buffer(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )
    writer.value = ""
    renderer.render_buffer(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )

    assert "\x1b[3;1Hhi" not in writer.value
    assert writer.value.endswith("\x1b[3;3H")
    renderer.run_external_repaint(lambda: None)
    writer.value = ""
    renderer.render_buffer(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )

    assert "\x1b[3;1Hhi" in writer.value

    writer.value = ""
    renderer.clear_rows((3, 4))

    assert writer.value == "\x1b[r\x1b[3;1H\x1b[2K\x1b[4;1H\x1b[2K"


def test_live_viewport_renderer_resize_check_invalidates_previous_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal invalidates previous frame state
    # after resize/viewport changes. Terminal controllers should call this
    # owner API instead of pairing resize callbacks with raw buffer resets.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    request = LiveViewportRenderRequest.new(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )

    renderer.render_request(request)
    writer.value = ""
    renderer.render_request(request)
    assert "\x1b[3;1Hhi" not in writer.value

    renderer.check_resize(lambda: calls.append("resize"))
    writer.value = ""
    renderer.render_request(request)

    assert calls == ["resize"]
    assert "\x1b[3;1Hhi" in writer.value


def test_check_live_viewport_resize_runs_requested_resize_through_owner() -> None:
    # Rust owner: codex-tui::custom_terminal owns resize-triggered frame
    # invalidation. Terminal adapters should delegate requested resize checks
    # here instead of duplicating live-viewport reset branches.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []

    assert check_live_viewport_resize(
        check_resize=False,
        resize=lambda: calls.append("skip"),
        live_viewport=renderer,
    ) is False
    assert calls == []

    assert check_live_viewport_resize(
        check_resize=True,
        resize=lambda: calls.append("renderer"),
        live_viewport=renderer,
    ) is True
    assert calls == ["renderer"]

    assert check_live_viewport_resize(
        check_resize=True,
        resize=lambda: calls.append("fallback"),
        live_viewport=None,
    ) is True
    assert calls == ["renderer", "fallback"]


def test_run_live_viewport_update_cycle_orders_resize_size_and_apply() -> None:
    # Rust owner: codex-tui::custom_terminal owns the live viewport draw
    # lifecycle: cursor sync, resize/invalidating previous frame state, then
    # reading the current terminal size, then applying the prepared live update.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []

    result = run_live_viewport_update_cycle(
        check_resize=True,
        resize=lambda: calls.append("resize"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        live_viewport=renderer,
        cursor_visible=False,
        apply_update=lambda size: calls.append(f"apply:{size.columns}x{size.lines}") or True,
    )

    assert result is True
    assert calls == ["resize", "size", "apply:40x12"]
    assert writer.value == "\x1b[?25l"

    calls.clear()
    run_live_viewport_update_cycle(
        check_resize=False,
        resize=lambda: calls.append("resize"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((80, 24)),
        apply_update=lambda size: calls.append(f"apply:{size.columns}x{size.lines}"),
    )

    assert calls == ["size", "apply:80x24"]


def test_run_live_viewport_projection_cycle_owns_skip_resize_and_projection_application() -> None:
    # Rust owner: codex-tui::custom_terminal owns live viewport draw lifecycle
    # for prepared projections. Hybrid adapters should supply a projection
    # factory, while this boundary owns skip gating, cursor sync, resize/size
    # order, projection application, cursor callback, and flush policy.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []
    cursor_calls: list[tuple[int, int]] = []
    policies: list[object] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)

    skipped = run_live_viewport_projection_cycle(
        writer,
        should_run=False,
        check_resize=True,
        resize=lambda: calls.append("resize"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        live_viewport=renderer,
        cursor_visible=False,
        projection=lambda size, policy: calls.append(f"projection:{size.columns}") or None,
    )

    assert skipped is False
    assert calls == []
    assert writer.value == ""

    ran = run_live_viewport_projection_cycle(
        writer,
        should_run=True,
        check_resize=True,
        resize=lambda: calls.append("resize"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        live_viewport=renderer,
        cursor_visible=True,
        move_cursor=lambda row, column: cursor_calls.append((row, column)),
        projection=lambda size, policy: policies.append(policy)
        or calls.append(f"projection:{size.columns}")
        or LiveViewportProjection(
            LiveViewportUpdate.render(
                LiveViewportRenderRequest.new(
                    clear_rows=(3,),
                    buffer=buffer,
                    cursor_position=None,
                ),
                flush=True,
            ),
            cursor_move=LiveViewportCursorMove(row=3, column=4),
        ),
    )

    assert ran is True
    assert calls == ["resize", "size", "projection:40"]
    assert len(policies) == 1
    assert getattr(policies[0], "cursor_visible") is True
    assert getattr(policies[0], "external_cursor_move") is True
    assert "\x1b[3;1Hhi" in writer.value
    assert cursor_calls == [(3, 4)]


def test_run_prepared_live_viewport_projection_cycle_owns_cycle_unpacking() -> None:
    # Rust owner: codex-tui::custom_terminal owns the live viewport lifecycle.
    # Product adapters may prepare owner-specific projection cycles, but this
    # boundary should consume the typed cycle object and unpack
    # should_run/check_resize/cursor/project fields.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []
    cursor_calls: list[tuple[int, int]] = []
    policies: list[object] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)

    def project(size: os.terminal_size, policy: object) -> LiveViewportProjection:
        policies.append(policy)
        calls.append(f"projection:{size.columns}")
        return LiveViewportProjection(
            LiveViewportUpdate.render(
                LiveViewportRenderRequest.new(
                    clear_rows=(3,),
                    buffer=buffer,
                ),
                flush=True,
            ),
            cursor_move=LiveViewportCursorMove(row=3, column=4),
        )

    ran = run_prepared_live_viewport_projection_cycle(
        writer,
        LiveViewportProjectionCycle(
            project=project,
            should_run=True,
            check_resize=True,
            cursor_visible=True,
        ),
        resize=lambda: calls.append("resize"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        live_viewport=renderer,
        move_cursor=lambda row, column: cursor_calls.append((row, column)),
    )

    assert ran is True
    assert calls == ["resize", "size", "projection:40"]
    assert len(policies) == 1
    assert getattr(policies[0], "cursor_visible") is True
    assert getattr(policies[0], "external_cursor_move") is True
    assert "\x1b[3;1Hhi" in writer.value
    assert cursor_calls == [(3, 4)]


def test_live_viewport_projection_cycle_runner_owns_stateful_cycle_lifecycle() -> None:
    # Rust owner: codex-tui::custom_terminal owns the stateful terminal
    # writer/renderer/resize lifecycle for repeated live-viewport frame draws.
    # Product adapters should hand prepared cycles to this runner instead of
    # storing LiveViewportRenderer state directly.
    writer = _StringWriter()
    calls: list[str] = []
    cursor_calls: list[tuple[int, int]] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    runner = create_live_viewport_projection_cycle_runner(
        writer,  # type: ignore[arg-type]
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )

    def project(size: os.terminal_size, _policy: object) -> LiveViewportProjection:
        calls.append(f"projection:{size.columns}")
        return LiveViewportProjection(
            LiveViewportUpdate.render(
                LiveViewportRenderRequest.new(
                    clear_rows=(3,),
                    buffer=buffer,
                ),
                flush=True,
            ),
            cursor_move=LiveViewportCursorMove(row=3, column=4),
        )

    cycle = LiveViewportProjectionCycle(
        project=project,
        should_run=True,
        check_resize=True,
        cursor_visible=True,
    )

    assert isinstance(runner, LiveViewportProjectionCycleRunner)
    assert runner.run(cycle, move_cursor=lambda row, column: cursor_calls.append((row, column))) is True
    assert "\x1b[3;1Hhi" in writer.value
    assert cursor_calls == [(3, 4)]
    assert calls == ["resize", "size", "projection:40"]

    writer.value = ""
    calls.clear()
    assert runner.run(
        LiveViewportProjectionCycle(
            project=project,
            should_run=True,
            check_resize=False,
            cursor_visible=True,
        )
    ) is True
    assert "\x1b[3;1Hhi" not in writer.value
    assert calls == ["size", "projection:40"]

    result = runner.run_external_repaint(lambda: calls.append("repaint") or "done")
    writer.value = ""
    assert runner.run(
        LiveViewportProjectionCycle(
            project=project,
            should_run=True,
            check_resize=False,
            cursor_visible=True,
        )
    ) is True
    assert result == "done"
    assert "\x1b[3;1Hhi" in writer.value


def test_live_viewport_projection_request_runner_owns_request_lifecycle() -> None:
    # Rust owner: codex-tui::custom_terminal owns live-viewport lifecycle
    # execution. Product adapters may define request objects and projection
    # functions, but custom_terminal should own request run/restore/external
    # repaint plumbing once the projection callback is supplied.
    writer = _StringWriter()
    calls: list[str] = []
    cursor_calls: list[tuple[int, int]] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 10, 1))
    buffer.set_line(0, 2, BridgeLine.raw("request"), max_width=10)

    def project(request: str) -> LiveViewportProjectionCycle:
        calls.append(f"project:{request}")

        def projection(size: os.terminal_size, _policy: object) -> LiveViewportProjection:
            calls.append(f"projection:{size.columns}")
            return LiveViewportProjection(
                LiveViewportUpdate.render(
                    LiveViewportRenderRequest.new(
                        clear_rows=(3,),
                        buffer=buffer,
                    ),
                    flush=True,
                ),
                cursor_move=LiveViewportCursorMove(row=3, column=8),
            )

        return LiveViewportProjectionCycle(
            project=projection,
            should_run=True,
            check_resize=request != "stable",
            cursor_visible=True,
        )

    runner = create_live_viewport_projection_request_runner(
        writer,  # type: ignore[arg-type]
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
        project=project,
    )

    assert isinstance(runner, LiveViewportProjectionRequestRunner)
    assert runner.run("bottom-pane", move_cursor=lambda row, column: cursor_calls.append((row, column))) is True
    assert "\x1b[3;1Hrequest" in writer.value
    assert cursor_calls == [(3, 8)]
    assert calls == ["project:bottom-pane", "resize", "size", "projection:40"]

    writer.value = ""
    calls.clear()
    assert runner.run("stable") is True
    assert "\x1b[3;1Hrequest" not in writer.value
    assert calls == ["project:stable", "size", "projection:40"]

    result = runner.run_external_repaint(lambda: calls.append("repaint") or "done")
    writer.value = ""
    assert runner.run("stable") is True
    assert result == "done"
    assert "\x1b[3;1Hrequest" in writer.value


def test_live_viewport_renderer_external_repaint_invalidates_previous_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal owns invalidation around external
    # terminal repaint callbacks. Bottom-pane controllers should delegate this
    # lifecycle step instead of bracketing callbacks with raw buffer resets.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    calls: list[str] = []
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    request = LiveViewportRenderRequest.new(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )

    renderer.render_request(request)
    writer.value = ""
    renderer.render_request(request)
    assert "\x1b[3;1Hhi" not in writer.value

    result = renderer.run_external_repaint(lambda: calls.append("repaint") or "done")
    writer.value = ""
    renderer.render_request(request)

    assert result == "done"
    assert calls == ["repaint"]
    assert "\x1b[3;1Hhi" in writer.value


def test_live_viewport_renderer_clear_request_invalidates_previous_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal invalidates previous frame state
    # after live viewport clearing, including request-based clears.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)

    renderer.render_request(
        LiveViewportRenderRequest.new(
            clear_rows=(3, 4),
            buffer=buffer,
            cursor_position=BridgePosition.new(2, 2),
        )
    )
    writer.value = ""
    renderer.clear_request(LiveViewportClearRequest.new([3, 4]))
    writer.value = ""
    renderer.render_request(
        LiveViewportRenderRequest.new(
            clear_rows=(3, 4),
            buffer=buffer,
            cursor_position=BridgePosition.new(2, 2),
        )
    )

    assert "\x1b[3;1Hhi" in writer.value


def test_live_viewport_renderer_can_render_prepared_request() -> None:
    # Rust owner: codex-tui::custom_terminal owns current/previous buffer
    # state while consuming prepared live-viewport requests.
    writer = _StringWriter()
    renderer = LiveViewportRenderer(writer)
    buffer = BridgeBuffer.empty(BridgeRect.new(0, 2, 8, 1))
    buffer.set_line(0, 2, BridgeLine.raw("hi"), max_width=8)
    request = LiveViewportRenderRequest.new(
        clear_rows=(3, 4),
        buffer=buffer,
        cursor_position=BridgePosition.new(2, 2),
    )

    renderer.render_request(request)
    writer.value = ""
    renderer.render_request(request)

    assert "\x1b[3;1Hhi" not in writer.value
    assert writer.value.endswith("\x1b[3;3H")


def test_alternate_screen_renderer_fully_redraws_changed_wide_rows(monkeypatch) -> None:
    """Rust custom_terminal invalidates diff rows containing changed wide cells."""

    writer = _StringWriter()
    renderer = AlternateScreenRenderer(writer)
    previous_arguments: list[object] = []
    original_draw = custom_terminal._bridge_draw_buffer_to_ansi

    def capture_draw(writer, buffer, *, previous=None, **kwargs):
        previous_arguments.append(previous)
        return original_draw(writer, buffer, previous=previous, **kwargs)

    monkeypatch.setattr(custom_terminal, "_bridge_draw_buffer_to_ansi", capture_draw)
    size = os.terminal_size((20, 4))
    renderer.enter()
    renderer.render_lines(["中文第一行", "中文第二行"], size)
    renderer.render_lines(["中文第二行", "中文第三行"], size)

    assert previous_arguments == [None, None]
    assert writer.value.count("\x1b[2J") >= 2
