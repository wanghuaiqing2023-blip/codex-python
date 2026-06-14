from pycodex.tui.history_cell import (
    HistoryRenderMode,
    desired_height,
    desired_transcript_height,
    display_hyperlink_lines_for_mode,
    display_lines_for_mode,
    is_stream_continuation,
    plain_lines,
    raw_lines_from_source,
    transcript_animation_tick,
)
from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.terminal_hyperlinks import HyperlinkLine, TerminalHyperlink


class DemoCell:
    def display_lines(self, width: int):
        return [Line.from_text("display link")]

    def raw_lines(self):
        return [Line.from_text("raw")]

    def display_hyperlink_lines(self, width: int):
        line = HyperlinkLine.new("display link")
        line.hyperlinks.append(TerminalHyperlink(range(8, 12), "https://example.com"))
        return [line]


class PlainCell:
    def display_lines(self, width: int):
        return [Line.from_text("abcdef")]

    def raw_lines(self):
        return [Line.from_text("raw")]


def test_raw_lines_from_source_matches_rust_split_rules() -> None:
    # Rust: history_cell/mod.rs::raw_lines_from_source.
    assert raw_lines_from_source("") == []
    assert raw_lines_from_source("a\nb\n") == [Line.from_text("a"), Line.from_text("b")]
    assert raw_lines_from_source("a\nb") == [Line.from_text("a"), Line.from_text("b")]


def test_plain_lines_flattens_spans_and_drops_metadata() -> None:
    source = [Line([Span("a", style="bold"), Span("b", style="dim")], style="line-style")]
    assert plain_lines(source) == [Line.from_text("ab")]


def test_mode_helpers_use_rich_hyperlinks_or_raw_lines() -> None:
    rich = display_hyperlink_lines_for_mode(DemoCell(), 80, HistoryRenderMode.RICH)
    raw = display_hyperlink_lines_for_mode(DemoCell(), 80, HistoryRenderMode.RAW)

    assert rich[0].hyperlinks == [TerminalHyperlink(range(8, 12), "https://example.com")]
    assert raw == [HyperlinkLine.new(Line.from_text("raw"))]
    assert display_lines_for_mode(DemoCell(), 80, HistoryRenderMode.RAW) == [Line.from_text("raw")]


def test_default_height_and_transcript_whitespace_clamp() -> None:
    assert desired_height(PlainCell(), 3) == 2

    class WhitespaceTranscript(PlainCell):
        def transcript_lines(self, width: int):
            return [Line.from_text("   ")]

    assert desired_transcript_height(WhitespaceTranscript(), 1) == 1


def test_default_stream_and_animation_methods() -> None:
    assert is_stream_continuation(PlainCell()) is False
    assert transcript_animation_tick(PlainCell()) is None
