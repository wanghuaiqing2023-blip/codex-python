from pycodex.tui.line_truncation import Line
from pycodex.tui.line_truncation import Span
from pycodex.tui.terminal_hyperlinks import HyperlinkLine
from pycodex.tui.terminal_hyperlinks import SemanticBuffer
from pycodex.tui.terminal_hyperlinks import SemanticRect
from pycodex.tui.terminal_hyperlinks import TerminalHyperlink
from pycodex.tui.terminal_hyperlinks import adaptive_wrap_hyperlink_lines
from pycodex.tui.terminal_hyperlinks import decorate_spans
from pycodex.tui.terminal_hyperlinks import line_text
from pycodex.tui.terminal_hyperlinks import mark_buffer_hyperlinks
from pycodex.tui.terminal_hyperlinks import mark_underlined_hyperlink
from pycodex.tui.terminal_hyperlinks import mark_url_hyperlink
from pycodex.tui.terminal_hyperlinks import osc8_hyperlink
from pycodex.tui.terminal_hyperlinks import prefix_hyperlink_lines
from pycodex.tui.terminal_hyperlinks import remap_wrapped_line
from pycodex.tui.terminal_hyperlinks import strip_osc8
from pycodex.tui.terminal_hyperlinks import web_links_in_text
from pycodex.tui.wrapping import RtOptions


def test_only_web_destinations_receive_osc8() -> None:
    # Rust: terminal_hyperlinks.rs::tests::only_web_destinations_receive_osc8
    assert "\x1b]8;;" in osc8_hyperlink("https://example.com/a", "a")
    assert osc8_hyperlink("mailto:a@example.com", "a") == "a"
    assert (
        osc8_hyperlink("https://example.com/\x07safe", "a")
        == "\x1b]8;;https://example.com/safe\x07a\x1b]8;;\x07"
    )
    assert strip_osc8(osc8_hyperlink("https://example.com/a", "visible")) == "visible"


def test_discovers_punctuated_web_url_columns() -> None:
    # Rust: terminal_hyperlinks.rs::tests::discovers_punctuated_web_url_columns
    assert web_links_in_text("See (https://example.com/a).") == [
        TerminalHyperlink(range(5, 26), "https://example.com/a")
    ]


def test_preserves_balanced_parentheses_in_bare_web_urls() -> None:
    # Rust: terminal_hyperlinks.rs::tests::preserves_balanced_parentheses_in_bare_web_urls
    destination = "https://en.wikipedia.org/wiki/Function_(mathematics)"
    assert web_links_in_text(f"See ({destination}).") == [
        TerminalHyperlink(range(5, 5 + len(destination)), destination)
    ]


def test_decorates_a_contiguous_web_link_with_one_osc8_pair() -> None:
    # Rust: terminal_hyperlinks.rs::tests::decorates_a_contiguous_web_link_with_one_osc8_pair
    destination = "https://example.com/a/very/long/path"
    line = HyperlinkLine(
        Line.from_text(destination),
        [TerminalHyperlink(range(0, len(destination)), destination)],
    )
    assert decorate_spans(line) == [Span(osc8_hyperlink(destination, destination))]
    assert decorate_spans(HyperlinkLine.new("not linked")) == [Span("not linked")]


def test_wrapping_maps_repeated_link_labels_by_source_position() -> None:
    # Rust: terminal_hyperlinks.rs::tests::wrapping_maps_repeated_link_labels_by_source_position
    source = HyperlinkLine.new("here here")
    source.hyperlinks.append(TerminalHyperlink(range(5, 9), "https://example.com"))
    wrapped = remap_wrapped_line(source, [Line.from_text("here here")])
    assert wrapped[0].hyperlinks == [
        TerminalHyperlink(range(5, 9), "https://example.com")
    ]


def test_prefix_hyperlink_lines_shifts_link_columns() -> None:
    source = HyperlinkLine.new("link")
    source.hyperlinks.append(TerminalHyperlink(range(0, 4), "https://example.com"))
    prefixed = prefix_hyperlink_lines([source], Span("> "), Span("  "))
    assert prefixed[0].hyperlinks == [
        TerminalHyperlink(range(2, 6), "https://example.com")
    ]


def test_push_span_records_web_destination_columns_and_skips_empty_or_unsafe_links() -> None:
    # Rust: HyperlinkLine::push_span measures current line width and only records
    # non-empty spans whose destination passes web_destination.
    line = HyperlinkLine.new("pre ")

    line.push_span(Span("link"), "https://example.com/path")
    line.push_span(Span(""), "https://example.com/empty")
    line.push_span(Span(" mail"), "mailto:a@example.com")

    assert line.line.plain_text() == "pre link mail"
    assert line.hyperlinks == [
        TerminalHyperlink(range(4, 8), "https://example.com/path")
    ]


def test_mark_buffer_hyperlinks_wraps_visible_symbols_with_osc8() -> None:
    # Rust: terminal_hyperlinks.rs::mark_buffer_hyperlinks cell mutation semantics.
    destination = "https://example.com"
    line = HyperlinkLine.new("link")
    line.hyperlinks.append(TerminalHyperlink(range(0, 4), destination))
    buf = SemanticBuffer.from_lines(["link"])

    mark_buffer_hyperlinks(buf, SemanticRect(0, 0, 4, 1), [line], scroll_rows=0)

    linked = "".join(strip_osc8(buf.cell(column, 0).symbol) for column in range(4))
    assert linked == "link"
    assert all(destination in buf.cell(column, 0).symbol for column in range(4))


def test_mark_buffer_hyperlinks_follow_word_wrapping() -> None:
    # Rust: terminal_hyperlinks.rs::tests::buffer_hyperlinks_follow_word_wrapping
    destination = "https://example.com/path"
    line = HyperlinkLine.new(f"See {destination} now")
    line.hyperlinks.append(TerminalHyperlink(range(4, 4 + len(destination)), destination))
    buf = SemanticBuffer.from_lines(["See https://exampl", "e.com/path now"])

    mark_buffer_hyperlinks(buf, SemanticRect(0, 0, 18, 2), [line], scroll_rows=0)

    linked_text = ""
    for row in range(2):
        for column in range(18):
            symbol = buf.cell(column, row).symbol
            if destination in symbol:
                linked_text += strip_osc8(symbol)
    assert linked_text == destination


def test_mark_url_and_underlined_hyperlinks_filter_matching_cells() -> None:
    destination = "https://example.com"
    buf = SemanticBuffer.from_lines(["abc"])
    buf.cell(0, 0).fg = "cyan"
    buf.cell(0, 0).modifiers.add("underlined")
    buf.cell(1, 0).modifiers.add("underlined")

    mark_url_hyperlink(buf, SemanticRect(0, 0, 3, 1), destination)
    assert destination in buf.cell(0, 0).symbol
    assert destination not in buf.cell(1, 0).symbol

    mark_underlined_hyperlink(buf, SemanticRect(0, 0, 3, 1), destination)
    assert destination in buf.cell(1, 0).symbol


def test_adaptive_wrap_hyperlink_lines_remaps_links_after_wrapping() -> None:
    # Rust: terminal_hyperlinks.rs::adaptive_wrap_hyperlink_lines wraps visible
    # text through wrapping::adaptive_wrap_line and remaps source hyperlink
    # columns onto each rendered fragment.
    destination = "https://example.com/path"
    source = HyperlinkLine.new(f"See {destination} now")
    source.hyperlinks.append(TerminalHyperlink(range(4, 4 + len(destination)), destination))

    wrapped = adaptive_wrap_hyperlink_lines([source], RtOptions.new(12))

    assert [line_text(line.line) for line in wrapped] == ["See", destination, "now"]
    assert wrapped[1].hyperlinks == [
        TerminalHyperlink(range(0, len(destination)), destination)
    ]
