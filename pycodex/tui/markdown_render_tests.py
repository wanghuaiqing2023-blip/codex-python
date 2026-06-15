"""Test-support helpers for Rust ``codex-tui::markdown_render_tests``.

Rust source: ``codex/codex-rs/tui/src/markdown_render_tests.rs``.

The Rust file is a large evidence suite for ``markdown_render``.  This Python
module ports the helper boundary owned by the test file and records categories
of renderer behavior without claiming that the tests module owns production
markdown rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple, Union

from ._porting import RustTuiModule, TuiModuleNotPortedError
from .markdown_render import render_markdown_text_with_width_and_cwd

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="markdown_render_tests",
    source="codex/codex-rs/tui/src/markdown_render_tests.rs",
    status="complete",
)

TEST_CATEGORIES: Dict[str, Tuple[str, ...]] = {
    "paragraphs": (
        "empty",
        "paragraph_single",
        "paragraph_soft_break",
        "paragraph_multiple",
    ),
    "blockquotes": (
        "blockquote_single",
        "blockquote_soft_break",
        "blockquote_nested_two_levels",
        "blockquote_with_list_items",
        "blockquote_with_code_block",
    ),
    "lists": (
        "list_unordered_single",
        "list_ordered",
        "list_nested",
        "deeply_nested_mixed_three_levels",
    ),
    "inline": (
        "inline_code",
        "strong",
        "emphasis",
        "strikethrough",
        "link",
    ),
    "file_links": (
        "file_link_hides_destination",
        "file_link_appends_line_number_when_label_lacks_it",
        "file_link_uses_target_path_for_hash_range",
    ),
    "code_blocks": (
        "code_block_known_lang_has_syntax_colors",
        "code_block_unknown_lang_plain",
        "code_block_preserves_trailing_blank_lines",
    ),
    "tables": (
        "table_renders_app_style_rows_with_themed_bold_header",
        "table_alignment_respects_markers",
        "table_falls_back_to_key_value_records_if_grid_cannot_fit",
    ),
}


@dataclass(frozen=True)
class SpanLike:
    content: str


@dataclass(frozen=True)
class LineLike:
    spans: Tuple[SpanLike, ...]


@dataclass(frozen=True)
class TextLike:
    lines: Tuple[Any, ...] = ()


def render_markdown_text_for_cwd(input_text: str, cwd: Union[str, Path]) -> Any:
    """Delegate to the production renderer with Rust test defaults.

    Rust calls ``render_markdown_text_with_width_and_cwd(input, None, Some(cwd))``.
    If the production renderer slice is incomplete, the test-support boundary
    returns semantic plain text instead of claiming production renderer parity.
    """

    try:
        return render_markdown_text_with_width_and_cwd(str(input_text), width=None, cwd=Path(cwd))
    except TuiModuleNotPortedError:
        return TextLike(tuple(LineLike((SpanLike(line),)) for line in str(input_text).splitlines()))


def plain_lines(text: Any) -> List[str]:
    """Flatten ratatui-like ``Text`` into plain line strings."""

    lines = _lines(text)
    rendered = []  # type: List[str]
    for line in lines:
        rendered.append("".join(_span_content(span) for span in _spans(line)))
    return rendered


def markdown_render_test_categories() -> Dict[str, Tuple[str, ...]]:
    return dict(TEST_CATEGORIES)


def all_markdown_render_test_names() -> Tuple[str, ...]:
    names = []  # type: List[str]
    for category_names in TEST_CATEGORIES.values():
        names.extend(category_names)
    return tuple(names)


def _lines(text: Any) -> Tuple[Any, ...]:
    if isinstance(text, TextLike):
        return text.lines
    if isinstance(text, Mapping):
        return tuple(text.get("lines", ()))
    if isinstance(text, str):
        return (LineLike((SpanLike(text),)),)
    return tuple(getattr(text, "lines", ()))


def _spans(line: Any) -> Tuple[Any, ...]:
    if isinstance(line, str):
        return (SpanLike(line),)
    if isinstance(line, Mapping):
        spans = line.get("spans")
        if spans is not None:
            return tuple(spans)
        return (SpanLike(str(line.get("text", ""))),)
    return tuple(getattr(line, "spans", (SpanLike(str(getattr(line, "text", line))),)))


def _span_content(span: Any) -> str:
    if isinstance(span, str):
        return span
    if isinstance(span, Mapping):
        return str(span.get("content", span.get("text", "")))
    return str(getattr(span, "content", getattr(span, "text", span)))


__all__ = [
    "LineLike",
    "RUST_MODULE",
    "SpanLike",
    "TEST_CATEGORIES",
    "TextLike",
    "all_markdown_render_test_names",
    "markdown_render_test_categories",
    "plain_lines",
    "render_markdown_text_for_cwd",
]
