"""Parity tests for Rust ``codex-tui::wrapping``.

Rust source: ``codex/codex-rs/tui/src/wrapping.rs``.
"""

from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.wrapping import (
    RtOptions,
    adaptive_wrap_line,
    concat_line,
    line_contains_url_like,
    line_has_mixed_url_and_non_url_tokens,
    map_owned_wrapped_line_to_range,
    text_contains_url_like,
    word_wrap_line,
    word_wrap_lines,
    wrap_ranges,
    wrap_ranges_trim,
)


def rendered(lines):
    return [concat_line(line) for line in lines]


def test_basic_word_wrap_and_indents() -> None:
    assert rendered(word_wrap_line(Line([Span("hello world")]), 8)) == ["hello", "world"]
    opts = RtOptions.new(8).initial_indent("- ").subsequent_indent("  ")
    out = rendered(word_wrap_line(Line([Span("hello world")]), opts))
    assert out[0].startswith("- ")
    assert all(line.startswith("  ") for line in out[1:])


def test_empty_leading_spaces_hyphen_and_break_words_behavior() -> None:
    assert rendered(word_wrap_line(Line([]), 10)) == [""]
    assert rendered(word_wrap_line(Line([Span("   hello")]), 8)) == ["   hello"]
    assert rendered(word_wrap_line(Line([Span("hello   world")]), 8)) == ["hello", "world"]
    assert rendered(word_wrap_line(Line([Span("supercalifragilistic")]), RtOptions.new(5).break_words(False))) == ["supercalifragilistic"]
    assert rendered(word_wrap_line(Line([Span("hello-world")]), 7)) == ["hello-", "world"]


def test_styled_split_within_span_preserves_style() -> None:
    out = word_wrap_line(Line([Span("abcd", style="red")]), 2)
    assert rendered(out) == ["ab", "cd"]
    assert out[0].spans[0].style == "red"
    assert out[1].spans[0].style == "red"


def test_word_wrap_lines_applies_initial_indent_once() -> None:
    opts = RtOptions.new(8).initial_indent("- ").subsequent_indent("  ")
    out = rendered(word_wrap_lines(["hello world", "foo bar baz"], opts))
    assert out[0].startswith("- ")
    assert all(line.startswith("  ") for line in out[1:])


def test_url_detection_matches_expected_tokens() -> None:
    positives = [
        "https://example.com/a/b",
        "ftp://host/path",
        "www.example.com/path?x=1",
        "example.test/path#frag",
        "localhost:3000/api",
        "127.0.0.1:8080/health",
        "(https://example.com/wrapped-in-parens)",
        "myapp://open/some/path",
    ]
    negatives = ["src/main.rs", "foo/bar", "key:value", "just-some-text-with-dashes", "hello.world"]
    assert all(text_contains_url_like(text) for text in positives)
    assert not any(text_contains_url_like(text) for text in negatives)
    assert not text_contains_url_like("localhost:99999/path")
    assert not text_contains_url_like("example.com:abc/path")


def test_line_url_detection_across_spans_and_mixed_markers() -> None:
    assert line_contains_url_like(Line([Span("see "), Span("https://example.com/a/very/long/path"), Span(" for details")]))
    assert line_has_mixed_url_and_non_url_tokens(Line([Span("see https://example.com/path for details")]))
    assert not line_has_mixed_url_and_non_url_tokens(Line([Span("  │"), Span("https://example.com/path")]))
    assert not line_has_mixed_url_and_non_url_tokens(Line([Span("1. https://example.com/path")]))


def test_adaptive_wrap_preserves_url_and_wraps_non_url() -> None:
    long_url = "example.test/a-very-long-path-with-many-segments-and-query?x=1&y=2"
    assert rendered(adaptive_wrap_line(Line([Span(long_url)]), RtOptions.new(20))) == [long_url]

    non_url = "a_very_long_token_without_spaces_to_force_wrapping"
    assert len(adaptive_wrap_line(Line([Span(non_url)]), RtOptions.new(20))) > 1


def test_adaptive_wrap_mixed_line_keeps_regular_words_intact() -> None:
    line = Line([Span("see https://example.com/path and keep strikethrough intact while wrapping prose")])
    assert rendered(adaptive_wrap_line(line, RtOptions.new(36))) == [
        "see https://example.com/path and",
        "keep strikethrough intact while",
        "wrapping prose",
    ]


def test_wrap_ranges_trim_and_sentinel_semantics() -> None:
    text = "hello   world"

    assert list(wrap_ranges_trim(text, 8)[0]) == list(range(0, 5))
    assert list(wrap_ranges(text, 8)[0]) == list(range(0, 9))

    rebuilt = "".join(text[range_.start : min(range_.stop, len(text))] for range_ in wrap_ranges_trim(text, 8))
    assert rebuilt == "helloworld"


def test_map_owned_wrapped_line_to_range_recovers_partial_prefix() -> None:
    mapped = map_owned_wrapped_line_to_range("hello world", 0, "helloX", "")
    assert mapped.start == 0
    assert mapped.stop == 5


def test_indent_consumes_width_leaving_one_char_space() -> None:
    opts = RtOptions.new(4).initial_indent(">>>>").subsequent_indent("--")
    assert rendered(word_wrap_line(Line([Span("hello")]), opts)) == [">>>>h", "--el", "--lo"]


def test_wide_unicode_wraps_by_display_width() -> None:
    line = Line([Span("😾😾😾")])
    assert rendered(word_wrap_line(line, 4)) == ["😾😾", "😾"]
    assert len(word_wrap_line(line, 2)) == 3
    assert len(word_wrap_line(line, 6)) == 1


def test_word_wrap_lines_without_indents_is_concat_of_single_wraps() -> None:
    assert rendered(word_wrap_lines(["hello", "world!"], 10)) == ["hello", "world!"]
    assert rendered(word_wrap_lines(["hello world", "foo bar baz"], 10)) == ["hello", "world", "foo bar", "baz"]
