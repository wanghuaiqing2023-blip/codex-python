from __future__ import annotations

# Rust parity source: codex-rs/tui/src/markdown_stream.rs
# Behavior contract: MarkdownStreamCollector commits only complete source lines
# through the last newline, finalizes partial tails with a newline, and clears
# all commit bookkeeping when drained or reset.

from pycodex.tui.markdown_stream import MarkdownStreamCollector, simulate_stream_markdown_for_tests


def _plain(lines):
    return [line.plain_text() for line in lines]


def test_commit_complete_source_waits_for_newline_and_returns_only_new_chunks():
    collector = MarkdownStreamCollector.new(width=80)

    collector.push_delta("Hello, world")
    assert collector.commit_complete_source() is None

    collector.push_delta("!\n")
    assert collector.commit_complete_source() == "Hello, world!\n"
    assert collector.commit_complete_source() is None

    collector.push_delta("again\n")
    assert collector.commit_complete_source() == "again\n"


def test_commit_complete_source_returns_multiple_newline_chunks_once():
    collector = MarkdownStreamCollector.new(width=None)

    collector.push_delta("a\nb\nc")

    assert collector.commit_complete_source() == "a\nb\n"
    assert collector.commit_complete_source() is None
    assert collector.finalize_and_drain_source() == "c\n"


def test_commit_complete_source_resumes_from_previous_boundary_when_tail_completes():
    # Rust: MarkdownStreamCollector tracks committed_source_len byte boundary;
    # an incomplete tail remains buffered and is returned once later completed.
    collector = MarkdownStreamCollector.new(width=None)

    collector.push_delta("alpha\nbe")
    assert collector.commit_complete_source() == "alpha\n"

    collector.push_delta("ta\n")
    assert collector.commit_complete_source() == "beta\n"
    assert collector.commit_complete_source() is None


def test_finalize_and_drain_source_adds_trailing_newline_and_clears():
    collector = MarkdownStreamCollector.new(width=None)

    collector.push_delta("partial")

    assert collector.finalize_and_drain_source() == "partial\n"
    assert collector.finalize_and_drain_source() == ""
    assert collector.buffer == ""
    assert collector.committed_source_len == 0


def test_finalize_and_drain_source_after_full_commit_clears_bookkeeping():
    collector = MarkdownStreamCollector.new(width=None)

    collector.push_delta("done\n")
    assert collector.commit_complete_source() == "done\n"

    assert collector.finalize_and_drain_source() == ""
    assert collector.buffer == ""
    assert collector.committed_source_len == 0
    assert collector.committed_line_count == 0


def test_clear_resets_commit_bookkeeping():
    collector = MarkdownStreamCollector.new(width=None)

    collector.push_delta("old\n")
    assert collector.commit_complete_source() == "old\n"
    collector.clear()
    collector.push_delta("new\n")

    assert collector.commit_complete_source() == "new\n"


def test_width_setter_and_plain_line_helpers_are_semantic_boundaries():
    collector = MarkdownStreamCollector.new(width=10)
    collector.set_width(4)
    collector.push_delta("alpha\nbeta")

    assert collector.width == 4
    assert _plain(collector.commit_complete_lines()) == ["alpha"]
    assert _plain(collector.finalize_and_drain()) == ["beta"]


def test_simulate_stream_markdown_for_tests_matches_source_boundaries():
    lines = simulate_stream_markdown_for_tests(["a", "\nb", "\nc"], finalize=True)

    assert _plain(lines) == ["a", "b", "c"]
