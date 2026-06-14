"""Parity tests for Rust ``codex-tui::table_detect``.

Rust source: ``codex/codex-rs/tui/src/table_detect.rs``.
"""

from pycodex.tui.table_detect import (
    FenceKind,
    FenceTracker,
    is_markdown_fence_info,
    is_table_delimiter_line,
    is_table_delimiter_segment,
    is_table_header_line,
    parse_fence_marker,
    parse_table_segments,
    strip_blockquote_prefix,
)


def test_parse_table_segments_rust_examples() -> None:
    assert parse_table_segments("| A | B | C |") == ["A", "B", "C"]
    assert parse_table_segments("A | B | C") == ["A", "B", "C"]
    assert parse_table_segments("A | B | C |") == ["A", "B", "C"]
    assert parse_table_segments("| A | B | C") == ["A", "B", "C"]
    assert parse_table_segments("| only |") == ["only"]
    assert parse_table_segments("just text") is None
    assert parse_table_segments("") is None
    assert parse_table_segments("   ") is None
    assert parse_table_segments(r"| A \| B | C |") == [r"A \| B", "C"]


def test_table_header_and_delimiter_detection() -> None:
    assert is_table_header_line("| A | B |")
    assert is_table_header_line("Name | Value")
    assert not is_table_header_line("| | |")

    for segment in ("---", ":---", "---:", ":---:", ":-------:"):
        assert is_table_delimiter_segment(segment)
    for segment in ("", "--", "abc", ":--"):
        assert not is_table_delimiter_segment(segment)

    assert is_table_delimiter_line("| --- | --- |")
    assert is_table_delimiter_line("|:---:|---:|")
    assert is_table_delimiter_line("--- | --- | ---")
    assert not is_table_delimiter_line("| A | B |")
    assert not is_table_delimiter_line("| -- | -- |")


def test_fence_tracker_rust_examples() -> None:
    tracker = FenceTracker.new()
    assert tracker.kind() is FenceKind.Outside

    tracker.advance("```rust")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("let x = 1;")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("```")
    assert tracker.kind() is FenceKind.Outside

    tracker.advance("~~~python")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("~~~")
    assert tracker.kind() is FenceKind.Outside

    tracker.advance("```md")
    assert tracker.kind() is FenceKind.Markdown
    tracker.advance("| A | B |")
    assert tracker.kind() is FenceKind.Markdown
    tracker.advance("```")
    assert tracker.kind() is FenceKind.Outside


def test_fence_tracker_close_rules() -> None:
    tracker = FenceTracker.new()
    tracker.advance("````sh")
    tracker.advance("```")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("````")
    assert tracker.kind() is FenceKind.Outside

    tracker.advance("```sh")
    tracker.advance("~~~")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("``` extra")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("```")
    assert tracker.kind() is FenceKind.Outside


def test_fence_tracker_indentation_blockquote_and_helpers() -> None:
    tracker = FenceTracker.new()
    tracker.advance("    ```sh")
    assert tracker.kind() is FenceKind.Outside
    tracker.advance("> ```sh")
    assert tracker.kind() is FenceKind.Other
    tracker.advance("> ```")
    assert tracker.kind() is FenceKind.Outside

    assert parse_fence_marker("```rust") == ("`", 3)
    assert parse_fence_marker("````") == ("`", 4)
    assert parse_fence_marker("~~~python") == ("~", 3)
    assert parse_fence_marker("``") is None
    assert parse_fence_marker("~~") is None
    assert parse_fence_marker("hello") is None
    assert parse_fence_marker("") is None

    assert is_markdown_fence_info("```md", 3)
    assert is_markdown_fence_info("```markdown", 3)
    assert is_markdown_fence_info("```MD", 3)
    assert not is_markdown_fence_info("```rust", 3)
    assert not is_markdown_fence_info("```", 3)

    assert strip_blockquote_prefix("> hello") == "hello"
    assert strip_blockquote_prefix("> > nested") == "nested"
    assert strip_blockquote_prefix("no prefix") == "no prefix"
