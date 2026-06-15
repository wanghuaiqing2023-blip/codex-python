from pycodex.tui.history_cell import (
    HistoryRenderMode,
    desired_height,
    desired_transcript_height,
    display_hyperlink_lines_for_mode,
    display_lines_for_mode,
    is_stream_continuation,
    plain_lines,
    raw_lines_from_source,
    render,
    transcript_animation_tick,
)
from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.terminal_hyperlinks import HyperlinkLine, SemanticBuffer, SemanticRect, TerminalHyperlink
from pycodex.tui.terminal_hyperlinks import strip_osc8


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


def test_render_clears_bottom_scrolls_and_marks_hyperlinks() -> None:
    # Rust: history_cell/mod.rs::Renderable for Box<dyn HistoryCell>.
    class TallLinkedCell:
        def display_lines(self, width: int):
            return [Line.from_text("old"), Line.from_text("display link")]

        def raw_lines(self):
            return []

        def display_hyperlink_lines(self, width: int):
            first = HyperlinkLine.new("old")
            second = HyperlinkLine.new("display link")
            second.hyperlinks.append(TerminalHyperlink(range(8, 12), "https://example.com"))
            return [first, second]

    buf = SemanticBuffer.from_lines(["xxxxx", "xxxxx"])

    render(TallLinkedCell(), SemanticRect(0, 0, 12, 1), buf)

    rendered = "".join(strip_osc8(buf.cell(column, 0).symbol) for column in range(12))
    assert rendered.startswith("display link")
    assert all("https://example.com" in buf.cell(column, 0).symbol for column in range(8, 12))
