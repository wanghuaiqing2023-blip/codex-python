from typing import List

from pycodex.tui.line_truncation import Line
from pycodex.tui.line_truncation import Span
from pycodex.tui.render.line_utils import is_blank_line_spaces_only
from pycodex.tui.render.line_utils import line_to_static
from pycodex.tui.render.line_utils import prefix_lines
from pycodex.tui.render.line_utils import push_owned_lines


def test_line_to_static_clones_line_metadata_and_spans() -> None:
    # Rust: codex-rs/tui/src/render/line_utils.rs::line_to_static
    line = Line.from_spans([Span("hello", "bold")], style="line", alignment="center")
    cloned = line_to_static(line)
    assert cloned == line
    assert cloned is not line
    assert cloned.spans is not line.spans


def test_push_owned_lines_appends_cloned_lines() -> None:
    # Rust: codex-rs/tui/src/render/line_utils.rs::push_owned_lines
    src = [Line.from_text("a"), Line.from_spans([Span("b", "style")])]
    existing = Line.from_text("existing")
    out: List[Line] = [existing]
    push_owned_lines(src, out)
    assert out == [existing, *src]
    assert out[1] is not src[0]


def test_is_blank_line_spaces_only_rejects_tabs_and_newlines() -> None:
    # Rust: codex-rs/tui/src/render/line_utils.rs::is_blank_line_spaces_only
    assert is_blank_line_spaces_only(Line(())) is True
    assert is_blank_line_spaces_only(Line.from_spans([Span(""), Span("   ")])) is True
    assert is_blank_line_spaces_only(Line.from_text("\t")) is False
    assert is_blank_line_spaces_only(Line.from_text("\n")) is False
    assert is_blank_line_spaces_only(Line.from_text(" x ")) is False


def test_prefix_lines_uses_initial_then_subsequent_prefixes() -> None:
    # Rust: codex-rs/tui/src/render/line_utils.rs::prefix_lines
    lines = [
        Line.from_text("first", style="line-style", alignment="center"),
        Line.from_text("second", style="line-style-2", alignment="right"),
    ]
    prefixed = prefix_lines(lines, Span("> ", "p1"), Span("  ", "p2"))
    assert prefixed[0].spans == (Span("> ", "p1"), Span("first"))
    assert prefixed[1].spans == (Span("  ", "p2"), Span("second"))
    assert prefixed[0].style == "line-style"
    assert prefixed[1].style == "line-style-2"
    assert prefixed[0].alignment is None
    assert prefixed[1].alignment is None


def test_prefix_lines_returns_empty_for_empty_input() -> None:
    assert prefix_lines([], Span("> "), Span("  ")) == []


def test_prefix_lines_accepts_string_inputs_and_copies_prefix_spans() -> None:
    # Rust accepts owned Line/Span values and returns newly reconstructed lines.
    prefixed = prefix_lines(["a", "b"], "> ", Span("  ", "indent"))
    assert prefixed[0].spans == (Span("> "), Span("a"))
    assert prefixed[1].spans == (Span("  ", "indent"), Span("b"))
    assert prefixed[0].spans[0] is not prefixed[1].spans[0]
