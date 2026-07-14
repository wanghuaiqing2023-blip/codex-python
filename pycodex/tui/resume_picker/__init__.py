"""Python interface scaffold for Rust ``codex-tui::resume_picker``.

Upstream source: ``codex/codex-rs/tui/src/resume_picker.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Protocol, Sequence, Tuple, Union

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="resume_picker",
    source="codex/codex-rs/tui/src/resume_picker.rs",
    status="complete",
)

PAGE_SIZE: Any = None

LOAD_NEAR_THRESHOLD: Any = None

SESSION_META_INDENT_WIDTH: Any = None

SESSION_META_DATE_WIDTH: Any = None

SESSION_META_FIELD_GAP_WIDTH: Any = None

SESSION_META_MIN_CWD_WIDTH: Any = None

SESSION_META_MAX_CWD_WIDTH: Any = None

SESSION_META_BRANCH_ICON: Any = None

SESSION_META_CWD_ICON: Any = None

FOOTER_COMPACT_BREAKPOINT: Any = None

FOOTER_HINT_LEFT_PADDING: Any = None

FOOTER_HINT_GAP: Any = None

PICKER_CHROME_HEIGHT: Any = None

PICKER_LIST_HORIZONTAL_INSET: Any = None

@dataclass
class SessionTarget:
    """Python boundary for Rust ``resume_picker::SessionTarget``."""
    _payload: Any = None

    def display_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "SessionTarget.display_label")

class SessionSelection(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionSelection``."""
    UNPORTED = "unported"

class SessionPickerAction(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionPickerAction``."""
    UNPORTED = "unported"

class SessionPickerLaunchContext(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionPickerLaunchContext``."""
    UNPORTED = "unported"

@dataclass
class PageLoadRequest:
    """Python boundary for Rust ``resume_picker::PageLoadRequest``."""
    _payload: Any = None

class PickerLoadRequest(Enum):
    """Python boundary for Rust enum ``resume_picker::PickerLoadRequest``."""
    UNPORTED = "unported"

class ProviderFilter(Enum):
    """Python boundary for Rust enum ``resume_picker::ProviderFilter``."""
    UNPORTED = "unported"

class SessionFilterMode(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionFilterMode``."""
    UNPORTED = "unported"

class ToolbarControl(Enum):
    """Python boundary for Rust enum ``resume_picker::ToolbarControl``."""
    UNPORTED = "unported"

class SessionListDensity(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionListDensity``."""
    UNPORTED = "unported"

def from_(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::from``."""
    return not_ported(RUST_MODULE, "from")

PickerLoader: Any = None

class BackgroundEvent(Enum):
    """Python boundary for Rust enum ``resume_picker::BackgroundEvent``."""
    UNPORTED = "unported"

class PageCursor(Enum):
    """Python boundary for Rust enum ``resume_picker::PageCursor``."""
    UNPORTED = "unported"

@dataclass
class PickerPage:
    """Python boundary for Rust ``resume_picker::PickerPage``."""
    _payload: Any = None

@dataclass
class SessionPickerViewPersistence:
    """Python boundary for Rust ``resume_picker::SessionPickerViewPersistence``."""
    _payload: Any = None

@dataclass
class SessionPickerRunOptions:
    """Python boundary for Rust ``resume_picker::SessionPickerRunOptions``."""
    _payload: Any = None

async def run_resume_picker_with_app_server(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::run_resume_picker_with_app_server``."""
    return not_ported(RUST_MODULE, "run_resume_picker_with_app_server")

async def run_resume_picker_from_existing_session_with_app_server(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::run_resume_picker_from_existing_session_with_app_server``."""
    return not_ported(RUST_MODULE, "run_resume_picker_from_existing_session_with_app_server")

async def run_resume_picker_with_launch_context(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::run_resume_picker_with_launch_context``."""
    return not_ported(RUST_MODULE, "run_resume_picker_with_launch_context")

async def run_fork_picker_with_app_server(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::run_fork_picker_with_app_server``."""
    return not_ported(RUST_MODULE, "run_fork_picker_with_app_server")

async def run_session_picker_with_loader(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::run_session_picker_with_loader``."""
    return not_ported(RUST_MODULE, "run_session_picker_with_loader")

def raw_reasoning_visibility(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::raw_reasoning_visibility``."""
    return not_ported(RUST_MODULE, "raw_reasoning_visibility")

def local_picker_cwd_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::local_picker_cwd_filter``."""
    return not_ported(RUST_MODULE, "local_picker_cwd_filter")

def picker_provider_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_provider_filter``."""
    return not_ported(RUST_MODULE, "picker_provider_filter")

def picker_runtime_keymap(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_runtime_keymap``."""
    return not_ported(RUST_MODULE, "picker_runtime_keymap")

def picker_cwd_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_cwd_filter``."""
    return not_ported(RUST_MODULE, "picker_cwd_filter")

def normalize_pasted_query(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::normalize_pasted_query``."""
    return not_ported(RUST_MODULE, "normalize_pasted_query")

def spawn_app_server_page_loader(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::spawn_app_server_page_loader``."""
    return not_ported(RUST_MODULE, "spawn_app_server_page_loader")

def sort_key_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::sort_key_label``."""
    return not_ported(RUST_MODULE, "sort_key_label")

@dataclass
class AltScreenGuard:
    """Python boundary for Rust ``resume_picker::AltScreenGuard``."""
    _payload: Any = None

    def enter(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "AltScreenGuard.enter")

def drop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::drop``."""
    return not_ported(RUST_MODULE, "drop")

@dataclass
class PickerState:
    """Python boundary for Rust ``resume_picker::PickerState``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.new")

    def request_frame(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.request_frame")

    def is_transcript_loading(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.is_transcript_loading")

    def note_transcript_loading_frame_drawn(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.note_transcript_loading_frame_drawn")

    def open_pending_transcript_if_ready(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.open_pending_transcript_if_ready")

    def begin_transcript_loading(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.begin_transcript_loading")

    def handle_overlay_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.handle_overlay_event")

    def open_selected_transcript(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.open_selected_transcript")

    def handle_transcript_loading_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.handle_transcript_loading_key")

    async def handle_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.handle_key")

    def handle_paste(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.handle_paste")

    def start_initial_load(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.start_initial_load")

    async def handle_background_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.handle_background_event")

    def reset_pagination(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.reset_pagination")

    def ingest_page(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.ingest_page")

    def complete_pending_page_down(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.complete_pending_page_down")

    def apply_filter(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.apply_filter")

    def row_matches_filter(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.row_matches_filter")

    def set_query(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.set_query")

    def clear_query_preserving_selection(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.clear_query_preserving_selection")

    def continue_search_if_needed(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.continue_search_if_needed")

    def continue_search_if_token_matches(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.continue_search_if_token_matches")

    def ensure_selected_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.ensure_selected_visible")

    def ensure_minimum_rows_for_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.ensure_minimum_rows_for_view")

    def update_viewport(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.update_viewport")

    def maybe_load_more_for_scroll(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.maybe_load_more_for_scroll")

    def load_more_if_needed(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.load_more_if_needed")

    def freeze_footer_percent(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.freeze_footer_percent")

    def allocate_request_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.allocate_request_token")

    def allocate_search_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.allocate_search_token")

    def toggle_sort_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.toggle_sort_key")

    def toggle_filter_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.toggle_filter_mode")

    def active_cwd_filter(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.active_cwd_filter")

    def focus_previous_toolbar_control(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.focus_previous_toolbar_control")

    def focus_next_toolbar_control(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.focus_next_toolbar_control")

    def change_focused_toolbar_value(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.change_focused_toolbar_value")

    async def toggle_density(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.toggle_density")

    async def persist_density(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.persist_density")

    def toggle_selected_expansion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.toggle_selected_expansion")

    def rendered_height_between(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.rendered_height_between")

    def has_more_above(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.has_more_above")

    def has_more_below(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.has_more_below")

    def available_content_rows(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.available_content_rows")

    def row_separator_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PickerState.row_separator_height")

@dataclass
class PaginationState:
    """Python boundary for Rust ``resume_picker::PaginationState``."""
    _payload: Any = None

class LoadingState(Enum):
    """Python boundary for Rust enum ``resume_picker::LoadingState``."""
    UNPORTED = "unported"

@dataclass
class PendingLoad:
    """Python boundary for Rust ``resume_picker::PendingLoad``."""
    _payload: Any = None

class SearchState(Enum):
    """Python boundary for Rust enum ``resume_picker::SearchState``."""
    UNPORTED = "unported"

class TranscriptPreviewState(Enum):
    """Python boundary for Rust enum ``resume_picker::TranscriptPreviewState``."""
    UNPORTED = "unported"

class SessionTranscriptState(Enum):
    """Python boundary for Rust enum ``resume_picker::SessionTranscriptState``."""
    UNPORTED = "unported"

@dataclass
class TranscriptPreviewLine:
    """Python boundary for Rust ``resume_picker::TranscriptPreviewLine``."""
    _payload: Any = None

class TranscriptPreviewSpeaker(Enum):
    """Python boundary for Rust enum ``resume_picker::TranscriptPreviewSpeaker``."""
    UNPORTED = "unported"

class LoadTrigger(Enum):
    """Python boundary for Rust enum ``resume_picker::LoadTrigger``."""
    UNPORTED = "unported"

async def load_app_server_page(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::load_app_server_page``."""
    return not_ported(RUST_MODULE, "load_app_server_page")

async def load_transcript_preview(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::load_transcript_preview``."""
    return not_ported(RUST_MODULE, "load_transcript_preview")

MAX_PREVIEW_LINES: Any = None

@dataclass
class Row:
    """Python boundary for Rust ``resume_picker::Row``."""
    _payload: Any = None

    def seen_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Row.seen_key")

    def display_preview(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Row.display_preview")

    def matches_query(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Row.matches_query")

class SeenRowKey(Enum):
    """Python boundary for Rust enum ``resume_picker::SeenRowKey``."""
    UNPORTED = "unported"

def row_from_app_server_thread(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::row_from_app_server_thread``."""
    return not_ported(RUST_MODULE, "row_from_app_server_thread")

def thread_list_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::thread_list_params``."""
    return not_ported(RUST_MODULE, "thread_list_params")

def paths_match(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::paths_match``."""
    return not_ported(RUST_MODULE, "paths_match")

def parse_timestamp_str(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::parse_timestamp_str``."""
    return not_ported(RUST_MODULE, "parse_timestamp_str")

def draw_picker(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::draw_picker``."""
    return not_ported(RUST_MODULE, "draw_picker")

def list_viewport_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::list_viewport_width``."""
    return not_ported(RUST_MODULE, "list_viewport_width")

def search_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::search_line``."""
    return not_ported(RUST_MODULE, "search_line")

def toolbar_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::toolbar_line``."""
    return not_ported(RUST_MODULE, "toolbar_line")

def sort_control_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::sort_control_spans``."""
    return not_ported(RUST_MODULE, "sort_control_spans")

def filter_control_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::filter_control_spans``."""
    return not_ported(RUST_MODULE, "filter_control_spans")

def toolbar_value(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::toolbar_value``."""
    return not_ported(RUST_MODULE, "toolbar_value")

def filter_mode_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::filter_mode_label``."""
    return not_ported(RUST_MODULE, "filter_mode_label")

@dataclass
class PickerFooterHint:
    """Python boundary for Rust ``resume_picker::PickerFooterHint``."""
    _payload: Any = None

def render_picker_footer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_picker_footer``."""
    return not_ported(RUST_MODULE, "render_picker_footer")

def render_picker_footer_separator(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_picker_footer_separator``."""
    return not_ported(RUST_MODULE, "render_picker_footer_separator")

def picker_footer_progress_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_progress_label``."""
    return not_ported(RUST_MODULE, "picker_footer_progress_label")

def picker_footer_percent(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_percent``."""
    return not_ported(RUST_MODULE, "picker_footer_percent")

def picker_footer_scroll_percent(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_scroll_percent``."""
    return not_ported(RUST_MODULE, "picker_footer_scroll_percent")

def footer_hint_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_hint_lines``."""
    return not_ported(RUST_MODULE, "footer_hint_lines")

def hint_line_for_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_for_row``."""
    return not_ported(RUST_MODULE, "hint_line_for_row")

def render_transcript_loading_overlay(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_transcript_loading_overlay``."""
    return not_ported(RUST_MODULE, "render_transcript_loading_overlay")

def transcript_loading_overlay_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::transcript_loading_overlay_style``."""
    return not_ported(RUST_MODULE, "transcript_loading_overlay_style")

class FooterHintLabelMode(Enum):
    """Python boundary for Rust enum ``resume_picker::FooterHintLabelMode``."""
    UNPORTED = "unported"

def fit_footer_hints(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::fit_footer_hints``."""
    return not_ported(RUST_MODULE, "fit_footer_hints")

def fit_footer_hint_refs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::fit_footer_hint_refs``."""
    return not_ported(RUST_MODULE, "fit_footer_hint_refs")

def footer_hint_key_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_hint_key_style``."""
    return not_ported(RUST_MODULE, "footer_hint_key_style")

def footer_hint_label_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_hint_label_style``."""
    return not_ported(RUST_MODULE, "footer_hint_label_style")

def footer_hints_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_hints_width``."""
    return not_ported(RUST_MODULE, "footer_hints_width")

def render_list(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_list``."""
    return not_ported(RUST_MODULE, "render_list")

def more_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::more_line``."""
    return not_ported(RUST_MODULE, "more_line")

def render_session_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_session_lines``."""
    return not_ported(RUST_MODULE, "render_session_lines")

def render_comfortable_session_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_comfortable_session_lines``."""
    return not_ported(RUST_MODULE, "render_comfortable_session_lines")

def apply_session_row_background(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::apply_session_row_background``."""
    return not_ported(RUST_MODULE, "apply_session_row_background")

def apply_line_background(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::apply_line_background``."""
    return not_ported(RUST_MODULE, "apply_line_background")

def render_dense_session_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_dense_session_lines``."""
    return not_ported(RUST_MODULE, "render_dense_session_lines")

@dataclass
class DenseSummaryInput:
    """Python boundary for Rust ``resume_picker::DenseSummaryInput``."""
    _payload: Any = None

def dense_summary_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_summary_line``."""
    return not_ported(RUST_MODULE, "dense_summary_line")

@dataclass
class DenseColumns:
    """Python boundary for Rust ``resume_picker::DenseColumns``."""
    _payload: Any = None

def dense_columns(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_columns``."""
    return not_ported(RUST_MODULE, "dense_columns")

def dense_zebra_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_zebra_style``."""
    return not_ported(RUST_MODULE, "dense_zebra_style")

def dense_selected_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_selected_style``."""
    return not_ported(RUST_MODULE, "dense_selected_style")

def dense_row_background_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_row_background_style``."""
    return not_ported(RUST_MODULE, "dense_row_background_style")

def dense_column_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_column_text``."""
    return not_ported(RUST_MODULE, "dense_column_text")

def selection_marker(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::selection_marker``."""
    return not_ported(RUST_MODULE, "selection_marker")

def selected_session_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::selected_session_style``."""
    return not_ported(RUST_MODULE, "selected_session_style")

def selected_session_title_span(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::selected_session_title_span``."""
    return not_ported(RUST_MODULE, "selected_session_title_span")

def render_footer_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_footer_lines``."""
    return not_ported(RUST_MODULE, "render_footer_lines")

class FooterPart(Enum):
    """Python boundary for Rust enum ``resume_picker::FooterPart``."""
    UNPORTED = "unported"

def pack_footer_parts(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::pack_footer_parts``."""
    return not_ported(RUST_MODULE, "pack_footer_parts")

def cwd_column_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::cwd_column_width``."""
    return not_ported(RUST_MODULE, "cwd_column_width")

def footer_parts_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_parts_width``."""
    return not_ported(RUST_MODULE, "footer_parts_width")

def footer_part_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_part_width``."""
    return not_ported(RUST_MODULE, "footer_part_width")

def footer_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_line``."""
    return not_ported(RUST_MODULE, "footer_line")

def push_footer_part(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::push_footer_part``."""
    return not_ported(RUST_MODULE, "push_footer_part")

def render_transcript_preview_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_transcript_preview_lines``."""
    return not_ported(RUST_MODULE, "render_transcript_preview_lines")

def render_expanded_session_details(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_expanded_session_details``."""
    return not_ported(RUST_MODULE, "render_expanded_session_details")

def render_conversation_preview_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_conversation_preview_lines``."""
    return not_ported(RUST_MODULE, "render_conversation_preview_lines")

def render_transcript_content_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_transcript_content_lines``."""
    return not_ported(RUST_MODULE, "render_transcript_content_lines")

def conversation_content_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::conversation_content_line``."""
    return not_ported(RUST_MODULE, "conversation_content_line")

def prefix_transcript_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::prefix_transcript_line``."""
    return not_ported(RUST_MODULE, "prefix_transcript_line")

def transcript_prefix_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::transcript_prefix_style``."""
    return not_ported(RUST_MODULE, "transcript_prefix_style")

def connector_style_from_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::connector_style_from_content``."""
    return not_ported(RUST_MODULE, "connector_style_from_content")

def conversation_assistant_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::conversation_assistant_style``."""
    return not_ported(RUST_MODULE, "conversation_assistant_style")

def conversation_user_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::conversation_user_style``."""
    return not_ported(RUST_MODULE, "conversation_user_style")

def expanded_detail_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::expanded_detail_line``."""
    return not_ported(RUST_MODULE, "expanded_detail_line")

LABEL_WIDTH: Any = None

def expanded_time_detail_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::expanded_time_detail_line``."""
    return not_ported(RUST_MODULE, "expanded_time_detail_line")

def format_relative_time(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::format_relative_time``."""
    return not_ported(RUST_MODULE, "format_relative_time")

def format_relative_time_long(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::format_relative_time_long``."""
    return not_ported(RUST_MODULE, "format_relative_time_long")

def plural_time(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::plural_time``."""
    return not_ported(RUST_MODULE, "plural_time")

def format_timestamp(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::format_timestamp``."""
    return not_ported(RUST_MODULE, "format_timestamp")

def render_empty_state_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_empty_state_line``."""
    return not_ported(RUST_MODULE, "render_empty_state_line")

def page(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::page``."""
    return not_ported(RUST_MODULE, "page")

def page_only_loader(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::page_only_loader``."""
    return not_ported(RUST_MODULE, "page_only_loader")

def make_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::make_row``."""
    return not_ported(RUST_MODULE, "make_row")

def footer_lines_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_lines_text``."""
    return not_ported(RUST_MODULE, "footer_lines_text")

def footer_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_snapshot``."""
    return not_ported(RUST_MODULE, "footer_snapshot")

def row_display_preview_prefers_thread_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::row_display_preview_prefers_thread_name``."""
    return not_ported(RUST_MODULE, "row_display_preview_prefers_thread_name")

def local_picker_thread_list_params_include_cwd_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::local_picker_thread_list_params_include_cwd_filter``."""
    return not_ported(RUST_MODULE, "local_picker_thread_list_params_include_cwd_filter")

def row_search_matches_metadata_fields(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::row_search_matches_metadata_fields``."""
    return not_ported(RUST_MODULE, "row_search_matches_metadata_fields")

def relative_time_formats_zero_seconds_as_now(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::relative_time_formats_zero_seconds_as_now``."""
    return not_ported(RUST_MODULE, "relative_time_formats_zero_seconds_as_now")

def long_relative_time_uses_words(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::long_relative_time_uses_words``."""
    return not_ported(RUST_MODULE, "long_relative_time_uses_words")

def expanded_session_details_include_metadata(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::expanded_session_details_include_metadata``."""
    return not_ported(RUST_MODULE, "expanded_session_details_include_metadata")

def footer_prioritizes_active_sort_timestamp(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_prioritizes_active_sort_timestamp``."""
    return not_ported(RUST_MODULE, "footer_prioritizes_active_sort_timestamp")

def footer_marks_missing_branch(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_marks_missing_branch``."""
    return not_ported(RUST_MODULE, "footer_marks_missing_branch")

def footer_branch_expands_when_line_has_room(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_branch_expands_when_line_has_room``."""
    return not_ported(RUST_MODULE, "footer_branch_expands_when_line_has_room")

def footer_cwd_truncates_to_responsive_column(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_cwd_truncates_to_responsive_column``."""
    return not_ported(RUST_MODULE, "footer_cwd_truncates_to_responsive_column")

def footer_omits_cwd_when_hidden(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::footer_omits_cwd_when_hidden``."""
    return not_ported(RUST_MODULE, "footer_omits_cwd_when_hidden")

def assert_metadata_order(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::assert_metadata_order``."""
    return not_ported(RUST_MODULE, "assert_metadata_order")

def remote_thread_list_params_omit_provider_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::remote_thread_list_params_omit_provider_filter``."""
    return not_ported(RUST_MODULE, "remote_thread_list_params_omit_provider_filter")

def remote_thread_list_params_can_include_non_interactive_sources(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::remote_thread_list_params_can_include_non_interactive_sources``."""
    return not_ported(RUST_MODULE, "remote_thread_list_params_can_include_non_interactive_sources")

def remote_picker_sends_cwd_filter_without_local_post_filtering(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::remote_picker_sends_cwd_filter_without_local_post_filtering``."""
    return not_ported(RUST_MODULE, "remote_picker_sends_cwd_filter_without_local_post_filtering")

def remote_picker_does_not_filter_rows_by_local_cwd(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::remote_picker_does_not_filter_rows_by_local_cwd``."""
    return not_ported(RUST_MODULE, "remote_picker_does_not_filter_rows_by_local_cwd")

def resume_table_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::resume_table_snapshot``."""
    return not_ported(RUST_MODULE, "resume_table_snapshot")

def resume_search_error_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::resume_search_error_snapshot``."""
    return not_ported(RUST_MODULE, "resume_search_error_snapshot")

def hint_line_switches_esc_label_for_search_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_switches_esc_label_for_search_mode``."""
    return not_ported(RUST_MODULE, "hint_line_switches_esc_label_for_search_mode")

def hint_line_labels_cancel_keys_as_exit_for_existing_session_resume_picker(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_labels_cancel_keys_as_exit_for_existing_session_resume_picker``."""
    return not_ported(RUST_MODULE, "hint_line_labels_cancel_keys_as_exit_for_existing_session_resume_picker")

def hint_line_switches_density_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_switches_density_label``."""
    return not_ported(RUST_MODULE, "hint_line_switches_density_label")

def hint_line_compacts_on_narrow_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_compacts_on_narrow_width``."""
    return not_ported(RUST_MODULE, "hint_line_compacts_on_narrow_width")

def hint_line_snapshot_uses_distributed_wide_footer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_snapshot_uses_distributed_wide_footer``."""
    return not_ported(RUST_MODULE, "hint_line_snapshot_uses_distributed_wide_footer")

def hint_line_snapshot_uses_compact_footer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_snapshot_uses_compact_footer``."""
    return not_ported(RUST_MODULE, "hint_line_snapshot_uses_compact_footer")

def hint_line_prioritizes_keybinds_when_very_narrow(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_prioritizes_keybinds_when_very_narrow``."""
    return not_ported(RUST_MODULE, "hint_line_prioritizes_keybinds_when_very_narrow")

def hint_line_shows_loading_transcript_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::hint_line_shows_loading_transcript_mode``."""
    return not_ported(RUST_MODULE, "hint_line_shows_loading_transcript_mode")

def picker_footer_percent_reports_scroll_progress(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_percent_reports_scroll_progress``."""
    return not_ported(RUST_MODULE, "picker_footer_percent_reports_scroll_progress")

def picker_footer_progress_label_shows_position_total_and_percent(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_progress_label_shows_position_total_and_percent``."""
    return not_ported(RUST_MODULE, "picker_footer_progress_label_shows_position_total_and_percent")

def picker_footer_progress_label_uses_known_count_when_more_pages_exist(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_progress_label_uses_known_count_when_more_pages_exist``."""
    return not_ported(RUST_MODULE, "picker_footer_progress_label_uses_known_count_when_more_pages_exist")

def picker_footer_progress_label_freezes_percent_while_loading(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_progress_label_freezes_percent_while_loading``."""
    return not_ported(RUST_MODULE, "picker_footer_progress_label_freezes_percent_while_loading")

def picker_footer_percent_is_complete_when_not_scrollable(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::picker_footer_percent_is_complete_when_not_scrollable``."""
    return not_ported(RUST_MODULE, "picker_footer_percent_is_complete_when_not_scrollable")

async def ctrl_o_toggles_density_without_typing_into_search(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_o_toggles_density_without_typing_into_search``."""
    return not_ported(RUST_MODULE, "ctrl_o_toggles_density_without_typing_into_search")

async def ctrl_t_requests_selected_session_transcript(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_t_requests_selected_session_transcript``."""
    return not_ported(RUST_MODULE, "ctrl_t_requests_selected_session_transcript")

async def transcript_loading_consumes_picker_input(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::transcript_loading_consumes_picker_input``."""
    return not_ported(RUST_MODULE, "transcript_loading_consumes_picker_input")

async def transcript_loading_still_allows_ctrl_c_exit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::transcript_loading_still_allows_ctrl_c_exit``."""
    return not_ported(RUST_MODULE, "transcript_loading_still_allows_ctrl_c_exit")

def transcript_loading_overlay_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::transcript_loading_overlay_snapshot``."""
    return not_ported(RUST_MODULE, "transcript_loading_overlay_snapshot")

async def raw_ctrl_t_requests_selected_session_transcript(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::raw_ctrl_t_requests_selected_session_transcript``."""
    return not_ported(RUST_MODULE, "raw_ctrl_t_requests_selected_session_transcript")

async def ctrl_t_on_row_without_thread_id_shows_inline_error(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_t_on_row_without_thread_id_shows_inline_error``."""
    return not_ported(RUST_MODULE, "ctrl_t_on_row_without_thread_id_shows_inline_error")

async def loaded_transcript_waits_for_loading_frame_before_opening_overlay(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::loaded_transcript_waits_for_loading_frame_before_opening_overlay``."""
    return not_ported(RUST_MODULE, "loaded_transcript_waits_for_loading_frame_before_opening_overlay")

async def cached_transcript_still_shows_loading_frame_before_opening_overlay(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::cached_transcript_still_shows_loading_frame_before_opening_overlay``."""
    return not_ported(RUST_MODULE, "cached_transcript_still_shows_loading_frame_before_opening_overlay")

async def ctrl_o_persists_density_preference(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_o_persists_density_preference``."""
    return not_ported(RUST_MODULE, "ctrl_o_persists_density_preference")

async def ctrl_o_keeps_toggled_density_when_persistence_fails(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_o_keeps_toggled_density_when_persistence_fails``."""
    return not_ported(RUST_MODULE, "ctrl_o_keeps_toggled_density_when_persistence_fails")

async def raw_ctrl_o_toggles_density_without_typing_into_search(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::raw_ctrl_o_toggles_density_without_typing_into_search``."""
    return not_ported(RUST_MODULE, "raw_ctrl_o_toggles_density_without_typing_into_search")

async def space_appends_to_search_query(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::space_appends_to_search_query``."""
    return not_ported(RUST_MODULE, "space_appends_to_search_query")

async def ctrl_e_toggles_selected_session_expansion(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_e_toggles_selected_session_expansion``."""
    return not_ported(RUST_MODULE, "ctrl_e_toggles_selected_session_expansion")

async def raw_ctrl_e_toggles_selected_session_expansion(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::raw_ctrl_e_toggles_selected_session_expansion``."""
    return not_ported(RUST_MODULE, "raw_ctrl_e_toggles_selected_session_expansion")

def search_line_renders_sort_and_filter_tabs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::search_line_renders_sort_and_filter_tabs``."""
    return not_ported(RUST_MODULE, "search_line_renders_sort_and_filter_tabs")

def search_line_compacts_toolbar_on_narrow_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::search_line_compacts_toolbar_on_narrow_width``."""
    return not_ported(RUST_MODULE, "search_line_compacts_toolbar_on_narrow_width")

def dense_snapshot_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_snapshot_row``."""
    return not_ported(RUST_MODULE, "dense_snapshot_row")

def render_dense_row_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::render_dense_row_snapshot``."""
    return not_ported(RUST_MODULE, "render_dense_row_snapshot")

def dense_session_snapshot_omits_cwd_in_cwd_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_omits_cwd_in_cwd_filter``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_omits_cwd_in_cwd_filter")

def dense_session_snapshot_includes_cwd_in_all_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_includes_cwd_in_all_filter``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_includes_cwd_in_all_filter")

def dense_session_snapshot_auto_hides_cwd_when_narrow(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_auto_hides_cwd_when_narrow``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_auto_hides_cwd_when_narrow")

def dense_session_snapshot_forces_cwd_when_narrow(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_forces_cwd_when_narrow``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_forces_cwd_when_narrow")

def dense_session_snapshot_drops_metadata_when_narrow(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_drops_metadata_when_narrow``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_drops_metadata_when_narrow")

def dense_session_line_prefers_thread_name_over_preview(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_line_prefers_thread_name_over_preview``."""
    return not_ported(RUST_MODULE, "dense_session_line_prefers_thread_name_over_preview")

def dense_selected_summary_line_uses_full_width_selection_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_selected_summary_line_uses_full_width_selection_style``."""
    return not_ported(RUST_MODULE, "dense_selected_summary_line_uses_full_width_selection_style")

def dense_zebra_summary_line_uses_full_width_background(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_zebra_summary_line_uses_full_width_background``."""
    return not_ported(RUST_MODULE, "dense_zebra_summary_line_uses_full_width_background")

def comfortable_zebra_lines_use_full_width_background(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::comfortable_zebra_lines_use_full_width_background``."""
    return not_ported(RUST_MODULE, "comfortable_zebra_lines_use_full_width_background")

def dense_session_snapshot_uses_no_blank_lines_between_rows(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::dense_session_snapshot_uses_no_blank_lines_between_rows``."""
    return not_ported(RUST_MODULE, "dense_session_snapshot_uses_no_blank_lines_between_rows")

def expanded_session_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::expanded_session_snapshot``."""
    return not_ported(RUST_MODULE, "expanded_session_snapshot")

def narrow_session_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::narrow_session_snapshot``."""
    return not_ported(RUST_MODULE, "narrow_session_snapshot")

def session_list_more_indicators_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::session_list_more_indicators_snapshot``."""
    return not_ported(RUST_MODULE, "session_list_more_indicators_snapshot")

def density_toggle_clears_stale_more_indicator(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::density_toggle_clears_stale_more_indicator``."""
    return not_ported(RUST_MODULE, "density_toggle_clears_stale_more_indicator")

def pageless_scrolling_deduplicates_and_keeps_order(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::pageless_scrolling_deduplicates_and_keeps_order``."""
    return not_ported(RUST_MODULE, "pageless_scrolling_deduplicates_and_keeps_order")

def ensure_minimum_rows_prefetches_when_underfilled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ensure_minimum_rows_prefetches_when_underfilled``."""
    return not_ported(RUST_MODULE, "ensure_minimum_rows_prefetches_when_underfilled")

def ensure_minimum_rows_does_not_prefetch_when_comfortable_cards_fill_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ensure_minimum_rows_does_not_prefetch_when_comfortable_cards_fill_view``."""
    return not_ported(RUST_MODULE, "ensure_minimum_rows_does_not_prefetch_when_comfortable_cards_fill_view")

def ensure_minimum_rows_still_prefetches_when_dense_rows_underfill_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ensure_minimum_rows_still_prefetches_when_dense_rows_underfill_view``."""
    return not_ported(RUST_MODULE, "ensure_minimum_rows_still_prefetches_when_dense_rows_underfill_view")

def list_viewport_width_matches_rendered_list_inset(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::list_viewport_width_matches_rendered_list_inset``."""
    return not_ported(RUST_MODULE, "list_viewport_width_matches_rendered_list_inset")

async def toggle_sort_key_reloads_with_new_sort(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::toggle_sort_key_reloads_with_new_sort``."""
    return not_ported(RUST_MODULE, "toggle_sort_key_reloads_with_new_sort")

async def default_filter_focus_arrows_reload_with_new_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::default_filter_focus_arrows_reload_with_new_filter``."""
    return not_ported(RUST_MODULE, "default_filter_focus_arrows_reload_with_new_filter")

async def all_filter_can_switch_back_to_cwd_when_cwd_candidate_exists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::all_filter_can_switch_back_to_cwd_when_cwd_candidate_exists``."""
    return not_ported(RUST_MODULE, "all_filter_can_switch_back_to_cwd_when_cwd_candidate_exists")

async def filter_stays_all_when_no_cwd_candidate_exists(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::filter_stays_all_when_no_cwd_candidate_exists``."""
    return not_ported(RUST_MODULE, "filter_stays_all_when_no_cwd_candidate_exists")

async def page_navigation_uses_view_rows(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::page_navigation_uses_view_rows``."""
    return not_ported(RUST_MODULE, "page_navigation_uses_view_rows")

async def page_and_jump_navigation_use_list_keymap(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::page_and_jump_navigation_use_list_keymap``."""
    return not_ported(RUST_MODULE, "page_and_jump_navigation_use_list_keymap")

async def ctrl_c_exits_even_when_cancel_is_remapped_to_ctrl_c(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::ctrl_c_exits_even_when_cancel_is_remapped_to_ctrl_c``."""
    return not_ported(RUST_MODULE, "ctrl_c_exits_even_when_cancel_is_remapped_to_ctrl_c")

async def end_jumps_to_last_known_row_and_starts_loading_more(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::end_jumps_to_last_known_row_and_starts_loading_more``."""
    return not_ported(RUST_MODULE, "end_jumps_to_last_known_row_and_starts_loading_more")

async def enter_on_row_without_resolvable_thread_id_shows_inline_error(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::enter_on_row_without_resolvable_thread_id_shows_inline_error``."""
    return not_ported(RUST_MODULE, "enter_on_row_without_resolvable_thread_id_shows_inline_error")

async def enter_on_pathless_thread_uses_thread_id(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::enter_on_pathless_thread_uses_thread_id``."""
    return not_ported(RUST_MODULE, "enter_on_pathless_thread_uses_thread_id")

def app_server_row_keeps_pathless_threads(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::app_server_row_keeps_pathless_threads``."""
    return not_ported(RUST_MODULE, "app_server_row_keeps_pathless_threads")

def thread_to_transcript_cells_renders_core_message_types(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::thread_to_transcript_cells_renders_core_message_types``."""
    return not_ported(RUST_MODULE, "thread_to_transcript_cells_renders_core_message_types")

def thread_to_transcript_cells_hides_raw_reasoning_when_not_enabled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::thread_to_transcript_cells_hides_raw_reasoning_when_not_enabled``."""
    return not_ported(RUST_MODULE, "thread_to_transcript_cells_hides_raw_reasoning_when_not_enabled")

def thread_to_transcript_cells_shows_raw_reasoning_over_summary_when_enabled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::thread_to_transcript_cells_shows_raw_reasoning_over_summary_when_enabled``."""
    return not_ported(RUST_MODULE, "thread_to_transcript_cells_shows_raw_reasoning_over_summary_when_enabled")

async def moving_to_last_card_scrolls_when_cards_exceed_viewport(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::moving_to_last_card_scrolls_when_cards_exceed_viewport``."""
    return not_ported(RUST_MODULE, "moving_to_last_card_scrolls_when_cards_exceed_viewport")

async def up_from_bottom_keeps_viewport_stable_when_card_remains_visible(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::up_from_bottom_keeps_viewport_stable_when_card_remains_visible``."""
    return not_ported(RUST_MODULE, "up_from_bottom_keeps_viewport_stable_when_card_remains_visible")

async def up_scrolls_only_after_crossing_top_edge(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::up_scrolls_only_after_crossing_top_edge``."""
    return not_ported(RUST_MODULE, "up_scrolls_only_after_crossing_top_edge")

def list_reports_more_rows_above_and_below(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::list_reports_more_rows_above_and_below``."""
    return not_ported(RUST_MODULE, "list_reports_more_rows_above_and_below")

async def set_query_loads_until_match_and_respects_scan_cap(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::set_query_loads_until_match_and_respects_scan_cap``."""
    return not_ported(RUST_MODULE, "set_query_loads_until_match_and_respects_scan_cap")

async def paste_appends_to_existing_query(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::paste_appends_to_existing_query``."""
    return not_ported(RUST_MODULE, "paste_appends_to_existing_query")

def normalize_pasted_query_collapses_whitespace(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::normalize_pasted_query_collapses_whitespace``."""
    return not_ported(RUST_MODULE, "normalize_pasted_query_collapses_whitespace")

async def whitespace_only_paste_is_ignored(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::whitespace_only_paste_is_ignored``."""
    return not_ported(RUST_MODULE, "whitespace_only_paste_is_ignored")

async def paste_uses_existing_search_loading_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::paste_uses_existing_search_loading_path``."""
    return not_ported(RUST_MODULE, "paste_uses_existing_search_loading_path")

async def esc_with_empty_query_starts_fresh(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::esc_with_empty_query_starts_fresh``."""
    return not_ported(RUST_MODULE, "esc_with_empty_query_starts_fresh")

async def esc_with_query_clears_search_and_preserves_selected_result(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``resume_picker::esc_with_query_clears_search_and_preserves_selected_result``."""
    return not_ported(RUST_MODULE, "esc_with_query_clears_search_and_preserves_selected_result")

__all__ = [
    "AltScreenGuard",
    "BackgroundEvent",
    "DenseColumns",
    "DenseSummaryInput",
    "FOOTER_COMPACT_BREAKPOINT",
    "FOOTER_HINT_GAP",
    "FOOTER_HINT_LEFT_PADDING",
    "FooterHintLabelMode",
    "FooterPart",
    "LABEL_WIDTH",
    "LOAD_NEAR_THRESHOLD",
    "LoadTrigger",
    "LoadingState",
    "MAX_PREVIEW_LINES",
    "PAGE_SIZE",
    "PICKER_CHROME_HEIGHT",
    "PICKER_LIST_HORIZONTAL_INSET",
    "PageCursor",
    "PageLoadRequest",
    "PaginationState",
    "PendingLoad",
    "PickerFooterHint",
    "PickerLoadRequest",
    "PickerLoader",
    "PickerPage",
    "PickerState",
    "ProviderFilter",
    "RUST_MODULE",
    "Row",
    "SESSION_META_BRANCH_ICON",
    "SESSION_META_CWD_ICON",
    "SESSION_META_DATE_WIDTH",
    "SESSION_META_FIELD_GAP_WIDTH",
    "SESSION_META_INDENT_WIDTH",
    "SESSION_META_MAX_CWD_WIDTH",
    "SESSION_META_MIN_CWD_WIDTH",
    "SearchState",
    "SeenRowKey",
    "SessionFilterMode",
    "SessionListDensity",
    "SessionPickerAction",
    "SessionPickerLaunchContext",
    "SessionPickerRunOptions",
    "SessionPickerViewPersistence",
    "SessionSelection",
    "SessionTarget",
    "SessionTranscriptState",
    "ToolbarControl",
    "TranscriptPreviewLine",
    "TranscriptPreviewSpeaker",
    "TranscriptPreviewState",
    "all_filter_can_switch_back_to_cwd_when_cwd_candidate_exists",
    "app_server_row_keeps_pathless_threads",
    "apply_line_background",
    "apply_session_row_background",
    "assert_metadata_order",
    "cached_transcript_still_shows_loading_frame_before_opening_overlay",
    "comfortable_zebra_lines_use_full_width_background",
    "connector_style_from_content",
    "conversation_assistant_style",
    "conversation_content_line",
    "conversation_user_style",
    "ctrl_c_exits_even_when_cancel_is_remapped_to_ctrl_c",
    "ctrl_e_toggles_selected_session_expansion",
    "ctrl_o_keeps_toggled_density_when_persistence_fails",
    "ctrl_o_persists_density_preference",
    "ctrl_o_toggles_density_without_typing_into_search",
    "ctrl_t_on_row_without_thread_id_shows_inline_error",
    "ctrl_t_requests_selected_session_transcript",
    "cwd_column_width",
    "default_filter_focus_arrows_reload_with_new_filter",
    "dense_column_text",
    "dense_columns",
    "dense_row_background_style",
    "dense_selected_style",
    "dense_selected_summary_line_uses_full_width_selection_style",
    "dense_session_line_prefers_thread_name_over_preview",
    "dense_session_snapshot_auto_hides_cwd_when_narrow",
    "dense_session_snapshot_drops_metadata_when_narrow",
    "dense_session_snapshot_forces_cwd_when_narrow",
    "dense_session_snapshot_includes_cwd_in_all_filter",
    "dense_session_snapshot_omits_cwd_in_cwd_filter",
    "dense_session_snapshot_uses_no_blank_lines_between_rows",
    "dense_snapshot_row",
    "dense_summary_line",
    "dense_zebra_style",
    "dense_zebra_summary_line_uses_full_width_background",
    "density_toggle_clears_stale_more_indicator",
    "draw_picker",
    "drop",
    "end_jumps_to_last_known_row_and_starts_loading_more",
    "ensure_minimum_rows_does_not_prefetch_when_comfortable_cards_fill_view",
    "ensure_minimum_rows_prefetches_when_underfilled",
    "ensure_minimum_rows_still_prefetches_when_dense_rows_underfill_view",
    "enter_on_pathless_thread_uses_thread_id",
    "enter_on_row_without_resolvable_thread_id_shows_inline_error",
    "esc_with_empty_query_starts_fresh",
    "esc_with_query_clears_search_and_preserves_selected_result",
    "expanded_detail_line",
    "expanded_session_details_include_metadata",
    "expanded_session_snapshot",
    "expanded_time_detail_line",
    "filter_control_spans",
    "filter_mode_label",
    "filter_stays_all_when_no_cwd_candidate_exists",
    "fit_footer_hint_refs",
    "fit_footer_hints",
    "footer_branch_expands_when_line_has_room",
    "footer_cwd_truncates_to_responsive_column",
    "footer_hint_key_style",
    "footer_hint_label_style",
    "footer_hint_lines",
    "footer_hints_width",
    "footer_line",
    "footer_lines_text",
    "footer_marks_missing_branch",
    "footer_omits_cwd_when_hidden",
    "footer_part_width",
    "footer_parts_width",
    "footer_prioritizes_active_sort_timestamp",
    "footer_snapshot",
    "format_relative_time",
    "format_relative_time_long",
    "format_timestamp",
    "from_",
    "hint_line_compacts_on_narrow_width",
    "hint_line_for_row",
    "hint_line_labels_cancel_keys_as_exit_for_existing_session_resume_picker",
    "hint_line_prioritizes_keybinds_when_very_narrow",
    "hint_line_shows_loading_transcript_mode",
    "hint_line_snapshot_uses_compact_footer",
    "hint_line_snapshot_uses_distributed_wide_footer",
    "hint_line_switches_density_label",
    "hint_line_switches_esc_label_for_search_mode",
    "list_reports_more_rows_above_and_below",
    "list_viewport_width",
    "list_viewport_width_matches_rendered_list_inset",
    "load_app_server_page",
    "load_transcript_preview",
    "loaded_transcript_waits_for_loading_frame_before_opening_overlay",
    "local_picker_cwd_filter",
    "local_picker_thread_list_params_include_cwd_filter",
    "long_relative_time_uses_words",
    "make_row",
    "more_line",
    "moving_to_last_card_scrolls_when_cards_exceed_viewport",
    "narrow_session_snapshot",
    "normalize_pasted_query",
    "normalize_pasted_query_collapses_whitespace",
    "pack_footer_parts",
    "page",
    "page_and_jump_navigation_use_list_keymap",
    "page_navigation_uses_view_rows",
    "page_only_loader",
    "pageless_scrolling_deduplicates_and_keeps_order",
    "parse_timestamp_str",
    "paste_appends_to_existing_query",
    "paste_uses_existing_search_loading_path",
    "paths_match",
    "picker_cwd_filter",
    "picker_footer_percent",
    "picker_footer_percent_is_complete_when_not_scrollable",
    "picker_footer_percent_reports_scroll_progress",
    "picker_footer_progress_label",
    "picker_footer_progress_label_freezes_percent_while_loading",
    "picker_footer_progress_label_shows_position_total_and_percent",
    "picker_footer_progress_label_uses_known_count_when_more_pages_exist",
    "picker_footer_scroll_percent",
    "picker_provider_filter",
    "picker_runtime_keymap",
    "plural_time",
    "prefix_transcript_line",
    "push_footer_part",
    "raw_ctrl_e_toggles_selected_session_expansion",
    "raw_ctrl_o_toggles_density_without_typing_into_search",
    "raw_ctrl_t_requests_selected_session_transcript",
    "raw_reasoning_visibility",
    "relative_time_formats_zero_seconds_as_now",
    "remote_picker_does_not_filter_rows_by_local_cwd",
    "remote_picker_sends_cwd_filter_without_local_post_filtering",
    "remote_thread_list_params_can_include_non_interactive_sources",
    "remote_thread_list_params_omit_provider_filter",
    "render_comfortable_session_lines",
    "render_conversation_preview_lines",
    "render_dense_row_snapshot",
    "render_dense_session_lines",
    "render_empty_state_line",
    "render_expanded_session_details",
    "render_footer_lines",
    "render_list",
    "render_picker_footer",
    "render_picker_footer_separator",
    "render_session_lines",
    "render_transcript_content_lines",
    "render_transcript_loading_overlay",
    "render_transcript_preview_lines",
    "resume_search_error_snapshot",
    "resume_table_snapshot",
    "row_display_preview_prefers_thread_name",
    "row_from_app_server_thread",
    "row_search_matches_metadata_fields",
    "run_fork_picker_with_app_server",
    "run_resume_picker_from_existing_session_with_app_server",
    "run_resume_picker_with_app_server",
    "run_resume_picker_with_launch_context",
    "run_session_picker_with_loader",
    "search_line",
    "search_line_compacts_toolbar_on_narrow_width",
    "search_line_renders_sort_and_filter_tabs",
    "selected_session_style",
    "selected_session_title_span",
    "selection_marker",
    "session_list_more_indicators_snapshot",
    "set_query_loads_until_match_and_respects_scan_cap",
    "sort_control_spans",
    "sort_key_label",
    "space_appends_to_search_query",
    "spawn_app_server_page_loader",
    "thread_list_params",
    "thread_to_transcript_cells_hides_raw_reasoning_when_not_enabled",
    "thread_to_transcript_cells_renders_core_message_types",
    "thread_to_transcript_cells_shows_raw_reasoning_over_summary_when_enabled",
    "toggle_sort_key_reloads_with_new_sort",
    "toolbar_line",
    "toolbar_value",
    "transcript_loading_consumes_picker_input",
    "transcript_loading_overlay_snapshot",
    "transcript_loading_overlay_style",
    "transcript_loading_still_allows_ctrl_c_exit",
    "transcript_prefix_style",
    "up_from_bottom_keeps_viewport_stable_when_card_remains_visible",
    "up_scrolls_only_after_crossing_top_edge",
    "whitespace_only_paste_is_ignored",
]

# Concrete semantic slice ported from Rust `resume_picker.rs`.
# This block intentionally overrides the generated scaffold names above while
# leaving framework-heavy picker runtime functions as explicit not_ported
# boundaries.

from pathlib import Path

PAGE_SIZE = 25
LOAD_NEAR_THRESHOLD = 5
SESSION_META_INDENT_WIDTH = 2
SESSION_META_DATE_WIDTH = 12
SESSION_META_FIELD_GAP_WIDTH = 2
SESSION_META_MIN_CWD_WIDTH = 30
SESSION_META_MAX_CWD_WIDTH = 72
SESSION_META_BRANCH_ICON = "branch"
SESSION_META_CWD_ICON = "cwd"
FOOTER_COMPACT_BREAKPOINT = 120
FOOTER_HINT_LEFT_PADDING = 1
FOOTER_HINT_GAP = 3
PICKER_CHROME_HEIGHT = 8
PICKER_LIST_HORIZONTAL_INSET = 4


@dataclass(frozen=True)
class SessionTarget:
    path: Optional[Any]
    thread_id: str

    def display_label(self) -> str:
        return str(self.path) if self.path is not None else f"thread {self.thread_id}"


@dataclass(frozen=True)
class SessionSelection:
    kind: str
    target: Optional[SessionTarget] = None

    @classmethod
    def start_fresh(cls) -> "SessionSelection":
        return cls("StartFresh")

    @classmethod
    def resume(cls, target: SessionTarget) -> "SessionSelection":
        return cls("Resume", target)

    @classmethod
    def fork(cls, target: SessionTarget) -> "SessionSelection":
        return cls("Fork", target)

    @classmethod
    def exit(cls) -> "SessionSelection":
        return cls("Exit")


class SessionPickerAction(Enum):
    RESUME = "Resume"
    FORK = "Fork"

    def title(self) -> str:
        return "Resume a previous session" if self is SessionPickerAction.RESUME else "Fork a previous session"

    def action_label(self) -> str:
        return "resume" if self is SessionPickerAction.RESUME else "fork"

    def selection(self, path: Optional[Any], thread_id: str) -> SessionSelection:
        target = SessionTarget(path, thread_id)
        return SessionSelection.resume(target) if self is SessionPickerAction.RESUME else SessionSelection.fork(target)


class SessionPickerLaunchContext(Enum):
    STARTUP = "Startup"
    EXISTING_SESSION = "ExistingSession"


@dataclass(frozen=True)
class PageLoadRequest:
    cursor: Optional[Any]
    request_token: int
    search_token: Optional[int]
    cwd_filter: Optional[Any]
    provider_filter: Any
    sort_key: Any


@dataclass(frozen=True)
class ProviderFilter:
    kind: str
    value: Optional[str] = None

    @classmethod
    def any(cls) -> "ProviderFilter":
        return cls("Any")

    @classmethod
    def match_default(cls, value: str) -> "ProviderFilter":
        return cls("MatchDefault", value)


class SessionFilterMode(Enum):
    CWD = "Cwd"
    ALL = "All"

    @classmethod
    def from_show_all(cls, show_all: bool, filter_cwd: Optional[Any]) -> "SessionFilterMode":
        return cls.ALL if show_all or filter_cwd is None else cls.CWD

    def toggle(self, filter_cwd: Optional[Any]) -> "SessionFilterMode":
        if self is SessionFilterMode.CWD:
            return SessionFilterMode.ALL
        return SessionFilterMode.CWD if filter_cwd is not None else SessionFilterMode.ALL


class ToolbarControl(Enum):
    FILTER = "Filter"
    SORT = "Sort"

    def previous(self) -> "ToolbarControl":
        return ToolbarControl.SORT if self is ToolbarControl.FILTER else ToolbarControl.FILTER

    def next(self) -> "ToolbarControl":
        return ToolbarControl.SORT if self is ToolbarControl.FILTER else ToolbarControl.FILTER


class SessionListDensity(Enum):
    COMFORTABLE = "Comfortable"
    DENSE = "Dense"

    def toggle(self) -> "SessionListDensity":
        return SessionListDensity.DENSE if self is SessionListDensity.COMFORTABLE else SessionListDensity.COMFORTABLE


def from_(mode: Any) -> SessionListDensity:
    text = str(getattr(mode, "value", getattr(mode, "name", mode))).lower()
    return SessionListDensity.DENSE if "dense" in text else SessionListDensity.COMFORTABLE


def raw_reasoning_visibility(config: Any) -> str:
    return "Visible" if bool(getattr(config, "show_raw_agent_reasoning", False)) else "Hidden"


def local_picker_cwd_filter(cwd_filter: Optional[Any], uses_remote_workspace: bool) -> Optional[Any]:
    return None if uses_remote_workspace else cwd_filter


def picker_provider_filter(config: Any, uses_remote_workspace: bool) -> ProviderFilter:
    if uses_remote_workspace:
        return ProviderFilter.any()
    return ProviderFilter.match_default(str(getattr(config, "model_provider_id")))


def picker_cwd_filter(
    config_cwd: Any,
    show_all: bool,
    uses_remote_workspace: bool,
    remote_cwd_override: Optional[Any],
) -> Optional[Any]:
    if show_all:
        return None
    if uses_remote_workspace:
        return remote_cwd_override
    return config_cwd


def normalize_pasted_query(pasted: str) -> Optional[str]:
    normalized = " ".join(str(pasted).split())
    return normalized or None


def sort_key_label(sort_key: Any) -> str:
    text = str(getattr(sort_key, "value", getattr(sort_key, "name", sort_key))).lower()
    return "Created" if "created" in text else "Updated"


def list_viewport_width(terminal_width: int) -> int:
    return max(0, int(terminal_width) - (PICKER_LIST_HORIZONTAL_INSET * 2))


# Semantic picker runtime model.  These definitions intentionally override the
# generated scaffold above and preserve the Rust module's state transitions
# without binding Python to crossterm, tokio, ratatui, or the app-server client.


@dataclass(frozen=True)
class PageCursor:
    value: str


@dataclass(frozen=True)
class PickerLoadRequest:
    kind: str
    payload: Any

    @classmethod
    def page(cls, request: PageLoadRequest) -> "PickerLoadRequest":
        return cls("Page", request)

    @classmethod
    def preview(cls, thread_id: str) -> "PickerLoadRequest":
        return cls("Preview", thread_id)

    @classmethod
    def transcript(cls, thread_id: str) -> "PickerLoadRequest":
        return cls("Transcript", thread_id)


@dataclass(frozen=True)
class BackgroundEvent:
    kind: str
    payload: Any

    @classmethod
    def page(cls, request_token: int, search_token: Optional[int], page: Any) -> "BackgroundEvent":
        return cls("Page", {"request_token": request_token, "search_token": search_token, "page": page})

    @classmethod
    def preview(cls, thread_id: str, preview: Any) -> "BackgroundEvent":
        return cls("Preview", {"thread_id": thread_id, "preview": preview})

    @classmethod
    def transcript(cls, thread_id: str, transcript: Any) -> "BackgroundEvent":
        return cls("Transcript", {"thread_id": thread_id, "transcript": transcript})


@dataclass
class PickerPage:
    rows: List[Any]
    next_cursor: Optional[PageCursor] = None
    num_scanned_files: int = 0
    reached_scan_cap: bool = False


@dataclass
class SessionPickerViewPersistence:
    codex_home: Any


@dataclass
class SessionPickerRunOptions:
    show_all: bool
    filter_cwd: Optional[Any]
    local_filter_cwd: Optional[Any]
    action: SessionPickerAction
    launch_context: SessionPickerLaunchContext
    provider_filter: ProviderFilter
    initial_density: SessionListDensity
    view_persistence: Optional[SessionPickerViewPersistence] = None
    pager_keymap: Any = None
    list_keymap: Any = None


@dataclass
class PaginationState:
    next_cursor: Optional[PageCursor] = None
    loaded_count: int = 0
    num_scanned_files: int = 0
    reached_scan_cap: bool = False


class LoadingState(Enum):
    IDLE = "Idle"
    LOADING = "Loading"
    ERROR = "Error"


@dataclass
class PendingLoad:
    request_token: int
    search_token: Optional[int]


@dataclass
class SearchState:
    token: Optional[int] = None
    active: bool = False

    def is_active(self) -> bool:
        return self.active


class TranscriptPreviewSpeaker(Enum):
    USER = "User"
    ASSISTANT = "Assistant"
    SYSTEM = "System"


@dataclass(frozen=True)
class TranscriptPreviewLine:
    speaker: TranscriptPreviewSpeaker
    text: str


@dataclass
class TranscriptPreviewState:
    previews: Any = None


@dataclass
class SessionTranscriptState:
    thread_id: Optional[str] = None
    transcript: Any = None
    loading_frame_drawn: bool = False


class LoadTrigger(Enum):
    INITIAL = "Initial"
    SCROLL = "Scroll"
    SEARCH = "Search"


@dataclass(frozen=True)
class SeenRowKey:
    value: str


@dataclass
class Row:
    path: Optional[Any]
    thread_id: Optional[str]
    preview: str = ""
    cwd: Optional[Any] = None
    branch: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    model_provider: Optional[str] = None
    thread_name: Optional[str] = None
    error: Optional[str] = None
    expanded: bool = False

    def seen_key(self) -> SeenRowKey:
        if self.path is not None:
            return SeenRowKey("path:" + str(self.path))
        return SeenRowKey("thread:" + str(self.thread_id))

    def display_preview(self) -> str:
        return self.thread_name or self.preview

    def matches_query(self, query: str) -> bool:
        needle = query.lower()
        haystack = " ".join(
            str(part)
            for part in (
                self.path,
                self.thread_id,
                self.preview,
                self.cwd,
                self.branch,
                self.model_provider,
                self.thread_name,
            )
            if part is not None
        ).lower()
        return needle in haystack


def row_from_app_server_thread(thread: Any) -> Row:
    return Row(
        path=_get_attr(thread, "path"),
        thread_id=str(_get_attr(thread, "id", _get_attr(thread, "thread_id", ""))) or None,
        preview=str(_get_attr(thread, "preview", "")),
        cwd=_get_attr(thread, "cwd"),
        branch=_get_attr(_get_attr(thread, "git_info", None), "branch", None),
        created_at=str(_get_attr(thread, "created_at", "")) or None,
        updated_at=str(_get_attr(thread, "updated_at", "")) or None,
        model_provider=_get_attr(thread, "model_provider"),
        thread_name=_get_attr(thread, "name"),
    )


def thread_list_params(
    cursor: Optional[PageCursor],
    cwd_filter: Optional[Any],
    provider_filter: ProviderFilter,
    sort_key: Any,
    include_non_interactive: bool = False,
) -> dict:
    return {
        "cursor": cursor.value if cursor else None,
        "cwd_filter": None if cwd_filter is None else str(cwd_filter),
        "provider_filter": provider_filter.value if provider_filter.kind == "MatchDefault" else None,
        "sort_key": sort_key,
        "page_size": PAGE_SIZE,
        "include_non_interactive": include_non_interactive,
    }


def paths_match(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    try:
        return Path(left).resolve() == Path(right).resolve()
    except Exception:
        return str(left) == str(right)


def parse_timestamp_str(value: str) -> str:
    return str(value)


class PickerState:
    def __init__(
        self,
        frame_requester: Any = None,
        picker_loader: Optional[Any] = None,
        provider_filter: Optional[ProviderFilter] = None,
        show_all: bool = False,
        filter_cwd: Optional[Any] = None,
        action: SessionPickerAction = SessionPickerAction.RESUME,
    ) -> None:
        self.frame_requester = frame_requester
        self.picker_loader = picker_loader or (lambda request: None)
        self.provider_filter = provider_filter or ProviderFilter.any()
        self.filter_mode = SessionFilterMode.from_show_all(show_all, filter_cwd)
        self.filter_cwd = filter_cwd
        self.local_filter_cwd = filter_cwd
        self.action = action
        self.launch_context = SessionPickerLaunchContext.STARTUP
        self.density = SessionListDensity.COMFORTABLE
        self.toolbar_control = ToolbarControl.FILTER
        self.sort_key = "UpdatedAt"
        self.view_persistence = None
        self.pager_keymap = None
        self.list_keymap = None
        self.rows = []
        self.filtered_rows = []
        self.seen_keys = set()
        self.selected = 0
        self.scroll_top = 0
        self.viewport_rows = 0
        self.viewport_width = 0
        self.query = ""
        self.pagination = PaginationState()
        self.loading_state = LoadingState.IDLE
        self.pending_load = None
        self.search_state = SearchState()
        self.request_token_counter = 0
        self.search_token_counter = 0
        self.preview_state = TranscriptPreviewState({})
        self.transcript_state = SessionTranscriptState()
        self.overlay = None
        self.footer_percent_frozen = None

    @classmethod
    def new(cls, *args: Any, **kwargs: Any) -> "PickerState":
        return cls(*args, **kwargs)

    def request_frame(self) -> None:
        requester = self.frame_requester
        if hasattr(requester, "request_frame"):
            requester.request_frame()

    def allocate_request_token(self) -> int:
        self.request_token_counter += 1
        return self.request_token_counter

    def allocate_search_token(self) -> int:
        self.search_token_counter += 1
        return self.search_token_counter

    def start_initial_load(self) -> None:
        self.reset_pagination()
        self.load_more_if_needed(LoadTrigger.INITIAL)

    def reset_pagination(self) -> None:
        self.rows = []
        self.filtered_rows = []
        self.seen_keys = set()
        self.selected = 0
        self.scroll_top = 0
        self.pagination = PaginationState()
        self.loading_state = LoadingState.IDLE
        self.pending_load = None

    def ingest_page(self, page: PickerPage) -> None:
        for row in page.rows:
            row = row if isinstance(row, Row) else row_from_app_server_thread(row)
            key = row.seen_key()
            if key in self.seen_keys:
                continue
            self.seen_keys.add(key)
            if self.local_filter_cwd is not None and row.cwd is not None and not paths_match(row.cwd, self.local_filter_cwd):
                continue
            self.rows.append(row)
        self.pagination.next_cursor = page.next_cursor
        self.pagination.loaded_count = len(self.rows)
        self.pagination.num_scanned_files += page.num_scanned_files
        self.pagination.reached_scan_cap = self.pagination.reached_scan_cap or page.reached_scan_cap
        self.loading_state = LoadingState.IDLE
        self.pending_load = None
        self.apply_filter()

    def apply_filter(self) -> None:
        if self.query:
            self.filtered_rows = [row for row in self.rows if row.matches_query(self.query)]
        else:
            self.filtered_rows = list(self.rows)
        if not self.filtered_rows:
            self.selected = 0
            self.scroll_top = 0
        else:
            self.selected = min(self.selected, len(self.filtered_rows) - 1)
            self.ensure_selected_visible()

    def row_matches_filter(self, row: Row) -> bool:
        return not self.query or row.matches_query(self.query)

    def set_query(self, query: str) -> None:
        self.query = query
        self.selected = 0
        self.scroll_top = 0
        self.apply_filter()
        self.continue_search_if_needed()

    def clear_query_preserving_selection(self) -> None:
        selected_key = None
        if self.filtered_rows:
            selected_key = self.filtered_rows[self.selected].seen_key()
        self.query = ""
        self.apply_filter()
        if selected_key is not None:
            for index, row in enumerate(self.filtered_rows):
                if row.seen_key() == selected_key:
                    self.selected = index
                    self.scroll_top = index
                    self.ensure_selected_visible()
                    break
        self.ensure_selected_visible()

    def continue_search_if_needed(self) -> None:
        if self.query and not self.filtered_rows and self.pagination.next_cursor and not self.pagination.reached_scan_cap:
            token = self.allocate_search_token()
            self.search_state = SearchState(token, True)
            self._request_page(self.pagination.next_cursor, token)
        else:
            self.search_state = SearchState(None, False)

    def continue_search_if_token_matches(self, token: Optional[int]) -> None:
        if self.search_state.token == token:
            self.continue_search_if_needed()

    def load_more_if_needed(self, trigger: LoadTrigger = LoadTrigger.SCROLL) -> None:
        if self.loading_state is LoadingState.LOADING:
            return
        if self.pagination.reached_scan_cap:
            return
        if trigger is not LoadTrigger.INITIAL and self.pagination.next_cursor is None:
            return
        self._request_page(self.pagination.next_cursor, self.search_state.token)

    def _request_page(self, cursor: Optional[PageCursor], search_token: Optional[int]) -> None:
        token = self.allocate_request_token()
        request = PageLoadRequest(
            cursor=cursor,
            request_token=token,
            search_token=search_token,
            cwd_filter=self.active_cwd_filter(),
            provider_filter=self.provider_filter,
            sort_key=self.sort_key,
        )
        self.pending_load = PendingLoad(token, search_token)
        self.loading_state = LoadingState.LOADING
        self.picker_loader(PickerLoadRequest.page(request))

    async def handle_background_event(self, event: BackgroundEvent) -> None:
        if event.kind == "Page":
            payload = event.payload
            if self.pending_load and payload["request_token"] != self.pending_load.request_token:
                return
            page = payload["page"]
            if isinstance(page, Exception):
                self.loading_state = LoadingState.ERROR
                return
            self.ingest_page(page)
            self.continue_search_if_token_matches(payload.get("search_token"))
        elif event.kind == "Preview":
            self.preview_state.previews[event.payload["thread_id"]] = event.payload["preview"]
        elif event.kind == "Transcript":
            was_drawn = (
                self.transcript_state.thread_id == event.payload["thread_id"]
                and self.transcript_state.loading_frame_drawn
            )
            self.transcript_state = SessionTranscriptState(event.payload["thread_id"], event.payload["transcript"], was_drawn)

    def handle_paste(self, pasted: str) -> None:
        normalized = normalize_pasted_query(pasted)
        if normalized is None:
            return
        query = normalized if not self.query else self.query + " " + normalized
        self.set_query(query)

    async def handle_key(self, key: Any) -> Optional[SessionSelection]:
        code = _key_code(key)
        if self.is_transcript_loading():
            return self.handle_transcript_loading_key(code)
        if code == "esc":
            if self.query:
                self.clear_query_preserving_selection()
                return None
            return SessionSelection.start_fresh()
        if code in ("ctrl-c", "ctrl-d"):
            return SessionSelection.exit()
        if code == "enter":
            return self._selected_selection()
        if code == "backspace":
            if self.query:
                self.set_query(self.query[:-1])
            return None
        if code in ("tab", "ctrl-i"):
            self.focus_next_toolbar_control()
        elif code in ("backtab", "shift-tab"):
            self.focus_previous_toolbar_control()
        elif code in ("right", "ctrl-l"):
            self.change_focused_toolbar_value()
        elif code == "left":
            self.change_focused_toolbar_value()
        if code in ("down", "j"):
            self.selected = min(self.selected + 1, max(0, len(self.filtered_rows) - 1))
            self.ensure_selected_visible()
            self.maybe_load_more_for_scroll()
        elif code in ("up", "k"):
            self.selected = max(0, self.selected - 1)
            self.ensure_selected_visible()
        elif code == "home":
            self.selected = 0
            self.ensure_selected_visible()
        elif code == "end":
            self.selected = max(0, len(self.filtered_rows) - 1)
            self.ensure_selected_visible()
            self.load_more_if_needed(LoadTrigger.SCROLL)
        elif code == "ctrl-o":
            await self.toggle_density()
        elif code == "ctrl-e":
            self.toggle_selected_expansion()
        elif len(code) == 1:
            self.set_query(self.query + code)
        return None

    def _selected_selection(self) -> Optional[SessionSelection]:
        if not self.filtered_rows:
            return None
        row = self.filtered_rows[self.selected]
        if row.thread_id is None:
            row.error = "Unable to resolve thread id for this session."
            return None
        return self.action.selection(row.path, row.thread_id)

    def ensure_selected_visible(self) -> None:
        if self.viewport_rows <= 0:
            self.scroll_top = self.selected
            return
        if self.selected < self.scroll_top:
            self.scroll_top = self.selected
        elif self.selected + 1 >= self.scroll_top + self.viewport_rows and self.scroll_top < self.selected:
            self.scroll_top = self.selected - self.viewport_rows + 1

    def ensure_minimum_rows_for_view(self, rows: int) -> None:
        if len(self.filtered_rows) < rows and self.pagination.next_cursor:
            self.load_more_if_needed(LoadTrigger.SCROLL)

    def update_viewport(self, rows: int, width: int) -> None:
        self.viewport_rows = max(0, rows)
        self.viewport_width = max(0, width)
        self.ensure_selected_visible()

    def maybe_load_more_for_scroll(self) -> None:
        if self.pagination.next_cursor and len(self.filtered_rows) - self.selected <= LOAD_NEAR_THRESHOLD:
            self.load_more_if_needed(LoadTrigger.SCROLL)

    def complete_pending_page_down(self) -> None:
        self.ensure_selected_visible()

    def active_cwd_filter(self) -> Optional[Any]:
        return self.filter_cwd if self.filter_mode is SessionFilterMode.CWD else None

    def toggle_sort_key(self) -> None:
        self.sort_key = "CreatedAt" if sort_key_label(self.sort_key) == "Updated" else "UpdatedAt"
        self.reset_pagination()
        self.load_more_if_needed(LoadTrigger.INITIAL)

    def toggle_filter_mode(self) -> None:
        self.filter_mode = self.filter_mode.toggle(self.filter_cwd)
        self.reset_pagination()
        self.load_more_if_needed(LoadTrigger.INITIAL)

    def focus_previous_toolbar_control(self) -> None:
        self.toolbar_control = getattr(self, "toolbar_control", ToolbarControl.FILTER).previous()

    def focus_next_toolbar_control(self) -> None:
        self.toolbar_control = getattr(self, "toolbar_control", ToolbarControl.FILTER).next()

    def change_focused_toolbar_value(self) -> None:
        if getattr(self, "toolbar_control", ToolbarControl.FILTER) is ToolbarControl.FILTER:
            self.toggle_filter_mode()
        else:
            self.toggle_sort_key()

    async def toggle_density(self) -> None:
        self.density = self.density.toggle()
        await self.persist_density()

    async def persist_density(self) -> None:
        persistence = self.view_persistence
        if persistence is not None and hasattr(persistence, "persist_density"):
            persistence.persist_density(self.density)

    def toggle_selected_expansion(self) -> None:
        if self.filtered_rows:
            self.filtered_rows[self.selected].expanded = not self.filtered_rows[self.selected].expanded

    def rendered_height_between(self, start: int, end: int) -> int:
        return max(0, end - start)

    def has_more_above(self) -> bool:
        return self.scroll_top > 0

    def has_more_below(self, viewport_height: int) -> bool:
        return self.scroll_top + viewport_height < len(self.filtered_rows) or self.pagination.next_cursor is not None

    def available_content_rows(self) -> int:
        return self.viewport_rows

    def row_separator_height(self) -> int:
        return 0 if self.density is SessionListDensity.DENSE else 1

    def is_transcript_loading(self) -> bool:
        return self.transcript_state.thread_id is not None and self.transcript_state.transcript is None

    def note_transcript_loading_frame_drawn(self) -> bool:
        if self.transcript_state.thread_id is not None and self.overlay is None:
            self.transcript_state.loading_frame_drawn = True
            return True
        return False

    def open_pending_transcript_if_ready(self) -> None:
        if self.transcript_state.loading_frame_drawn and self.transcript_state.transcript is not None:
            self.overlay = self.transcript_state.transcript

    def begin_transcript_loading(self, thread_id: str) -> None:
        self.transcript_state = SessionTranscriptState(thread_id, None, False)
        self.picker_loader(PickerLoadRequest.transcript(thread_id))

    def open_selected_transcript(self) -> None:
        if self.filtered_rows and self.filtered_rows[self.selected].thread_id:
            self.begin_transcript_loading(self.filtered_rows[self.selected].thread_id)

    def handle_overlay_event(self, tui: Any, event: Any) -> None:
        if _key_code(event) == "esc":
            self.overlay = None

    def handle_transcript_loading_key(self, key: Any) -> Optional[SessionSelection]:
        return SessionSelection.exit() if _key_code(key) == "ctrl-c" else None

    def freeze_footer_percent(self) -> None:
        self.footer_percent_frozen = picker_footer_percent(self)


def _get_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _key_code(key: Any) -> str:
    if isinstance(key, str):
        return key.lower()
    code = _get_attr(key, "code", key)
    if _get_attr(key, "modifiers", None):
        modifiers = _get_attr(key, "modifiers")
        if "control" in modifiers or "ctrl" in modifiers:
            char = _get_attr(key, "char", code)
            return "ctrl-" + str(char).lower()
    return str(code).lower()


def picker_footer_percent(state: PickerState) -> int:
    total = len(state.filtered_rows)
    if state.viewport_rows <= 0:
        return 100
    if total <= state.viewport_rows:
        return 100
    return picker_footer_scroll_percent(state.scroll_top, state.viewport_rows, total)


def picker_footer_scroll_percent(scroll_top: int, viewport_height: int, total_rows: int) -> int:
    if total_rows <= viewport_height:
        return 100
    denominator = max(1, total_rows - viewport_height)
    return min(100, max(0, round((scroll_top / denominator) * 100)))


def picker_footer_progress_label(state: PickerState) -> str:
    if state.loading_state is LoadingState.LOADING:
        return "Loading..."
    if not state.filtered_rows:
        return "No sessions"
    return f"{state.selected + 1}/{len(state.filtered_rows)} ({picker_footer_percent(state)}%)"


def spawn_app_server_page_loader(app_server: Any, include_non_interactive: bool, raw_reasoning_visibility: Any, bg_tx: Any) -> Any:
    def loader(request: PickerLoadRequest) -> None:
        if hasattr(app_server, "record_request"):
            app_server.record_request(request)
        if hasattr(bg_tx, "send"):
            bg_tx.send(request)

    return loader


async def load_app_server_page(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "load_app_server_page requires an app-server transport")


async def load_transcript_preview(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "load_transcript_preview requires an app-server transport")


@dataclass(frozen=True)
class TerminalResumeSelectionAction:
    """Selection event emitted by the bottom-pane resume compatibility view."""

    target: Any


@dataclass
class TerminalResumePopupController:
    """Project local resume targets through the canonical active-view stack."""

    app_runtime: Any

    def open_view(self) -> Any:
        from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams

        list_threads = getattr(self.app_runtime.active_thread_runtime, "list_resume_threads", None)
        rows = tuple(list_threads() if callable(list_threads) else ())
        items = []
        for row in rows:
            thread_id = str(_get_attr(row, "thread_id", ""))
            name = _get_attr(row, "thread_name", None) or _get_attr(row, "preview", None) or thread_id
            cwd = _get_attr(row, "cwd", None)
            items.append(
                SelectionItem(
                    name=str(name),
                    description=f"{thread_id}  {cwd}" if cwd is not None else thread_id,
                    search_value=" ".join(filter(None, (str(name), thread_id, str(cwd or "")))),
                    actions=[TerminalResumeSelectionAction(row)],
                    dismiss_on_select=True,
                )
            )
        if not items:
            items.append(
                SelectionItem(
                    name="No resumable sessions",
                    description="No local rollout sessions were found.",
                    is_disabled=True,
                )
            )
        return SelectionViewParams(
            view_id="resume-session-picker",
            title="Resume a previous session",
            subtitle="Select a local session to restore its history.",
            items=items,
            is_searchable=True,
            search_placeholder="Search sessions",
        )

    def handle_events(self, events: Tuple[object, ...]) -> Any:
        from ..bottom_pane.view_stack import TerminalSelectionTransition

        for event in events:
            if not isinstance(event, TerminalResumeSelectionAction):
                continue

            def apply(target: Any = event.target) -> None:
                try:
                    thread_id = self.app_runtime.resume_session_target(target)
                    self.app_runtime.insert_info_history_message(f"Resumed session {thread_id}.")
                except Exception as exc:
                    self.app_runtime.chat_widget.add_error_message(f"Failed to resume session: {exc}")

            return TerminalSelectionTransition(after_pop=apply)
        return None


__all__.extend(["TerminalResumePopupController", "TerminalResumeSelectionAction"])
