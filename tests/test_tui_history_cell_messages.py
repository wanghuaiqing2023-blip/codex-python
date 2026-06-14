"""Parity tests for codex-rs/tui/src/history_cell/messages.rs."""

from pycodex.tui.history_cell.messages import (
    AgentMarkdownCell,
    AgentMessageCell,
    StreamingAgentTailCell,
    TextElement,
    build_user_message_lines_with_elements,
    line_text,
    local_image_label_text,
    new_reasoning_summary_block,
    new_user_prompt,
    trim_trailing_blank_lines,
)
from pycodex.tui.line_truncation import Line
from pycodex.tui.terminal_hyperlinks import HyperlinkLine


def texts(lines):
    return [line_text(line) for line in lines]


def hyperlink_texts(lines):
    return [line_text(line.line) for line in lines]


def test_build_user_message_lines_with_elements_interleaves_styled_ranges() -> None:
    message = "hello token\nsecond"
    lines = build_user_message_lines_with_elements(
        message,
        [TextElement.new((6, 11), "token")],
        style="base",
        element_style="element",
    )

    assert texts(lines) == ["hello token", "second"]
    assert [span.style for span in lines[0].spans] == [None, "element"]
    assert lines[0].style == "base"


def test_build_user_message_lines_skips_invalid_utf8_byte_boundaries() -> None:
    message = "a界b"
    lines = build_user_message_lines_with_elements(
        message,
        [TextElement.new((2, 3), None)],
        style="base",
        element_style="element",
    )

    assert texts(lines) == ["a界b"]
    assert lines[0].spans[0].style is None


def test_user_history_cell_trims_trailing_blank_message_lines_and_keeps_one_outer_blank() -> None:
    cell = new_user_prompt(
        "line one\n\n   \n\t \n",
        remote_image_urls=["https://example.com/one.png"],
    )

    rendered = texts(cell.display_lines(80))

    assert "line one" in "\n".join(rendered)
    trailing_blank_count = 0
    for line in reversed(rendered):
        if line.strip():
            break
        trailing_blank_count += 1
    assert trailing_blank_count == 1


def test_user_history_cell_raw_lines_include_remote_image_labels() -> None:
    cell = new_user_prompt("hello\n", remote_image_urls=["https://example.com/img.png"])

    assert texts(cell.raw_lines()) == ["hello", "", local_image_label_text(1)]
    assert local_image_label_text(2) == "[Image #2]"


def test_trim_trailing_blank_lines_removes_blank_only_lines() -> None:
    lines = [Line.from_text("a"), Line.from_text(" "), Line.from_text("")]

    assert texts(trim_trailing_blank_lines(lines)) == ["a"]


def test_agent_message_cell_prefixes_and_raw_lines() -> None:
    cell = AgentMessageCell.new([Line.from_text("hello")], is_first_line=True)

    assert texts(cell.display_lines(80)) == ["> hello"]
    assert texts(cell.raw_lines()) == ["hello"]
    assert cell.is_stream_continuation() is False


def test_streaming_agent_tail_cell_uses_continuation_prefix_when_not_first() -> None:
    cell = StreamingAgentTailCell.new(
        [HyperlinkLine.new(Line.from_text("tail"))],
        is_first_line=False,
    )

    assert texts(cell.display_lines(80)) == ["  tail"]
    assert cell.is_stream_continuation() is True


def test_agent_markdown_cell_renders_from_source_and_preserves_raw() -> None:
    cell = AgentMarkdownCell.new("see https://example.com", ".")

    assert texts(cell.raw_lines()) == ["see https://example.com"]
    links = cell.display_hyperlink_lines(80)
    assert hyperlink_texts(links) == ["> see https://example.com"]


def test_reasoning_summary_block_splits_header_only_when_summary_exists() -> None:
    visible = new_reasoning_summary_block("**Reasoning** useful detail", ".")
    transcript_only = new_reasoning_summary_block("no bold header", ".")

    assert visible.transcript_only is False
    assert texts(visible.raw_lines()) == [" useful detail"]
    assert transcript_only.transcript_only is True
    assert transcript_only.raw_lines() == []
