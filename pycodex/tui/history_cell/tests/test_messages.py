"""Parity tests for codex-rs/tui/src/history_cell/messages.rs."""

from pycodex.tui.history_cell.messages import (
    AgentMarkdownCell,
    AgentMessageCell,
    StreamingAgentTailCell,
    TerminalUserPromptOutputWriter,
    TextElement,
    build_user_message_lines_with_elements,
    line_text,
    local_image_label_text,
    new_reasoning_summary_block,
    new_user_prompt,
    run_terminal_user_prompt_output,
    terminal_user_prompt_text,
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
    assert "› line one" in rendered


def test_user_history_cell_raw_lines_include_remote_image_labels() -> None:
    cell = new_user_prompt("hello\n", remote_image_urls=["https://example.com/img.png"])

    assert texts(cell.raw_lines()) == ["hello", "", local_image_label_text(1)]
    assert local_image_label_text(2) == "[Image #2]"


def test_terminal_user_prompt_text_matches_scrollback_product_shape() -> None:
    # Rust owner: codex-tui::history_cell::messages::new_user_prompt.
    assert terminal_user_prompt_text("hello?") == "\u203a hello?"


def test_run_terminal_user_prompt_output_writes_and_renders_when_terminal_active() -> None:
    # Rust owner: codex-tui::history_cell::messages owns user prompt history
    # output; terminal runtime supplies side-effect callbacks.
    calls: list[tuple[str, str | bool | None]] = []

    run_terminal_user_prompt_output(
        "hello?",
        terminal_active=True,
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, reserve_active_bottom_pane=False: calls.append(
            ("write", f"{text}|reserve={reserve_active_bottom_pane}")
        ),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    assert calls == [
        ("clear_live", None),
        ("write", "\u203a hello?|reserve=True"),
        ("render", None),
    ]


def test_run_terminal_user_prompt_output_skips_render_when_terminal_inactive() -> None:
    calls: list[tuple[str, str | None]] = []

    run_terminal_user_prompt_output(
        "offline",
        terminal_active=False,
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, **kwargs: calls.append(("write", text)),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    assert calls == [("clear_live", None), ("write", "\u203a offline")]


def test_terminal_user_prompt_output_writer_binds_runtime_callbacks() -> None:
    # Rust owner: codex-tui::history_cell::messages owns terminal user-prompt
    # scrollback output. terminal_runtime should call the bound writer instead
    # of passing prompt-output side-effect callbacks at the submit site.
    active = [True]
    calls: list[tuple[str, str | bool | None]] = []
    writer = TerminalUserPromptOutputWriter(
        terminal_active=lambda: active[0],
        clear_live_status=lambda: calls.append(("clear_live", None)),
        write_history_cell=lambda text, reserve_active_bottom_pane=False: calls.append(
            ("write", f"{text}|reserve={reserve_active_bottom_pane}")
        ),
        render_bottom_pane=lambda: calls.append(("render", None)),
    )

    writer.write("hello?")
    active[0] = False
    writer.write("offline")

    assert calls == [
        ("clear_live", None),
        ("write", "\u203a hello?|reserve=True"),
        ("render", None),
        ("clear_live", None),
        ("write", "\u203a offline|reserve=True"),
    ]


def test_trim_trailing_blank_lines_removes_blank_only_lines() -> None:
    lines = [Line.from_text("a"), Line.from_text(" "), Line.from_text("")]

    assert texts(trim_trailing_blank_lines(lines)) == ["a"]


def test_agent_message_cell_prefixes_and_raw_lines() -> None:
    cell = AgentMessageCell.new([Line.from_text("hello")], is_first_line=True)

    rendered = texts(cell.display_lines(80))
    assert rendered == ["• hello"]
    assert "鈥?" not in "\n".join(rendered)
    assert texts(cell.raw_lines()) == ["hello"]
    assert cell.is_stream_continuation() is False


def test_streaming_agent_tail_cell_uses_bullet_then_continuation_prefixes() -> None:
    first = StreamingAgentTailCell.new(
        [HyperlinkLine.new(Line.from_text("tail"))],
        is_first_line=True,
    )
    continuation = StreamingAgentTailCell.new(
        [HyperlinkLine.new(Line.from_text("tail"))],
        is_first_line=False,
    )

    assert texts(first.display_lines(80)) == ["• tail"]
    assert texts(continuation.display_lines(80)) == ["  tail"]
    assert continuation.is_stream_continuation() is True


def test_agent_markdown_cell_renders_from_source_and_preserves_raw() -> None:
    cell = AgentMarkdownCell.new("see https://example.com", ".")

    assert texts(cell.raw_lines()) == ["see https://example.com"]
    links = cell.display_hyperlink_lines(80)
    assert hyperlink_texts(links) == ["• see https://example.com"]


def test_agent_markdown_cell_rerenders_source_at_different_widths() -> None:
    # Fixed Rust owner/evidence: codex-tui::history_cell::messages and
    # history_cell/tests.rs::agent_markdown_cell_renders_source_at_different_widths.
    source = "A long agent message that should wrap differently when the terminal width changes.\n"
    cell = AgentMarkdownCell.new(source, ".")

    wide = texts(cell.display_lines(80))
    narrow = texts(cell.display_lines(32))

    assert wide[0].startswith("\u2022 ")
    assert len(narrow) > len(wide)
    assert texts(cell.raw_lines()) == [source.rstrip("\n")]


def test_agent_markdown_cell_preserves_soft_breaks_heading_and_table_layout() -> None:
    # Fixed Rust owner/evidence: codex-tui::markdown, markdown_render, and
    # history_cell::messages. Completion and resize share this source renderer.
    source = "## Heading\nfirst\nsecond\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    rendered = texts(AgentMarkdownCell.new(source, ".").display_lines(40))

    assert rendered[:3] == ["\u2022 ## Heading", "  first", "  second"]
    assert any("A" in line and "B" in line for line in rendered)
    assert any("1" in line and "2" in line for line in rendered)
    assert not any("|---|" in line for line in rendered)


def test_agent_markdown_cell_tiny_width_keeps_prefix() -> None:
    # Fixed Rust evidence:
    # history_cell/tests.rs::agent_markdown_cell_narrow_width_shows_prefix_only.
    rendered = texts(AgentMarkdownCell.new("narrow width coverage\n", ".").display_lines(2))

    assert rendered == ["\u2022 "]


def test_agent_markdown_cell_preserves_fenced_code_verbatim() -> None:
    source = "```c\n#include <stdio.h>\n```\n"

    rendered = texts(AgentMarkdownCell.new(source, ".").display_lines(80))

    assert rendered == ["\u2022 #include <stdio.h>"]


def test_reasoning_summary_block_splits_header_only_when_summary_exists() -> None:
    visible = new_reasoning_summary_block("**Reasoning** useful detail", ".")
    transcript_only = new_reasoning_summary_block("no bold header", ".")

    assert visible.transcript_only is False
    assert texts(visible.raw_lines()) == [" useful detail"]
    assert texts(visible.display_lines(80)) == ["•  useful detail"]
    assert transcript_only.transcript_only is True
    assert transcript_only.raw_lines() == []
