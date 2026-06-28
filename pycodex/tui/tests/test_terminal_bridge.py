from __future__ import annotations

import io

import pycodex.tui.terminal_bridge as terminal_bridge


def test_terminal_bridge_projects_rows_through_ratatui_buffer() -> None:
    # Rust source contract:
    # - codex-tui/src/tui.rs renders terminal output through Ratatui widgets and
    #   a cell-addressable backend.
    # - Python keeps porting-test terminal rows behind ratatui_bridge's
    #   semantic Paragraph/Text/Buffer boundary before writing TextIO output.
    rendered = terminal_bridge.render_plain_lines(["abcdef", "xy"], width=4)

    assert rendered == ["abcd", "xy"]


def test_terminal_bridge_write_plain_lines_returns_rendered_rows() -> None:
    writer = io.StringIO()

    rendered = terminal_bridge.write_plain_lines(writer, ["hello", ""], width=10, prefix="[", suffix="]")

    assert rendered == ["hello", ""]
    assert writer.getvalue() == "[hello]\n[]\n"


def test_terminal_bridge_write_styled_lines_applies_edge_style_after_bridge_projection() -> None:
    writer = io.StringIO()

    rendered = terminal_bridge.write_styled_lines(writer, ["abcdef"], width=4, prefix="<", suffix=">")

    assert rendered == ["abcd"]
    assert writer.getvalue() == "<abcd>\n"


def test_terminal_bridge_streaming_segment_does_not_append_newline() -> None:
    assert terminal_bridge.render_plain_segment("abcdef", width=4) == "abcd"
    assert terminal_bridge.render_plain_segment("") == ""


def test_terminal_bridge_streaming_segment_preserves_trailing_spaces() -> None:
    assert terminal_bridge.render_plain_segment("a  ", width=3) == "a  "
