"""Parity tests for Rust ``codex-tui::live_wrap``.

Rust source: ``codex/codex-rs/tui/src/live_wrap.rs``.
"""

from pycodex.tui.live_wrap import Row, RowBuilder, take_prefix_by_width


def test_rows_do_not_exceed_width_ascii() -> None:
    rb = RowBuilder.new(10)
    rb.push_fragment("hello whirl this is a test")
    assert rb.rows() == [
        Row("hello whir", False),
        Row("l this is ", False),
    ]


def test_rows_do_not_exceed_width_emoji_cjk() -> None:
    rb = RowBuilder.new(6)
    rb.push_fragment("😀😀 你好")
    assert rb.rows() == [Row("😀😀 ", False)]


def test_fragmentation_invariance_long_token() -> None:
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rb_all = RowBuilder.new(7)
    rb_all.push_fragment(text)

    rb_chunks = RowBuilder.new(7)
    for index in range(0, len(text), 3):
        rb_chunks.push_fragment(text[index : min(index + 3, len(text))])

    assert rb_all.rows() == rb_chunks.rows()


def test_newline_splits_rows() -> None:
    rb = RowBuilder.new(10)
    rb.push_fragment("hello\nworld")
    rows = rb.display_rows()
    assert any(row.explicit_break for row in rows)
    assert rows[0].text == "hello"
    assert any(row.text.startswith("world") for row in rows)


def test_rewrap_on_width_change() -> None:
    rb = RowBuilder.new(10)
    rb.push_fragment("abcdefghijK")
    assert rb.rows()
    rb.set_width(5)
    assert all(row.width() <= 5 for row in rb.rows())


def test_take_prefix_by_width_returns_prefix_suffix_and_width() -> None:
    assert take_prefix_by_width("abcdef", 3) == ("abc", "def", 3)
    assert take_prefix_by_width("😀😀x", 4) == ("😀😀", "x", 4)
    assert take_prefix_by_width("", 3) == ("", "", 0)
    assert take_prefix_by_width("abc", 0) == ("", "abc", 0)


def test_drain_commit_ready_counts_current_display_row() -> None:
    rb = RowBuilder.new(3)
    rb.push_fragment("abcdefg")
    assert rb.display_rows() == [Row("abc", False), Row("def", False), Row("g", False)]
    assert rb.drain_commit_ready(2) == [Row("abc", False)]
    assert rb.display_rows() == [Row("def", False), Row("g", False)]


def test_row_builder_clamps_zero_width_like_rust() -> None:
    rb = RowBuilder.new(0)
    assert rb.width() == 1

    rb.push_fragment("ab")
    assert rb.display_rows() == [Row("a", False), Row("b", False)]

    rb.set_width(0)
    assert rb.width() == 1
    assert all(row.width() <= 1 for row in rb.display_rows())
