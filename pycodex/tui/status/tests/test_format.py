from __future__ import annotations

from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.status.format import DIM_STYLE, FieldFormatter, line_display_width, push_label, truncate_line_to_width


def test_field_formatter_from_labels_aligns_label_spans_like_rust() -> None:
    # Rust: FieldFormatter::from_labels computes max Unicode label width and pads by 3.
    formatter = FieldFormatter.from_labels(["Model", "路径"])
    line = formatter.line("Model", [Span("gpt-5", {"fg": "green"})])

    assert formatter.indent == " "
    assert formatter.label_width == 5
    assert formatter.value_offset == 10
    assert formatter.value_width(12) == 2
    assert formatter.value_width(9) == 0
    assert line.spans == (
        Span(" Model:   ", DIM_STYLE),
        Span("gpt-5", {"fg": "green"}),
    )


def test_field_formatter_handles_wide_labels_and_continuations() -> None:
    # Rust: continuation starts with a dim value-indent span of value_offset spaces.
    formatter = FieldFormatter.from_labels(["路径", "Plan"])
    assert formatter.label_width == 4
    assert formatter.label_span("路径") == Span(" 路径:   ", DIM_STYLE)
    assert formatter.label_span("Plan") == Span(" Plan:   ", DIM_STYLE)
    assert formatter.continuation([Span("continued")]).spans == (
        Span(" " * formatter.value_offset, DIM_STYLE),
        Span("continued"),
    )


def test_push_label_preserves_first_seen_order() -> None:
    # Rust: push_label appends only when the BTreeSet did not already contain the label.
    labels: list[str] = []
    seen: set[str] = set()
    push_label(labels, seen, "Model")
    push_label(labels, seen, "Account")
    push_label(labels, seen, "Model")

    assert labels == ["Model", "Account"]
    assert seen == {"Model", "Account"}


def test_line_display_width_sums_span_unicode_widths() -> None:
    # Rust: line_display_width sums UnicodeWidthStr width for each span content.
    assert line_display_width(Line.from_spans([Span("ab"), Span("路径")])) == 6


def test_truncate_line_to_width_matches_rust_span_and_width_rules() -> None:
    # Rust: zero-width spans are preserved, wide chars are not split, style is retained.
    line = Line.from_spans([
        Span("", {"zero": True}),
        Span("ab", {"fg": "red"}),
        Span("路径", {"fg": "blue"}),
        Span("tail", {"fg": "gray"}),
    ])

    assert truncate_line_to_width(line, 0).spans == ()
    assert truncate_line_to_width(line, 1).spans == (Span("", {"zero": True}), Span("a", {"fg": "red"}))
    assert truncate_line_to_width(line, 4).spans == (
        Span("", {"zero": True}),
        Span("ab", {"fg": "red"}),
        Span("路", {"fg": "blue"}),
    )
    assert truncate_line_to_width(line, 20).spans == line.spans
