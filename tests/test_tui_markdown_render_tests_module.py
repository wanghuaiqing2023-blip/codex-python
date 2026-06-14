from pathlib import Path

from pycodex.tui.markdown_render_tests import (
    LineLike,
    SpanLike,
    TextLike,
    all_markdown_render_test_names,
    markdown_render_test_categories,
    plain_lines,
    render_markdown_text_for_cwd,
)


def test_plain_lines_flattens_text_line_span_shapes() -> None:
    text = TextLike(
        lines=(
            LineLike((SpanLike("hello"), SpanLike(" world"))),
            {"spans": [{"content": "second"}, {"content": " line"}]},
            "third",
        )
    )
    assert plain_lines(text) == ["hello world", "second line", "third"]


def test_markdown_render_test_categories_document_renderer_evidence() -> None:
    categories = markdown_render_test_categories()
    assert "paragraph_single" in categories["paragraphs"]
    assert "blockquote_nested_two_levels" in categories["blockquotes"]
    assert "file_link_hides_destination" in categories["file_links"]
    assert "table_alignment_respects_markers" in categories["tables"]
    assert "strong" in all_markdown_render_test_names()


def test_render_markdown_text_for_cwd_delegates_to_renderer_boundary() -> None:
    rendered = render_markdown_text_for_cwd("Hello", Path("/tmp"))
    assert plain_lines(rendered) == ["Hello"]
