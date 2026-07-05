# Parity source: codex-rs/tui/src/insert_history.rs

from io import StringIO

import pytest

from pycodex.tui.insert_history import (
    HistoryLineWrapPolicy,
    Hyperlink,
    HyperlinkLine,
    InsertHistoryMode,
    Line,
    Modifier,
    ModifierDiff,
    ResetScrollRegion,
    SetScrollRegion,
    Span,
    Style,
    TerminalHistoryState,
    TerminalHistoryWriter,
    TerminalModel,
    execute_winapi,
    finish_history_stream_output_and_flush,
    finish_history_stream_projection_and_flush,
    finish_plain_history_output_and_flush,
    finish_terminal_history_output,
    insert_history_lines,
    insert_history_lines_output_and_flush,
    insert_history_lines_with_mode_and_wrap_policy,
    insert_plain_history_lines_and_flush,
    insert_terminal_history_lines_and_flush,
    leading_whitespace_prefix,
    open_history_stream_output_and_flush,
    open_history_stream_plan_output_and_flush,
    open_plain_history_stream_and_flush,
    open_terminal_history_stream_and_flush,
    prepare_terminal_history_insert,
    run_terminal_history_cell_output_and_flush,
    run_terminal_history_lines_output_and_flush,
    run_terminal_history_output_and_flush,
    run_terminal_history_stream_open_and_flush,
    terminal_history_cell_insert_plan,
    terminal_history_cell_insert_lines,
    terminal_history_cell_lines,
    terminal_history_inline_write_plan,
    terminal_history_lines_insert_plan,
    terminal_history_stream_finish_plan,
    terminal_history_stream_open_plan,
    terminal_history_wrap_width,
    terminal_history_write_state_after_insert_lines,
    terminal_history_write_state_after_write,
    wrap_history_line,
    write_history_cell_output_and_flush,
    write_history_inline_output_and_flush,
    write_history_line,
    write_spans,
    write_terminal_history_stream_delta_and_flush,
)


class FlushTrackingStringIO(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def test_set_and_reset_scroll_region_write_ansi_like_rust_commands():
    assert SetScrollRegion(range(1, 10)).write_ansi() == "\x1b[1;10r"
    assert ResetScrollRegion().write_ansi() == "\x1b[r"


def test_prepare_terminal_history_insert_sets_region_and_cursor():
    # Rust owner: codex-tui::insert_history prepares the scroll region and
    # cursor before finalized or streaming history rows are written.
    writer = StringIO()

    prepare_terminal_history_insert(
        writer,
        history_bottom_row=18,
        scroll_region_bottom=20,
    )

    assert writer.getvalue() == "\x1b[1;20r\x1b[18;1H"


def test_finish_terminal_history_output_resets_region_and_repaints_bottom_pane():
    # Rust owner: codex-tui::insert_history returns terminal state to the full
    # viewport after streaming history output, then lets bottom_pane repaint.
    writer = StringIO()

    finish_terminal_history_output(
        writer,
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    assert writer.getvalue() == "\x1b[r<bottom-pane>"


def test_finish_history_stream_output_and_flush_selects_terminal_or_plain_surface() -> None:
    # Rust owner: codex-tui::insert_history owns terminal/plain streaming
    # history output finalization; the runner supplies only the active surface.
    terminal_writer = FlushTrackingStringIO()
    plain_writer = FlushTrackingStringIO()

    finish_history_stream_output_and_flush(
        terminal_writer,
        terminal_active=True,
        render_bottom_pane=lambda: terminal_writer.write("<bottom-pane>"),
    )
    finish_history_stream_output_and_flush(
        plain_writer,
        terminal_active=False,
        render_bottom_pane=lambda: plain_writer.write("<unused>"),
    )

    assert terminal_writer.getvalue() == "\x1b[r<bottom-pane>"
    assert terminal_writer.flush_count == 0
    assert plain_writer.getvalue() == "\n"
    assert plain_writer.flush_count == 1


def test_finish_history_stream_projection_and_flush_records_projection() -> None:
    # Rust owner: codex-tui::insert_history owns the streaming history output
    # finalizer and retained transcript projection update. The terminal runner
    # should not open-code that state transition around assistant stream finish.
    terminal_writer = FlushTrackingStringIO()
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=False,
        projection_cells=("\u203a hello",),
    )

    next_state = finish_history_stream_projection_and_flush(
        terminal_writer,
        state,
        "\u2022 answer",
        terminal_active=True,
        render_bottom_pane=lambda: terminal_writer.write("<bottom-pane>"),
    )

    assert terminal_writer.getvalue() == "\x1b[r<bottom-pane>"
    assert terminal_writer.flush_count == 0
    assert next_state.projection_cells == ("\u203a hello", "\u2022 answer")
    assert next_state.history_has_content is True
    assert next_state.history_ended_with_blank is False


def test_finish_history_stream_projection_and_flush_plain_output_without_projection() -> None:
    # Rust owner: codex-tui::insert_history keeps non-TTY stream finalization in
    # the same boundary while leaving retained history unchanged without a
    # finalized assistant projection.
    plain_writer = FlushTrackingStringIO()
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=False,
        projection_cells=("\u203a hello",),
    )

    next_state = finish_history_stream_projection_and_flush(
        plain_writer,
        state,
        None,
        terminal_active=False,
        render_bottom_pane=lambda: plain_writer.write("<unused>"),
    )

    assert plain_writer.getvalue() == "\n"
    assert plain_writer.flush_count == 1
    assert next_state == state


def test_execute_winapi_panics_semantically_like_rust():
    with pytest.raises(RuntimeError, match="use ANSI instead"):
        execute_winapi()


def test_modifier_diff_writes_bold_then_regular_spans():
    writer = StringIO()
    spans = [Span("A", Style(add_modifier=Modifier.BOLD)), Span("B")]

    write_spans(writer, spans)
    output = writer.getvalue()

    assert "\x1b[1m" in output
    assert "\x1b[22m" in output
    assert output.endswith("\x1b[39m\x1b[49m\x1b[0m")
    assert "A" in output and "B" in output


def test_modifier_diff_reapplies_dim_when_bold_is_removed_to_dim():
    diff = ModifierDiff(Modifier.BOLD, Modifier.DIM).ansi()

    assert "\x1b[22m" in diff
    assert "\x1b[2m" in diff


def test_leading_whitespace_prefix_preserves_span_styles_until_first_non_space():
    line = Line(
        (
            Span("  ", Style(fg="green")),
            Span("\tfoo", Style(fg="blue")),
            Span("bar", Style(fg="red")),
        ),
        Style(bg="black"),
    )

    prefix = leading_whitespace_prefix(line)

    assert prefix.text == "  \t"
    assert [span.style.fg for span in prefix.spans] == ["green", "blue"]
    assert prefix.style.bg == "black"


def test_terminal_wrap_policy_does_not_pre_wrap_long_paragraph():
    line = HyperlinkLine(Line.from_text("alpha beta gamma delta epsilon zeta"))

    wrapped = wrap_history_line(line, 20, HistoryLineWrapPolicy.TERMINAL)

    assert [item.text for item in wrapped] == ["alpha beta gamma delta epsilon zeta"]


def test_pre_wrap_preserves_prefix_on_non_url_wrapped_rows():
    line = HyperlinkLine(Line.from_text("      dog while this deliberately long string tests wrapping"))

    wrapped = wrap_history_line(line, 32, HistoryLineWrapPolicy.PRE_WRAP)

    assert len(wrapped) >= 2
    assert wrapped[1].text.startswith("      ")


def test_url_only_lines_are_kept_intact_for_terminal_link_detection():
    text = "http://a-long-url.com/this/that/blablablab/new.aspx/many_people_like_how"
    line = HyperlinkLine(Line.from_text("  |" + text))

    wrapped = wrap_history_line(line, 24, HistoryLineWrapPolicy.PRE_WRAP)

    assert [item.text for item in wrapped] == ["  |" + text]


def test_mixed_url_line_wraps_suffix_words_and_keeps_prefix():
    line = HyperlinkLine(Line.from_text("  see https://example.test/path/abcdef12345 tail words"))

    wrapped = wrap_history_line(line, 24, HistoryLineWrapPolicy.PRE_WRAP)

    assert wrapped[0].text.startswith("  see")
    assert any("tail words" in item.text for item in wrapped)
    assert all(item.text.startswith("  ") for item in wrapped[1:])


def test_write_history_line_decorates_semantic_web_link_without_changing_visible_text():
    destination = "https://example.com/long/path"
    line = HyperlinkLine(
        Line.from_text(destination),
        hyperlinks=(Hyperlink(0, len(destination), destination),),
    )
    writer = StringIO()

    write_history_line(writer, line, 80)
    output = writer.getvalue()

    assert "\x1b]8;;https://example.com/long/path\x07" in output
    assert destination in output


def test_write_history_line_clears_continuation_rows_for_wide_lines():
    writer = StringIO()

    write_history_line(writer, Line.from_text("x" * 45), 20)
    output = writer.getvalue()

    assert output.count("\x1b[K") >= 3
    assert "\x1b[s" in output
    assert "\x1b[u" in output
    assert "<clear-eol>" not in output


def test_insert_history_lines_records_wrapped_rows_and_scroll_region():
    terminal = TerminalModel(width=20, height=8, viewport_y=7, viewport_height=1)

    wrapped = insert_history_lines(terminal, ["alpha beta gamma delta epsilon zeta"])

    assert len(wrapped) >= 2
    assert terminal.history_rows_inserted >= 2
    assert "\x1b[1;7r" in terminal.output.getvalue()
    assert terminal.output.getvalue().endswith("\x1b[r")


def test_zellij_raw_mode_uses_raw_marker_and_terminal_policy():
    terminal = TerminalModel(width=20, height=8, viewport_y=6, viewport_height=2)

    wrapped = insert_history_lines_with_mode_and_wrap_policy(
        terminal,
        ["raw-start-aaaaaaaaaaaaaaaaaaaaaaaa-tail-must-remain"],
        InsertHistoryMode.ZELLIJ_RAW,
        HistoryLineWrapPolicy.TERMINAL,
    )

    assert len(wrapped) == 1
    output = terminal.output.getvalue()
    assert "\x1b[7;1H\x1b[J" in output
    assert "<clear-after-viewport><move-viewport-top>" not in output
    assert terminal.history_rows_inserted >= 1


def test_terminal_history_cell_lines_preserve_prompt_prefix_on_continuation_rows():
    rows = terminal_history_cell_lines(
        "\u203a alpha beta gamma delta epsilon",
        14,
    )

    assert rows[0].startswith("\u203a ")
    assert len(rows) >= 2
    assert rows[1].startswith("  ")
    assert "\u203a" not in rows[1]


def test_terminal_history_cell_lines_count_wide_characters_in_wrap_budget():
    rows = terminal_history_cell_lines(
        "\u2022 \u4f60\u597dabc def",
        8,
    )

    assert rows[0] == "\u2022 \u4f60\u597dab"
    assert rows[1] == "  c def"


def test_terminal_history_wrap_width_matches_product_terminal_margin():
    assert terminal_history_wrap_width(80) == 79
    assert terminal_history_wrap_width(4) == 10


def test_terminal_history_cell_insert_lines_adds_gap_between_cells() -> None:
    rows = terminal_history_cell_insert_lines(
        "\u2022 alpha beta gamma",
        12,
        history_has_content=True,
        history_ended_with_blank=False,
    )

    assert rows[0] == ""
    assert rows[1].startswith("\u2022 ")
    assert len(rows) >= 2


def test_terminal_history_cell_insert_lines_skips_gap_after_blank_history() -> None:
    rows = terminal_history_cell_insert_lines(
        "next",
        12,
        history_has_content=True,
        history_ended_with_blank=True,
    )

    assert rows == ["next"]


def test_terminal_history_cell_insert_plan_records_projection_and_materializes_rows() -> None:
    # Rust owner: codex-tui::insert_history owns finalized transcript insertion.
    # The terminal runner should consume a prepared plan instead of deriving
    # separator rows and retained projection cells itself.
    plan = terminal_history_cell_insert_plan(
        TerminalHistoryState(history_has_content=True, history_ended_with_blank=False),
        "\u203a alpha beta gamma",
        12,
    )

    assert plan.lines[0] == ""
    assert plan.lines[1].startswith("\u203a ")
    assert plan.state.projection_cells == ("\u203a alpha beta gamma",)
    assert plan.state.history_has_content is True
    assert plan.state.history_ended_with_blank is False


def test_terminal_history_cell_insert_plan_leaves_write_markers_for_actual_insert() -> None:
    plan = terminal_history_cell_insert_plan(
        TerminalHistoryState.empty(),
        "hello",
        20,
    )

    assert plan.lines == ("hello",)
    assert plan.state.projection_cells == ("hello",)
    assert plan.state.history_has_content is False
    assert plan.state.after_insert_lines(plan.lines).history_has_content is True


def test_terminal_history_write_state_ignores_initial_blank_line() -> None:
    # Rust owner: codex-tui::insert_history owns finalized history insertion
    # semantics; a leading separator row should not make the transcript look
    # like it already has a non-empty history cell.
    assert terminal_history_write_state_after_write(
        history_has_content=False,
        history_ended_with_blank=False,
        text="",
        end="\n",
    ) == (False, False)


def test_terminal_history_write_state_tracks_blank_separator_after_content() -> None:
    state = terminal_history_write_state_after_insert_lines(
        history_has_content=False,
        history_ended_with_blank=False,
        lines=["\u203a hello", ""],
    )

    assert state == (True, True)


def test_terminal_history_write_state_non_empty_line_clears_blank_marker() -> None:
    state = terminal_history_write_state_after_insert_lines(
        history_has_content=True,
        history_ended_with_blank=True,
        lines=["\u2022 answer"],
    )

    assert state == (True, False)


def test_terminal_history_lines_insert_plan_advances_write_markers() -> None:
    # Rust owner: codex-tui::insert_history owns emitted-row history state.
    # The terminal runner should perform writer side effects, not decide how
    # inserted rows advance content/blank markers.
    plan = terminal_history_lines_insert_plan(
        TerminalHistoryState(history_has_content=True, history_ended_with_blank=True),
        ["answer"],
    )

    assert plan.lines == ("answer",)
    assert plan.state.history_has_content is True
    assert plan.state.history_ended_with_blank is False


def test_terminal_history_lines_insert_plan_empty_rows_leave_state_unchanged() -> None:
    state = TerminalHistoryState(history_has_content=True, history_ended_with_blank=True)

    plan = terminal_history_lines_insert_plan(state, [])

    assert plan.lines == ()
    assert plan.state == state


def test_terminal_history_inline_write_plan_advances_write_markers() -> None:
    # Rust owner: codex-tui::insert_history owns write-marker advancement for
    # history output, while the terminal runner only performs writer effects.
    plan = terminal_history_inline_write_plan(
        TerminalHistoryState.empty(),
        "partial",
        "",
    )

    assert plan.text == "partial"
    assert plan.end == ""
    assert plan.state.history_has_content is True
    assert plan.state.history_ended_with_blank is False


def test_write_history_inline_output_and_flush_writes_and_advances_state() -> None:
    writer = FlushTrackingStringIO()

    state = write_history_inline_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "partial",
        "",
    )

    assert writer.getvalue() == "partial"
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is False


def test_terminal_history_state_tracks_projection_and_write_markers() -> None:
    # Rust owner: codex-tui::insert_history owns transcript insertion state.
    # The terminal runner stores this object, but projection and blank-marker
    # advancement should remain an insert-history responsibility.
    state = TerminalHistoryState.empty()

    state = state.with_projection_cell("\u203a hello")
    assert state.projection_cells == ("\u203a hello",)
    assert state.history_has_content is False
    assert state.history_ended_with_blank is False

    state = state.after_insert_lines(["\u203a hello", ""])
    assert state.history_has_content is True
    assert state.history_ended_with_blank is True
    assert state.projection_cells == ("\u203a hello",)

    state = state.after_stream_open()
    assert state.history_has_content is True
    assert state.history_ended_with_blank is False
    assert state.projection_cells == ("\u203a hello",)


def test_terminal_history_stream_open_plan_inserts_separator_before_active_stream() -> None:
    # Rust owner: codex-tui::insert_history owns the boundary between
    # finalized transcript insertion and streaming assistant history output.
    plan = terminal_history_stream_open_plan(
        TerminalHistoryState(
            history_has_content=True,
            history_ended_with_blank=False,
            projection_cells=("\u203a hello",),
        )
    )

    assert plan.gap_lines == ("",)
    assert plan.state.history_has_content is True
    assert plan.state.history_ended_with_blank is False
    assert plan.state.projection_cells == ("\u203a hello",)


def test_terminal_history_stream_open_plan_skips_separator_after_blank_or_empty_history() -> None:
    after_blank = terminal_history_stream_open_plan(
        TerminalHistoryState(history_has_content=True, history_ended_with_blank=True)
    )
    empty = terminal_history_stream_open_plan(TerminalHistoryState.empty())

    assert after_blank.gap_lines == ()
    assert after_blank.state.history_has_content is True
    assert after_blank.state.history_ended_with_blank is False
    assert empty.gap_lines == ()
    assert empty.state.history_has_content is True
    assert empty.state.history_ended_with_blank is False


def test_terminal_history_stream_finish_plan_records_optional_projection() -> None:
    # Rust owner: codex-tui::insert_history owns retained transcript projection
    # state; assistant stream finalization should not open-code projection cell
    # updates in the terminal runner.
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=False,
        projection_cells=("\u203a hello",),
    )

    with_projection = terminal_history_stream_finish_plan(state, "\u2022 answer")
    without_projection = terminal_history_stream_finish_plan(state, None)

    assert with_projection.state.projection_cells == ("\u203a hello", "\u2022 answer")
    assert with_projection.state.history_has_content is True
    assert with_projection.state.history_ended_with_blank is False
    assert without_projection.state == state


def test_insert_plain_history_lines_and_flush_writes_non_tty_lines() -> None:
    writer = FlushTrackingStringIO()

    insert_plain_history_lines_and_flush(writer, ["alpha", "beta"])

    assert writer.getvalue() == "alpha\nbeta\n"
    assert writer.flush_count == 1


def test_insert_terminal_history_lines_and_flush_flushes_writer() -> None:
    writer = FlushTrackingStringIO()

    insert_terminal_history_lines_and_flush(
        writer,
        ["alpha", "beta"],
        history_bottom_row=18,
        scroll_region_bottom=20,
    )

    output = writer.getvalue()
    assert output.startswith("\x1b[1;20r\x1b[18;1H\r\nalpha\r\nbeta\x1b[r")
    assert writer.flush_count == 1


def test_insert_history_lines_output_and_flush_selects_terminal_surface_and_state() -> None:
    writer = FlushTrackingStringIO()

    state = insert_history_lines_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        ["alpha", ""],
        terminal_active=True,
        history_bottom_row=18,
        scroll_region_bottom=20,
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    assert writer.getvalue().startswith("\x1b[1;20r\x1b[18;1H\r\nalpha\r\n\x1b[r<bottom-pane>")
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is True


def test_insert_history_lines_output_and_flush_selects_plain_surface_and_state() -> None:
    writer = FlushTrackingStringIO()

    state = insert_history_lines_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        ["alpha", ""],
        terminal_active=False,
    )

    assert writer.getvalue() == "alpha\n\n"
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is True


def test_run_terminal_history_lines_output_and_flush_sequences_terminal_callbacks() -> None:
    # Rust owner: codex-tui::insert_history owns finalized row insertion,
    # terminal surface preparation, bottom-pane repaint, and emitted-row state.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    state = run_terminal_history_lines_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        ["alpha", ""],
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert writer.getvalue().startswith("\x1b[1;18r\x1b[18;1H\r\nalpha\r\n\x1b[r")
    assert calls == ["resize", "bottom", "clear", "render"]
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is True


def test_run_terminal_history_lines_output_and_flush_skips_empty_rows() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    state = TerminalHistoryState(history_has_content=True, history_ended_with_blank=True)

    next_state = run_terminal_history_lines_output_and_flush(
        writer,
        state,
        [],
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
    )

    assert writer.getvalue() == ""
    assert calls == []
    assert writer.flush_count == 0
    assert next_state == state


def test_run_terminal_history_output_and_flush_routes_newline_to_row_insertion() -> None:
    # Rust owner: codex-tui::insert_history owns whether output is finalized
    # row insertion or inline writing. The terminal runner supplies callbacks.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    state = run_terminal_history_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "alpha",
        "\n",
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert writer.getvalue().startswith("\x1b[1;18r\x1b[18;1H\r\nalpha\x1b[r")
    assert calls == ["resize", "bottom", "clear", "render"]
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is False


def test_run_terminal_history_output_and_flush_routes_non_newline_to_inline_write() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    state = run_terminal_history_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "partial",
        "",
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert writer.getvalue() == "partial"
    assert calls == []
    assert writer.flush_count == 1
    assert state.history_has_content is True
    assert state.history_ended_with_blank is False


def test_write_history_cell_output_and_flush_records_projection_and_rows() -> None:
    # Rust owner: codex-tui::insert_history owns finalized cell projection,
    # row materialization, surface output, and emitted-row state advancement.
    writer = FlushTrackingStringIO()

    state = write_history_cell_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "\u203a alpha beta gamma",
        12,
        terminal_active=False,
    )

    assert writer.getvalue() == "\u203a alpha\n  beta gamma\n"
    assert writer.flush_count == 1
    assert state.projection_cells == ("\u203a alpha beta gamma",)
    assert state.history_has_content is True
    assert state.history_ended_with_blank is False


def test_run_terminal_history_cell_output_and_flush_sequences_terminal_callbacks() -> None:
    # Rust owner: codex-tui::insert_history owns finalized history-cell
    # materialization, terminal surface preparation, insertion, and flush order.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    state = run_terminal_history_cell_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "alpha beta gamma",
        "\n",
        10,
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    output = writer.getvalue()
    assert output.startswith("\x1b[1;18r\x1b[18;1H\r\nalpha\r\nbeta gamma\x1b[r")
    assert calls == ["resize", "bottom", "clear", "render"]
    assert writer.flush_count == 1
    assert state.projection_cells == ("alpha beta gamma",)
    assert state.history_has_content is True


def test_run_terminal_history_cell_output_and_flush_selects_inline_output() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    state = run_terminal_history_cell_output_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "partial",
        "",
        10,
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
    )

    assert writer.getvalue() == "partial"
    assert calls == []
    assert writer.flush_count == 1
    assert state.history_has_content is True


def test_open_terminal_history_stream_and_flush_prepares_region_prefix_and_flushes() -> None:
    writer = FlushTrackingStringIO()

    open_terminal_history_stream_and_flush(
        writer,
        "\u2022 ",
        history_bottom_row=18,
        scroll_region_bottom=20,
    )

    assert writer.getvalue() == "\x1b[1;20r\x1b[18;1H\r\n\u2022 "
    assert writer.flush_count == 1


def test_open_plain_history_stream_and_flush_writes_prefix_and_flushes() -> None:
    writer = FlushTrackingStringIO()

    open_plain_history_stream_and_flush(writer, "\u2022 ")

    assert writer.getvalue() == "\u2022 "
    assert writer.flush_count == 1


def test_open_history_stream_output_and_flush_writes_terminal_gap_then_prefix() -> None:
    # Rust owner: codex-tui::insert_history owns the terminal scrollback
    # insertion surface for separator rows and streaming history prefixes.
    writer = FlushTrackingStringIO()

    open_history_stream_output_and_flush(
        writer,
        "\u2022 ",
        gap_lines=[""],
        terminal_active=True,
        history_bottom_row=18,
        scroll_region_bottom=20,
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    assert writer.getvalue() == (
        "\x1b[1;20r\x1b[18;1H\r\n\x1b[r<bottom-pane>"
        "\x1b[1;20r\x1b[18;1H\r\n\u2022 "
    )
    assert writer.flush_count == 2


def test_open_history_stream_output_and_flush_writes_plain_gap_then_prefix() -> None:
    writer = FlushTrackingStringIO()

    open_history_stream_output_and_flush(
        writer,
        "\u2022 ",
        gap_lines=[""],
        terminal_active=False,
        render_bottom_pane=lambda: writer.write("<unused>"),
    )

    assert writer.getvalue() == "\n\u2022 "
    assert writer.flush_count == 2


def test_open_history_stream_plan_output_and_flush_terminal_gap_advances_state() -> None:
    # Rust owner: codex-tui::insert_history owns stream opening from finalized
    # history state: separator row emission, prefix output, bottom-pane repaint,
    # and history write-marker advancement belong together.
    writer = FlushTrackingStringIO()
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=False,
        projection_cells=("\u203a hello",),
    )

    next_state = open_history_stream_plan_output_and_flush(
        writer,
        state,
        "\u2022 ",
        terminal_active=True,
        history_bottom_row=18,
        scroll_region_bottom=20,
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    assert writer.getvalue() == (
        "\x1b[1;20r\x1b[18;1H\r\n\x1b[r<bottom-pane>"
        "\x1b[1;20r\x1b[18;1H\r\n\u2022 "
    )
    assert writer.flush_count == 2
    assert next_state.history_has_content is True
    assert next_state.history_ended_with_blank is False
    assert next_state.projection_cells == ("\u203a hello",)


def test_open_history_stream_plan_output_and_flush_plain_without_gap() -> None:
    writer = FlushTrackingStringIO()
    state = TerminalHistoryState.empty()

    next_state = open_history_stream_plan_output_and_flush(
        writer,
        state,
        "\u2022 ",
        terminal_active=False,
        render_bottom_pane=lambda: writer.write("<unused>"),
    )

    assert writer.getvalue() == "\u2022 "
    assert writer.flush_count == 1
    assert next_state.history_has_content is True
    assert next_state.history_ended_with_blank is False


def test_run_terminal_history_stream_open_and_flush_sequences_terminal_callbacks() -> None:
    # Rust owner: codex-tui::insert_history owns assistant stream opening from
    # finalized history state, including resize-time terminal surface lookup.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    state = TerminalHistoryState(history_has_content=True, history_ended_with_blank=False)

    next_state = run_terminal_history_stream_open_and_flush(
        writer,
        state,
        "\u2022 ",
        terminal_active=True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert writer.getvalue() == (
        "\x1b[1;18r\x1b[18;1H\r\n\x1b[r"
        "\x1b[1;18r\x1b[18;1H\r\n\u2022 "
    )
    assert calls == ["resize", "bottom", "render"]
    assert writer.flush_count == 2
    assert next_state.history_has_content is True
    assert next_state.history_ended_with_blank is False


def test_run_terminal_history_stream_open_and_flush_plain_skips_terminal_callbacks() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    next_state = run_terminal_history_stream_open_and_flush(
        writer,
        TerminalHistoryState.empty(),
        "\u2022 ",
        terminal_active=False,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda: calls.append("bottom") or 18,
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert writer.getvalue() == "\u2022 "
    assert calls == []
    assert writer.flush_count == 1
    assert next_state.history_has_content is True
    assert next_state.history_ended_with_blank is False


def test_terminal_history_writer_routes_cell_output_and_keeps_state() -> None:
    # Rust owner: codex-tui::insert_history owns the stateful history insertion
    # boundary. The terminal runner should supply environment callbacks, not
    # duplicate callback sequencing and retained state management.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    history = TerminalHistoryWriter(
        writer,
        terminal_active=lambda: True,
        terminal_columns=lambda: 11,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda reserve: calls.append(f"bottom:{reserve}") or 18,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    history.write_cell("alpha beta", reserve_active_bottom_pane=True)

    assert writer.getvalue().startswith("\x1b[1;18r\x1b[18;1H\r\nalpha beta\x1b[r")
    assert calls == ["resize", "bottom:True", "clear", "render"]
    assert writer.flush_count == 1
    assert history.state.projection_cells == ("alpha beta",)
    assert history.state.history_has_content is True


def test_terminal_history_writer_can_replay_rows_without_bottom_pane_effects() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    history = TerminalHistoryWriter(
        writer,
        state=TerminalHistoryState(history_has_content=True, history_ended_with_blank=True),
        terminal_active=lambda: True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda reserve: calls.append(f"bottom:{reserve}") or 9,
        clear_bottom_pane=lambda: calls.append("clear"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    history.insert_lines(
        ["replayed"],
        clear_bottom_pane=False,
        reserve_active_bottom_pane=True,
        render_bottom_pane=False,
    )

    assert writer.getvalue().startswith("\x1b[1;9r\x1b[9;1H\r\nreplayed\x1b[r")
    assert calls == ["resize", "bottom:True"]
    assert writer.flush_count == 1
    assert history.state.history_has_content is True
    assert history.state.history_ended_with_blank is False


def test_terminal_history_writer_opens_delta_and_finishes_stream() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    history = TerminalHistoryWriter(
        writer,
        state=TerminalHistoryState(history_has_content=True, history_ended_with_blank=False),
        terminal_active=lambda: True,
        check_resize=lambda: calls.append("resize"),
        history_bottom_row=lambda reserve: calls.append(f"bottom:{reserve}") or 12,
        render_bottom_pane=lambda: calls.append("render"),
    )

    history.open_stream("\u2022 ")
    history.write_stream_delta("answer")
    next_state = history.finish_stream_projection("\u2022 answer")

    assert writer.getvalue() == (
        "\x1b[1;12r\x1b[12;1H\r\n\x1b[r"
        "\x1b[1;12r\x1b[12;1H\r\n\u2022 "
        "answer"
        "\x1b[r"
    )
    assert calls == ["resize", "bottom:False", "render", "render"]
    assert writer.flush_count == 3
    assert next_state.projection_cells == ("\u2022 answer",)
    assert history.state is next_state


def test_write_terminal_history_stream_delta_and_flush_writes_text_and_flushes() -> None:
    writer = FlushTrackingStringIO()

    write_terminal_history_stream_delta_and_flush(writer, "a\r\n  b")

    assert writer.getvalue() == "a\r\n  b"
    assert writer.flush_count == 1


def test_finish_plain_history_output_and_flush_writes_newline_and_flushes() -> None:
    writer = FlushTrackingStringIO()

    finish_plain_history_output_and_flush(writer)

    assert writer.getvalue() == "\n"
    assert writer.flush_count == 1
