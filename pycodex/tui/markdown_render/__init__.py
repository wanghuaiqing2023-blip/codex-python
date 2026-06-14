"""Python interface scaffold for Rust ``codex-tui::markdown_render``.

Upstream source: ``codex/codex-rs/tui/src/markdown_render.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="markdown_render", source="codex/codex-rs/tui/src/markdown_render.rs")

TABLE_COLUMN_GAP: Any = None

TABLE_CELL_PADDING: Any = None

TABLE_HEADER_SEPARATOR_CHAR: Any = None

TABLE_BODY_SEPARATOR_CHAR: Any = None

@dataclass
class MarkdownStyles:
    """Python boundary for Rust ``markdown_render::MarkdownStyles``."""
    _payload: Any = None

def default(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::default``."""
    return not_ported(RUST_MODULE, "default")

@dataclass
class IndentContext:
    """Python boundary for Rust ``markdown_render::IndentContext``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "IndentContext.new")

@dataclass
class TableCell:
    """Python boundary for Rust ``markdown_render::TableCell``."""
    _payload: Any = None

    def ensure_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableCell.ensure_line")

    def push_span(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableCell.push_span")

    def push_annotated(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableCell.push_annotated")

    def hard_break(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableCell.hard_break")

    def plain_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableCell.plain_text")

@dataclass
class TableBodyRow:
    """Python boundary for Rust ``markdown_render::TableBodyRow``."""
    _payload: Any = None

@dataclass
class TableState:
    """Python boundary for Rust ``markdown_render::TableState``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "TableState.new")

@dataclass
class RenderedTableLines:
    """Python boundary for Rust ``markdown_render::RenderedTableLines``."""
    _payload: Any = None

class TableColumnKind(Enum):
    """Python boundary for Rust enum ``markdown_render::TableColumnKind``."""
    UNPORTED = "unported"

@dataclass
class TableColumnMetrics:
    """Python boundary for Rust ``markdown_render::TableColumnMetrics``."""
    _payload: Any = None

def render_markdown_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_markdown_text``."""
    return not_ported(RUST_MODULE, "render_markdown_text")

def render_markdown_text_with_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_markdown_text_with_width``."""
    return not_ported(RUST_MODULE, "render_markdown_text_with_width")

def render_markdown_text_with_width_and_cwd(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_markdown_text_with_width_and_cwd``."""
    return not_ported(RUST_MODULE, "render_markdown_text_with_width_and_cwd")

def render_markdown_lines_with_width_and_cwd(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_markdown_lines_with_width_and_cwd``."""
    return not_ported(RUST_MODULE, "render_markdown_lines_with_width_and_cwd")

@dataclass
class LinkState:
    """Python boundary for Rust ``markdown_render::LinkState``."""
    _payload: Any = None

def should_render_link_destination(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::should_render_link_destination``."""
    return not_ported(RUST_MODULE, "should_render_link_destination")

COLON_LOCATION_SUFFIX_RE: Any = None

HASH_LOCATION_SUFFIX_RE: Any = None

@dataclass
class Writer:
    """Python boundary for Rust ``markdown_render::Writer``."""
    _payload: Any = None

def new(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::new``."""
    return not_ported(RUST_MODULE, "new")

def run(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::run``."""
    return not_ported(RUST_MODULE, "run")

def handle_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::handle_event``."""
    return not_ported(RUST_MODULE, "handle_event")

def prepare_for_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::prepare_for_event``."""
    return not_ported(RUST_MODULE, "prepare_for_event")

def start_tag(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_tag``."""
    return not_ported(RUST_MODULE, "start_tag")

def end_tag(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_tag``."""
    return not_ported(RUST_MODULE, "end_tag")

def start_paragraph(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_paragraph``."""
    return not_ported(RUST_MODULE, "start_paragraph")

def end_paragraph(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_paragraph``."""
    return not_ported(RUST_MODULE, "end_paragraph")

def start_heading(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_heading``."""
    return not_ported(RUST_MODULE, "start_heading")

def end_heading(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_heading``."""
    return not_ported(RUST_MODULE, "end_heading")

def start_blockquote(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_blockquote``."""
    return not_ported(RUST_MODULE, "start_blockquote")

def end_blockquote(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_blockquote``."""
    return not_ported(RUST_MODULE, "end_blockquote")

def text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::text``."""
    return not_ported(RUST_MODULE, "text")

def code(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::code``."""
    return not_ported(RUST_MODULE, "code")

def html(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::html``."""
    return not_ported(RUST_MODULE, "html")

def hard_break(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::hard_break``."""
    return not_ported(RUST_MODULE, "hard_break")

def soft_break(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::soft_break``."""
    return not_ported(RUST_MODULE, "soft_break")

def start_list(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_list``."""
    return not_ported(RUST_MODULE, "start_list")

def end_list(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_list``."""
    return not_ported(RUST_MODULE, "end_list")

def start_item(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_item``."""
    return not_ported(RUST_MODULE, "start_item")

def start_codeblock(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_codeblock``."""
    return not_ported(RUST_MODULE, "start_codeblock")

def end_codeblock(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_codeblock``."""
    return not_ported(RUST_MODULE, "end_codeblock")

def start_table(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_table``."""
    return not_ported(RUST_MODULE, "start_table")

def end_table(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_table``."""
    return not_ported(RUST_MODULE, "end_table")

def start_table_head(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_table_head``."""
    return not_ported(RUST_MODULE, "start_table_head")

def end_table_head(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_table_head``."""
    return not_ported(RUST_MODULE, "end_table_head")

def start_table_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_table_row``."""
    return not_ported(RUST_MODULE, "start_table_row")

def has_table_row_boundary_pipe(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::has_table_row_boundary_pipe``."""
    return not_ported(RUST_MODULE, "has_table_row_boundary_pipe")

def end_table_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_table_row``."""
    return not_ported(RUST_MODULE, "end_table_row")

def start_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::start_table_cell``."""
    return not_ported(RUST_MODULE, "start_table_cell")

def end_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::end_table_cell``."""
    return not_ported(RUST_MODULE, "end_table_cell")

def in_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::in_table_cell``."""
    return not_ported(RUST_MODULE, "in_table_cell")

def push_span_to_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_span_to_table_cell``."""
    return not_ported(RUST_MODULE, "push_span_to_table_cell")

def push_table_cell_hard_break(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_table_cell_hard_break``."""
    return not_ported(RUST_MODULE, "push_table_cell_hard_break")

def push_text_to_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_text_to_table_cell``."""
    return not_ported(RUST_MODULE, "push_text_to_table_cell")

def push_text_spans_to_table_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_text_spans_to_table_cell``."""
    return not_ported(RUST_MODULE, "push_text_spans_to_table_cell")

def render_table_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_table_lines``."""
    return not_ported(RUST_MODULE, "render_table_lines")

def normalize_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::normalize_row``."""
    return not_ported(RUST_MODULE, "normalize_row")

def available_table_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::available_table_width``."""
    return not_ported(RUST_MODULE, "available_table_width")

def available_record_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::available_record_width``."""
    return not_ported(RUST_MODULE, "available_record_width")

def compute_column_widths(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::compute_column_widths``."""
    return not_ported(RUST_MODULE, "compute_column_widths")

def collect_table_column_metrics(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::collect_table_column_metrics``."""
    return not_ported(RUST_MODULE, "collect_table_column_metrics")

def preferred_column_floor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::preferred_column_floor``."""
    return not_ported(RUST_MODULE, "preferred_column_floor")

def next_column_to_shrink(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::next_column_to_shrink``."""
    return not_ported(RUST_MODULE, "next_column_to_shrink")

def column_shrink_priority(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::column_shrink_priority``."""
    return not_ported(RUST_MODULE, "column_shrink_priority")

def render_table_separator(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_table_separator``."""
    return not_ported(RUST_MODULE, "render_table_separator")

def render_table_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_table_row``."""
    return not_ported(RUST_MODULE, "render_table_row")

def render_table_pipe_fallback(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_table_pipe_fallback``."""
    return not_ported(RUST_MODULE, "render_table_pipe_fallback")

def row_to_pipe_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::row_to_pipe_line``."""
    return not_ported(RUST_MODULE, "row_to_pipe_line")

def alignments_to_pipe_delimiter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::alignments_to_pipe_delimiter``."""
    return not_ported(RUST_MODULE, "alignments_to_pipe_delimiter")

def wrap_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wrap_cell``."""
    return not_ported(RUST_MODULE, "wrap_cell")

def is_spillover_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::is_spillover_row``."""
    return not_ported(RUST_MODULE, "is_spillover_row")

def first_non_empty_only_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::first_non_empty_only_text``."""
    return not_ported(RUST_MODULE, "first_non_empty_only_text")

def looks_like_html_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::looks_like_html_content``."""
    return not_ported(RUST_MODULE, "looks_like_html_content")

def looks_like_html_label_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::looks_like_html_label_line``."""
    return not_ported(RUST_MODULE, "looks_like_html_label_line")

def spans_display_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spans_display_width``."""
    return not_ported(RUST_MODULE, "spans_display_width")

def line_display_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::line_display_width``."""
    return not_ported(RUST_MODULE, "line_display_width")

def cell_display_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::cell_display_width``."""
    return not_ported(RUST_MODULE, "cell_display_width")

def longest_token_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::longest_token_width``."""
    return not_ported(RUST_MODULE, "longest_token_width")

def push_inline_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_inline_style``."""
    return not_ported(RUST_MODULE, "push_inline_style")

def pop_inline_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::pop_inline_style``."""
    return not_ported(RUST_MODULE, "pop_inline_style")

def push_link(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_link``."""
    return not_ported(RUST_MODULE, "push_link")

def pop_link(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::pop_link``."""
    return not_ported(RUST_MODULE, "pop_link")

def suppressing_local_link_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::suppressing_local_link_label``."""
    return not_ported(RUST_MODULE, "suppressing_local_link_label")

def flush_current_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::flush_current_line``."""
    return not_ported(RUST_MODULE, "flush_current_line")

def is_blockquote_active(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::is_blockquote_active``."""
    return not_ported(RUST_MODULE, "is_blockquote_active")

def push_prewrapped_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_prewrapped_line``."""
    return not_ported(RUST_MODULE, "push_prewrapped_line")

def push_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_line``."""
    return not_ported(RUST_MODULE, "push_line")

def push_hyperlink_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_hyperlink_line``."""
    return not_ported(RUST_MODULE, "push_hyperlink_line")

def push_span(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_span``."""
    return not_ported(RUST_MODULE, "push_span")

def push_annotated(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_annotated``."""
    return not_ported(RUST_MODULE, "push_annotated")

def push_text_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_text_spans``."""
    return not_ported(RUST_MODULE, "push_text_spans")

def push_blank_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_blank_line``."""
    return not_ported(RUST_MODULE, "push_blank_line")

def push_output_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::push_output_line``."""
    return not_ported(RUST_MODULE, "push_output_line")

def prefix_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::prefix_spans``."""
    return not_ported(RUST_MODULE, "prefix_spans")

def is_local_path_like_link(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::is_local_path_like_link``."""
    return not_ported(RUST_MODULE, "is_local_path_like_link")

def render_local_link_target(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::render_local_link_target``."""
    return not_ported(RUST_MODULE, "render_local_link_target")

def parse_local_link_target(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::parse_local_link_target``."""
    return not_ported(RUST_MODULE, "parse_local_link_target")

def normalize_hash_location_suffix_fragment(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::normalize_hash_location_suffix_fragment``."""
    return not_ported(RUST_MODULE, "normalize_hash_location_suffix_fragment")

def extract_colon_location_suffix(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::extract_colon_location_suffix``."""
    return not_ported(RUST_MODULE, "extract_colon_location_suffix")

def expand_local_link_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::expand_local_link_path``."""
    return not_ported(RUST_MODULE, "expand_local_link_path")

def file_url_to_local_path_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::file_url_to_local_path_text``."""
    return not_ported(RUST_MODULE, "file_url_to_local_path_text")

def normalize_local_link_path_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::normalize_local_link_path_text``."""
    return not_ported(RUST_MODULE, "normalize_local_link_path_text")

def is_absolute_local_link_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::is_absolute_local_link_path``."""
    return not_ported(RUST_MODULE, "is_absolute_local_link_path")

def trim_trailing_local_path_separator(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::trim_trailing_local_path_separator``."""
    return not_ported(RUST_MODULE, "trim_trailing_local_path_separator")

def strip_local_path_prefix(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::strip_local_path_prefix``."""
    return not_ported(RUST_MODULE, "strip_local_path_prefix")

def display_local_link_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::display_local_link_path``."""
    return not_ported(RUST_MODULE, "display_local_link_path")

def lines_to_strings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::lines_to_strings``."""
    return not_ported(RUST_MODULE, "lines_to_strings")

def wraps_plain_text_when_width_provided(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_plain_text_when_width_provided``."""
    return not_ported(RUST_MODULE, "wraps_plain_text_when_width_provided")

def wraps_list_items_preserving_indent(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_list_items_preserving_indent``."""
    return not_ported(RUST_MODULE, "wraps_list_items_preserving_indent")

def wraps_nested_lists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_nested_lists``."""
    return not_ported(RUST_MODULE, "wraps_nested_lists")

def wraps_ordered_lists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_ordered_lists``."""
    return not_ported(RUST_MODULE, "wraps_ordered_lists")

def wraps_blockquotes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_blockquotes``."""
    return not_ported(RUST_MODULE, "wraps_blockquotes")

def wraps_blockquotes_inside_lists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_blockquotes_inside_lists``."""
    return not_ported(RUST_MODULE, "wraps_blockquotes_inside_lists")

def wraps_list_items_containing_blockquotes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wraps_list_items_containing_blockquotes``."""
    return not_ported(RUST_MODULE, "wraps_list_items_containing_blockquotes")

def does_not_wrap_code_blocks(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::does_not_wrap_code_blocks``."""
    return not_ported(RUST_MODULE, "does_not_wrap_code_blocks")

def does_not_split_long_url_like_token_without_scheme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::does_not_split_long_url_like_token_without_scheme``."""
    return not_ported(RUST_MODULE, "does_not_split_long_url_like_token_without_scheme")

def fenced_code_info_string_with_metadata_highlights(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::fenced_code_info_string_with_metadata_highlights``."""
    return not_ported(RUST_MODULE, "fenced_code_info_string_with_metadata_highlights")

def crlf_code_block_no_extra_blank_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::crlf_code_block_no_extra_blank_lines``."""
    return not_ported(RUST_MODULE, "crlf_code_block_no_extra_blank_lines")

def wrap_cell_preserves_hard_break_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wrap_cell_preserves_hard_break_lines``."""
    return not_ported(RUST_MODULE, "wrap_cell_preserves_hard_break_lines")

W: Any = None

def make_cell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::make_cell``."""
    return not_ported(RUST_MODULE, "make_cell")

def make_body_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::make_body_row``."""
    return not_ported(RUST_MODULE, "make_body_row")

def column_classification_narrative_by_word_count(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::column_classification_narrative_by_word_count``."""
    return not_ported(RUST_MODULE, "column_classification_narrative_by_word_count")

def column_classification_token_heavy_by_url_like_tokens(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::column_classification_token_heavy_by_url_like_tokens``."""
    return not_ported(RUST_MODULE, "column_classification_token_heavy_by_url_like_tokens")

def column_classification_token_heavy_for_local_path_lists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::column_classification_token_heavy_for_local_path_lists``."""
    return not_ported(RUST_MODULE, "column_classification_token_heavy_for_local_path_lists")

def column_classification_compact_all_short(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::column_classification_compact_all_short``."""
    return not_ported(RUST_MODULE, "column_classification_compact_all_short")

def preferred_floor_narrative_retains_readable_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::preferred_floor_narrative_retains_readable_width``."""
    return not_ported(RUST_MODULE, "preferred_floor_narrative_retains_readable_width")

def preferred_floor_token_heavy_retains_readable_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::preferred_floor_token_heavy_retains_readable_width``."""
    return not_ported(RUST_MODULE, "preferred_floor_token_heavy_retains_readable_width")

def preferred_floor_compact_uses_body_token(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::preferred_floor_compact_uses_body_token``."""
    return not_ported(RUST_MODULE, "preferred_floor_compact_uses_body_token")

def next_column_to_shrink_prefers_token_heavy_then_narrative(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::next_column_to_shrink_prefers_token_heavy_then_narrative``."""
    return not_ported(RUST_MODULE, "next_column_to_shrink_prefers_token_heavy_then_narrative")

def spillover_detects_single_cell_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_detects_single_cell_row``."""
    return not_ported(RUST_MODULE, "spillover_detects_single_cell_row")

def spillover_keeps_single_cell_row_with_table_pipe_syntax(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_keeps_single_cell_row_with_table_pipe_syntax``."""
    return not_ported(RUST_MODULE, "spillover_keeps_single_cell_row_with_table_pipe_syntax")

def spillover_detects_html_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_detects_html_content``."""
    return not_ported(RUST_MODULE, "spillover_detects_html_content")

def spillover_detects_label_followed_by_html(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_detects_label_followed_by_html``."""
    return not_ported(RUST_MODULE, "spillover_detects_label_followed_by_html")

def spillover_detects_trailing_html_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_detects_trailing_html_label``."""
    return not_ported(RUST_MODULE, "spillover_detects_trailing_html_label")

def spillover_keeps_normal_multi_cell_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_keeps_normal_multi_cell_row``."""
    return not_ported(RUST_MODULE, "spillover_keeps_normal_multi_cell_row")

def spillover_keeps_label_when_next_is_not_html(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::spillover_keeps_label_when_next_is_not_html``."""
    return not_ported(RUST_MODULE, "spillover_keeps_label_when_next_is_not_html")

def annotates_explicit_web_link_label_and_visible_destination(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::annotates_explicit_web_link_label_and_visible_destination``."""
    return not_ported(RUST_MODULE, "annotates_explicit_web_link_label_and_visible_destination")

def wrapped_table_url_fragments_keep_complete_web_destination(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::wrapped_table_url_fragments_keep_complete_web_destination``."""
    return not_ported(RUST_MODULE, "wrapped_table_url_fragments_keep_complete_web_destination")

def key_value_table_keeps_web_annotations(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::key_value_table_keeps_web_annotations``."""
    return not_ported(RUST_MODULE, "key_value_table_keeps_web_annotations")

def does_not_annotate_code_or_non_web_markdown_links(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::does_not_annotate_code_or_non_web_markdown_links``."""
    return not_ported(RUST_MODULE, "does_not_annotate_code_or_non_web_markdown_links")

def pipe_table_fallback_keeps_web_annotations(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``markdown_render::pipe_table_fallback_keeps_web_annotations``."""
    return not_ported(RUST_MODULE, "pipe_table_fallback_keeps_web_annotations")

__all__ = [
    "COLON_LOCATION_SUFFIX_RE",
    "HASH_LOCATION_SUFFIX_RE",
    "IndentContext",
    "LinkState",
    "MarkdownStyles",
    "RUST_MODULE",
    "RenderedTableLines",
    "TABLE_BODY_SEPARATOR_CHAR",
    "TABLE_CELL_PADDING",
    "TABLE_COLUMN_GAP",
    "TABLE_HEADER_SEPARATOR_CHAR",
    "TableBodyRow",
    "TableCell",
    "TableColumnKind",
    "TableColumnMetrics",
    "TableState",
    "W",
    "Writer",
    "alignments_to_pipe_delimiter",
    "annotates_explicit_web_link_label_and_visible_destination",
    "available_record_width",
    "available_table_width",
    "cell_display_width",
    "code",
    "collect_table_column_metrics",
    "column_classification_compact_all_short",
    "column_classification_narrative_by_word_count",
    "column_classification_token_heavy_by_url_like_tokens",
    "column_classification_token_heavy_for_local_path_lists",
    "column_shrink_priority",
    "compute_column_widths",
    "crlf_code_block_no_extra_blank_lines",
    "default",
    "display_local_link_path",
    "does_not_annotate_code_or_non_web_markdown_links",
    "does_not_split_long_url_like_token_without_scheme",
    "does_not_wrap_code_blocks",
    "end_blockquote",
    "end_codeblock",
    "end_heading",
    "end_list",
    "end_paragraph",
    "end_table",
    "end_table_cell",
    "end_table_head",
    "end_table_row",
    "end_tag",
    "expand_local_link_path",
    "extract_colon_location_suffix",
    "fenced_code_info_string_with_metadata_highlights",
    "file_url_to_local_path_text",
    "first_non_empty_only_text",
    "flush_current_line",
    "handle_event",
    "hard_break",
    "has_table_row_boundary_pipe",
    "html",
    "in_table_cell",
    "is_absolute_local_link_path",
    "is_blockquote_active",
    "is_local_path_like_link",
    "is_spillover_row",
    "key_value_table_keeps_web_annotations",
    "line_display_width",
    "lines_to_strings",
    "longest_token_width",
    "looks_like_html_content",
    "looks_like_html_label_line",
    "make_body_row",
    "make_cell",
    "new",
    "next_column_to_shrink",
    "next_column_to_shrink_prefers_token_heavy_then_narrative",
    "normalize_hash_location_suffix_fragment",
    "normalize_local_link_path_text",
    "normalize_row",
    "parse_local_link_target",
    "pipe_table_fallback_keeps_web_annotations",
    "pop_inline_style",
    "pop_link",
    "preferred_column_floor",
    "preferred_floor_compact_uses_body_token",
    "preferred_floor_narrative_retains_readable_width",
    "preferred_floor_token_heavy_retains_readable_width",
    "prefix_spans",
    "prepare_for_event",
    "push_annotated",
    "push_blank_line",
    "push_hyperlink_line",
    "push_inline_style",
    "push_line",
    "push_link",
    "push_output_line",
    "push_prewrapped_line",
    "push_span",
    "push_span_to_table_cell",
    "push_table_cell_hard_break",
    "push_text_spans",
    "push_text_spans_to_table_cell",
    "push_text_to_table_cell",
    "render_local_link_target",
    "render_markdown_lines_with_width_and_cwd",
    "render_markdown_text",
    "render_markdown_text_with_width",
    "render_markdown_text_with_width_and_cwd",
    "render_table_lines",
    "render_table_pipe_fallback",
    "render_table_row",
    "render_table_separator",
    "row_to_pipe_line",
    "run",
    "should_render_link_destination",
    "soft_break",
    "spans_display_width",
    "spillover_detects_html_content",
    "spillover_detects_label_followed_by_html",
    "spillover_detects_single_cell_row",
    "spillover_detects_trailing_html_label",
    "spillover_keeps_label_when_next_is_not_html",
    "spillover_keeps_normal_multi_cell_row",
    "spillover_keeps_single_cell_row_with_table_pipe_syntax",
    "start_blockquote",
    "start_codeblock",
    "start_heading",
    "start_item",
    "start_list",
    "start_paragraph",
    "start_table",
    "start_table_cell",
    "start_table_head",
    "start_table_row",
    "start_tag",
    "strip_local_path_prefix",
    "suppressing_local_link_label",
    "text",
    "trim_trailing_local_path_separator",
    "wrap_cell",
    "wrap_cell_preserves_hard_break_lines",
    "wrapped_table_url_fragments_keep_complete_web_destination",
    "wraps_blockquotes",
    "wraps_blockquotes_inside_lists",
    "wraps_list_items_containing_blockquotes",
    "wraps_list_items_preserving_indent",
    "wraps_nested_lists",
    "wraps_ordered_lists",
    "wraps_plain_text_when_width_provided",
]
