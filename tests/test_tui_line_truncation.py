from pycodex.tui.line_truncation import Line
from pycodex.tui.line_truncation import Span
from pycodex.tui.line_truncation import line_width
from pycodex.tui.line_truncation import truncate_line_to_width
from pycodex.tui.line_truncation import truncate_line_with_ellipsis_if_overflow


def test_line_width_sums_span_display_widths() -> None:
    # Rust: codex-rs/tui/src/line_truncation.rs::line_width behavior contract.
    line = Line.from_spans([Span("ab"), Span("你好"), Span("", style="zero")])
    assert line_width(line) == 6


def test_truncate_line_to_width_preserves_line_metadata_and_span_styles() -> None:
    # Rust: codex-rs/tui/src/line_truncation.rs::truncate_line_to_width behavior contract.
    line = Line.from_spans(
        [Span("abc", style="plain"), Span("你好", style="wide")],
        style="line-style",
        alignment="left",
    )
    truncated = truncate_line_to_width(line, 5)
    assert truncated.style == "line-style"
    assert truncated.alignment == "left"
    assert truncated.spans == (Span("abc", "plain"), Span("你", "wide"))


def test_truncate_line_to_width_keeps_zero_width_spans() -> None:
    # Rust keeps zero-width spans before enforcing the maximum width cutoff.
    line = Line.from_spans([Span("", style="marker"), Span("abcdef", style="text")])
    assert truncate_line_to_width(line, 2).spans == (
        Span("", "marker"),
        Span("ab", "text"),
    )


def test_zero_width_truncation_drops_line_metadata_like_rust() -> None:
    line = Line.from_spans([Span("abc", style="text")], style="line", alignment="center")
    truncated = truncate_line_to_width(line, 0)
    assert truncated.spans == ()
    assert truncated.style is None
    assert truncated.alignment is None


def test_truncate_line_with_ellipsis_if_overflow_appends_ellipsis() -> None:
    # Rust: codex-rs/tui/src/line_truncation.rs::truncate_line_with_ellipsis_if_overflow.
    line = Line.from_spans([Span("abcdef", style="text")])
    assert truncate_line_with_ellipsis_if_overflow(line, 4).spans == (
        Span("abc", "text"),
        Span("…", "text"),
    )


def test_truncate_line_with_ellipsis_returns_original_when_not_overflowing() -> None:
    line = Line.from_spans([Span("abc", style="text")])
    assert truncate_line_with_ellipsis_if_overflow(line, 3) is line
