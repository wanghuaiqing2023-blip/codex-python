"""Parity tests for ``codex-tui/src/streaming/table_holdback.rs``.

Rust tests are exercised from ``streaming/controller.rs`` because the helper is
``pub(super)``. These tests port the table holdback scanner contract without
pulling in the stream controller implementation.
"""

from pycodex.tui.table_detect import FenceKind
from pycodex.tui.streaming.table_holdback import (
    TableHoldbackScanner,
    TableHoldbackState,
    parse_lines_with_fence_state,
    table_candidate_text,
    table_holdback_state,
)


def test_table_holdback_state_detects_header_plus_delimiter() -> None:
    # Rust: streaming::controller::tests::table_holdback_state_detects_header_plus_delimiter
    state = table_holdback_state("| Key | Description |\n| --- | --- |\n")
    assert state.is_confirmed()
    assert state.table_start == 0


def test_table_holdback_state_detects_single_column_header_plus_delimiter() -> None:
    # Rust: table_holdback_state_detects_single_column_header_plus_delimiter
    state = table_holdback_state("| Only |\n| --- |\n")
    assert state.is_confirmed()
    assert state.table_start == 0


def test_table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence() -> None:
    # Rust: table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence
    source = "````sh\n```cmd\n| Key | Description |\n| --- | --- |\n````\n"
    assert table_holdback_state(source) == TableHoldbackState.none()


def test_table_holdback_state_treats_indented_fence_text_as_plain_content() -> None:
    # Rust: table_holdback_state_treats_indented_fence_text_as_plain_content
    source = "    ```sh\n| Key | Description |\n| --- | --- |\n"
    assert table_holdback_state(source).is_confirmed()


def test_table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence() -> None:
    # Rust: table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence
    source = "> ```sh\n> | Key | Value |\n> | --- | --- |\n> ```\n"
    assert table_holdback_state(source) == TableHoldbackState.none()


def test_incremental_holdback_matches_stateless_scan_per_chunk() -> None:
    # Rust: incremental_holdback_matches_stateless_scan_per_chunk
    chunks = [
        "status | owner\n",
        "\n",
        "> ```sh\n",
        "> | A | B |\n",
        "> | --- | --- |\n",
        "> ```\n",
        "> | Key | Value |\n",
        "> | --- | --- |\n",
    ]
    scanner = TableHoldbackScanner.new()
    source = ""
    for chunk in chunks:
        source += chunk
        scanner.push_source_chunk(chunk)
        assert scanner.state() == table_holdback_state(source)


def test_incremental_holdback_detects_header_delimiter_across_chunk_boundary() -> None:
    # Rust: incremental_holdback_detects_header_delimiter_across_chunk_boundary
    scanner = TableHoldbackScanner.new()
    scanner.push_source_chunk("| A | B |\n")
    assert scanner.state() == TableHoldbackState.pending_header(0)
    scanner.push_source_chunk("| --- | --- |\n")
    assert scanner.state() == TableHoldbackState.confirmed(0)


def test_table_candidate_text_strips_blockquotes_and_requires_pipe_segments() -> None:
    # Rust source: table_candidate_text strips blockquote prefixes before segment parsing.
    assert table_candidate_text("> | Key | Value |") == "| Key | Value |"
    assert table_candidate_text("> no table here") is None


def test_parse_lines_with_fence_state_reports_source_byte_offsets() -> None:
    # Rust source: parse_lines_with_fence_state stores byte offsets into the source buffer.
    lines = parse_lines_with_fence_state("é\n```sh\n| A | B |\n")
    assert [line.source_start for line in lines[:3]] == [0, 3, 9]
    assert lines[0].fence_context is FenceKind.Outside
    assert lines[2].fence_context is FenceKind.Other


def test_scanner_reset_clears_confirmed_state() -> None:
    # Rust source: TableHoldbackScanner::reset assigns Self::new().
    scanner = TableHoldbackScanner.new()
    scanner.push_source_chunk("| A | B |\n| --- | --- |\n")
    assert scanner.state().is_confirmed()
    scanner.reset()
    assert scanner.state() == TableHoldbackState.none()
    assert scanner.source_offset == 0
