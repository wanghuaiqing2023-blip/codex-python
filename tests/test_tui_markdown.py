"""Parity tests for Rust ``codex-tui::markdown`` fence normalization.

Rust source: ``codex/codex-rs/tui/src/markdown.rs``.
"""

from pycodex.tui.markdown import (
    Fence,
    append_markdown,
    append_markdown_agent_keeps_non_blockquoted_markdown_fence_with_blockquote_table_example,
    append_markdown_agent_unwraps_blockquoted_markdown_fence_table,
    is_close_fence,
    markdown_fence_contains_table,
    parse_open_fence,
    strip_line_indent,
    unwrap_markdown_fences,
    unwrap_markdown_fences_repro_keeps_fence_without_header_delimiter_pair,
)
from pycodex.tui.terminal_hyperlinks import line_text


def test_strip_line_indent_matches_commonmark_fence_indent_rule() -> None:
    assert strip_line_indent("   ```md\n") == "```md"
    assert strip_line_indent("\t```md\n") is None
    assert strip_line_indent("    ```md\n") is None


def test_parse_open_and_close_fence_metadata() -> None:
    parsed = parse_open_fence(" > ```markdown\n")
    assert parsed is not None
    fence, is_markdown = parsed
    assert fence == Fence("`", 3, True)
    assert is_markdown is True
    assert is_close_fence(" > ```\n", fence) is True
    assert is_close_fence("```\n", fence) is False

    parsed = parse_open_fence("~~~rust\n")
    assert parsed is not None
    fence, is_markdown = parsed
    assert fence == Fence("~", 3, False)
    assert is_markdown is False
    assert is_close_fence("~~~~\n", fence) is True


def test_markdown_fence_contains_table_requires_adjacent_header_delimiter() -> None:
    assert markdown_fence_contains_table("| A | B |\n|---|---|\n| 1 | 2 |\n", False)
    assert not markdown_fence_contains_table("| A | B |\n\n|---|---|\n| 1 | 2 |\n", False)
    assert markdown_fence_contains_table("> | A | B |\n> |---|---|\n> | 1 | 2 |\n", True)
    assert not markdown_fence_contains_table("> | A | B |\n> not delimiter\n> |---|---|\n", True)


def test_unwrap_markdown_fences_only_for_markdown_table_bodies() -> None:
    src = "```markdown\n| A | B |\n|---|---|\n| 1 | 2 |\n```\n"
    assert unwrap_markdown_fences(src) == "| A | B |\n|---|---|\n| 1 | 2 |\n"

    non_markdown = "```rust\n| A | B |\n|---|---|\n```\n"
    assert unwrap_markdown_fences(non_markdown) == non_markdown

    no_table = "```markdown\n**bold**\n```\n"
    assert unwrap_markdown_fences(no_table) == no_table


def test_unwrap_markdown_fences_blockquote_and_unclosed_boundaries() -> None:
    rendered = append_markdown_agent_unwraps_blockquoted_markdown_fence_table()
    assert "```" not in rendered
    assert "> | A | B |" in rendered

    kept = append_markdown_agent_keeps_non_blockquoted_markdown_fence_with_blockquote_table_example()
    assert kept == "```markdown\n> | A | B |\n> |---|---|\n> | 1 | 2 |\n```\n"

    unclosed = "```markdown\n| A | B |\n|---|---|\n"
    assert unwrap_markdown_fences(unclosed) == unclosed


def test_unwrap_markdown_fences_keeps_non_adjacent_delimiter_cases() -> None:
    assert unwrap_markdown_fences_repro_keeps_fence_without_header_delimiter_pair() == (
        "```markdown\n| A | B |\nnot a delimiter row\n| --- | --- |\n# Heading\n```\n"
    )
    src = "```markdown\n| A | B |\n\n|---|---|\n| 1 | 2 |\n```\n"
    assert unwrap_markdown_fences(src) == src


def test_append_markdown_delegates_to_renderer_boundary() -> None:
    # Rust source: codex-tui/src/markdown.rs delegates append_markdown to
    # markdown_render::render_markdown_text_with_width_and_cwd.
    lines = append_markdown("plain text", None, None, [])

    assert [line_text(line) for line in lines] == ["plain text"]
