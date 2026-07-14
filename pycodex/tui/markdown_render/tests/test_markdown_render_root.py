from pathlib import Path

from pycodex.tui.markdown_render import (
    TableColumnKind,
    collect_table_column_metrics,
    display_local_link_path,
    lines_to_strings,
    render_local_link_target,
    render_markdown_lines_with_width_and_cwd,
    render_markdown_text,
    render_markdown_text_with_width,
    render_markdown_text_with_width_and_cwd,
    should_render_link_destination,
)
from pycodex.tui.terminal_hyperlinks import line_text


def test_render_markdown_text_wraps_plain_text_when_width_provided() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Rust test: markdown_render::tests::wraps_plain_text_when_width_provided
    rendered = render_markdown_text_with_width("alpha beta gamma", 11)

    assert lines_to_strings(rendered) == ["alpha beta", "gamma"]


def test_intraword_underscores_remain_visible_like_pulldown_cmark() -> None:
    # Rust owner: codex-tui::markdown_render delegates inline parsing to
    # pulldown-cmark/CommonMark, where intraword underscores are literal.
    rendered = render_markdown_text("PYCODEX_EXEC_DONE")

    assert lines_to_strings(rendered) == ["PYCODEX_EXEC_DONE"]


def test_render_markdown_soft_break_and_heading_marker_match_rust() -> None:
    # Rust source: codex-tui::markdown_render_tests::{paragraph_soft_break,headings}
    assert lines_to_strings(render_markdown_text("Hello\nWorld")) == ["Hello", "World"]
    assert lines_to_strings(render_markdown_text("## Heading")) == ["## Heading"]


def test_render_markdown_text_preserves_list_and_blockquote_indents() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Rust tests: wraps_list_items_preserving_indent, wraps_blockquotes
    rendered = render_markdown_text_with_width("- alpha beta gamma\n> quoted words", 10)

    assert lines_to_strings(rendered) == [
        "- alpha",
        "  beta",
        "  gamma",
        "> quoted",
        "> words",
    ]


def test_render_markdown_text_does_not_wrap_code_blocks() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Rust test: markdown_render::tests::does_not_wrap_code_blocks
    rendered = render_markdown_text_with_width("```text\nalpha beta gamma\n```", 5)

    assert lines_to_strings(rendered) == ["alpha beta gamma"]


def test_local_file_link_renders_target_relative_to_cwd() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Contract: local file links suppress the markdown label and display the real target path.
    cwd = Path("/repo")
    rendered = render_markdown_text_with_width_and_cwd("See [label](/repo/src/app.py#L12)", 80, cwd)

    assert lines_to_strings(rendered) == ["See src/app.py#L12"]
    assert should_render_link_destination("/repo/src/app.py") is False
    assert render_local_link_target("/repo/src/app.py:4:2", cwd) == "src/app.py:4:2"
    assert display_local_link_path("/repo/src/app.py", cwd) == "src/app.py"


def test_web_link_keeps_visible_label_and_hyperlink_destination() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Contract: non-local links keep the label visible and carry the destination annotation.
    lines = render_markdown_lines_with_width_and_cwd("[OpenAI](https://openai.com)", 80, None)

    assert [line_text(line.line) for line in lines] == ["OpenAI (https://openai.com)"]
    assert lines[0].hyperlinks[0].destination == "https://openai.com"
    assert should_render_link_destination("https://openai.com") is True


def test_pipe_table_uses_columnar_rows_when_scannable() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Contract: table rows preserve a columnar form while values remain scannable.
    rendered = render_markdown_text("| Name | Value |\n| --- | --- |\n| A | 1 |")

    assert lines_to_strings(rendered) == ["Name  Value", "────  ─────", "A     1"]


def test_table_column_metrics_classify_token_heavy_paths() -> None:
    # Rust source: codex-tui::markdown_render.rs
    # Rust tests: column_classification_token_heavy_for_local_path_lists
    metrics = collect_table_column_metrics(["Path"], [["/very/long/path/to/file.py"], ["./relative/path"]])

    assert metrics[0].kind is TableColumnKind.TOKEN_HEAVY


def test_fenced_code_preserves_c_include_angle_brackets_and_spacing() -> None:
    # Rust source: codex-tui/src/markdown_render.rs. Code block text events are
    # rendered literally; HTML-like inline parsing must not alter source code.
    rendered = render_markdown_text("```c\n#include <stdio.h>\n```")

    assert lines_to_strings(rendered) == ["#include <stdio.h>"]
