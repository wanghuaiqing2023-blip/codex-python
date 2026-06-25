"""Parity tests for codex-rs/tui/src/history_cell/base.rs."""

from pycodex.tui.history_cell.base import (
    CompositeHistoryCell,
    PlainHistoryCell,
    PrefixedWrappedHistoryCell,
    WebHyperlinkHistoryCell,
    line_text,
)
from pycodex.tui.line_truncation import Line, Span


def texts(lines):
    return [line_text(line) for line in lines]


def hyperlink_texts(lines):
    return [line_text(line.line) for line in lines]


def test_plain_history_cell_clones_display_and_strips_raw_styles() -> None:
    styled = Line.from_spans([Span("hello", "bold"), Span(" world", "dim")])
    cell = PlainHistoryCell.new([styled])

    assert texts(cell.display_lines(80)) == ["hello world"]
    assert cell.display_lines(80)[0].spans[0].style == "bold"
    assert texts(cell.raw_lines()) == ["hello world"]
    assert cell.raw_lines()[0].spans[0].style is None


def test_web_hyperlink_cell_annotates_display_and_transcript_links() -> None:
    cell = WebHyperlinkHistoryCell.new(["see https://example.com now"])

    display_links = cell.display_hyperlink_lines(80)
    transcript_links = cell.transcript_hyperlink_lines(80)

    assert hyperlink_texts(display_links) == ["see https://example.com now"]
    assert display_links[0].hyperlinks[0].destination == "https://example.com"
    assert transcript_links[0].hyperlinks[0].destination == "https://example.com"
    assert texts(cell.raw_lines()) == ["see https://example.com now"]


def test_prefixed_wrapped_cell_handles_zero_width_and_prefixes() -> None:
    cell = PrefixedWrappedHistoryCell.new("abcdef", "> ", "  ")

    assert cell.display_lines(0) == []
    assert texts(cell.display_lines(4)) == ["> ab", "  cd", "  ef"]
    assert texts(cell.raw_lines()) == ["abcdef"]


def test_composite_history_cell_joins_non_empty_parts_with_blank_lines() -> None:
    first = PlainHistoryCell.new(["one"])
    empty = PlainHistoryCell.new([])
    second = PlainHistoryCell.new(["two"])
    composite = CompositeHistoryCell.new([first, empty, second])

    assert texts(composite.display_lines(80)) == ["one", "", "two"]
    assert texts(composite.raw_lines()) == ["one", "", "two"]


def test_composite_hyperlink_variants_preserve_blank_separator_kind() -> None:
    first = WebHyperlinkHistoryCell.new(["https://one.example"])
    second = WebHyperlinkHistoryCell.new(["https://two.example"])
    composite = CompositeHistoryCell.new([first, second])

    display = composite.display_hyperlink_lines(80)
    transcript = composite.transcript_hyperlink_lines(80)

    assert hyperlink_texts(display) == ["https://one.example", "", "https://two.example"]
    assert hyperlink_texts(transcript) == ["https://one.example", "", "https://two.example"]
    assert display[0].hyperlinks[0].destination == "https://one.example"
    assert display[2].hyperlinks[0].destination == "https://two.example"
