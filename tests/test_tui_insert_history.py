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
    TerminalModel,
    execute_winapi,
    insert_history_lines,
    insert_history_lines_with_mode_and_wrap_policy,
    leading_whitespace_prefix,
    wrap_history_line,
    write_history_line,
    write_spans,
)


def test_set_and_reset_scroll_region_write_ansi_like_rust_commands():
    assert SetScrollRegion(range(1, 10)).write_ansi() == "\x1b[1;10r"
    assert ResetScrollRegion().write_ansi() == "\x1b[r"


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

    assert writer.getvalue().count("<clear-eol>") >= 3


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
    assert "<clear-after-viewport><move-viewport-top>" in terminal.output.getvalue()
    assert terminal.history_rows_inserted >= 1
