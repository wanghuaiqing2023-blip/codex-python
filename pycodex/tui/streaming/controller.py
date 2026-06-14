"""Python interface scaffold for Rust ``codex-tui::streaming::controller``.

Upstream source: ``codex/codex-rs/tui/src/streaming/controller.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="streaming::controller", source="codex/codex-rs/tui/src/streaming/controller.rs")

@dataclass
class StreamCore:
    """Python boundary for Rust ``streaming::controller::StreamCore``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.new")

    def push_delta(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.push_delta")

    def finalize_remaining(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.finalize_remaining")

    def tick(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.tick")

    def tick_batch(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.tick_batch")

    def is_idle(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.is_idle")

    def queued_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.queued_lines")

    def oldest_queued_age(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.oldest_queued_age")

    def current_tail_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.current_tail_lines")

    def has_tail(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.has_tail")

    def set_width(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.set_width")

    def reset(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.reset")

    def render_source(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.render_source")

    def recompute_streaming_render(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.recompute_streaming_render")

    def set_render_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.set_render_mode")

    def compute_target_stable_len(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.compute_target_stable_len")

    def sync_stable_queue(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.sync_stable_queue")

    def rebuild_stable_queue_from_render(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.rebuild_stable_queue_from_render")

    def active_tail_budget_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.active_tail_budget_lines")

    def tail_budget_from_source_start(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.tail_budget_from_source_start")

    def stable_prefix_len_for_source_start(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamCore.stable_prefix_len_for_source_start")

@dataclass
class StablePrefixLenCache:
    """Python boundary for Rust ``streaming::controller::StablePrefixLenCache``."""
    _payload: Any = None

@dataclass
class StreamController:
    """Python boundary for Rust ``streaming::controller::StreamController``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.new")

    def push(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.push")

    def finalize(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.finalize")

    def on_commit_tick(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.on_commit_tick")

    def on_commit_tick_batch(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.on_commit_tick_batch")

    def queued_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.queued_lines")

    def oldest_queued_age(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.oldest_queued_age")

    def current_tail_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.current_tail_lines")

    def tail_starts_stream(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.tail_starts_stream")

    def has_live_tail(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.has_live_tail")

    def clear_queue(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.clear_queue")

    def set_width(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.set_width")

    def set_render_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.set_render_mode")

    def emit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "StreamController.emit")

@dataclass
class PlanStreamController:
    """Python boundary for Rust ``streaming::controller::PlanStreamController``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.new")

    def push(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.push")

    def finalize(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.finalize")

    def on_commit_tick(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.on_commit_tick")

    def on_commit_tick_batch(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.on_commit_tick_batch")

    def queued_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.queued_lines")

    def has_live_tail(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.has_live_tail")

    def current_tail_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.current_tail_lines")

    def tail_starts_stream(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.tail_starts_stream")

    def current_tail_display_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.current_tail_display_lines")

    def oldest_queued_age(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.oldest_queued_age")

    def clear_queue(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.clear_queue")

    def set_width(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.set_width")

    def set_render_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.set_render_mode")

    def emit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.emit")

    def render_display_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "PlanStreamController.render_display_lines")

def test_cwd(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::test_cwd``."""
    return not_ported(RUST_MODULE, "test_cwd")

def stream_controller(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::stream_controller``."""
    return not_ported(RUST_MODULE, "stream_controller")

def plan_stream_controller(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_stream_controller``."""
    return not_ported(RUST_MODULE, "plan_stream_controller")

def lines_to_plain_strings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::lines_to_plain_strings``."""
    return not_ported(RUST_MODULE, "lines_to_plain_strings")

def hyperlink_lines_to_plain_strings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::hyperlink_lines_to_plain_strings``."""
    return not_ported(RUST_MODULE, "hyperlink_lines_to_plain_strings")

def collect_streamed_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::collect_streamed_lines``."""
    return not_ported(RUST_MODULE, "collect_streamed_lines")

def collect_plan_streamed_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::collect_plan_streamed_lines``."""
    return not_ported(RUST_MODULE, "collect_plan_streamed_lines")

def controller_set_width_rebuilds_queued_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_rebuilds_queued_lines``."""
    return not_ported(RUST_MODULE, "controller_set_width_rebuilds_queued_lines")

def controller_set_width_no_duplicate_after_emit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_no_duplicate_after_emit``."""
    return not_ported(RUST_MODULE, "controller_set_width_no_duplicate_after_emit")

def controller_tick_batch_zero_is_noop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_tick_batch_zero_is_noop``."""
    return not_ported(RUST_MODULE, "controller_tick_batch_zero_is_noop")

def controller_has_live_tail_reflects_tail_presence(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_has_live_tail_reflects_tail_presence``."""
    return not_ported(RUST_MODULE, "controller_has_live_tail_reflects_tail_presence")

def plan_controller_has_live_tail_reflects_tail_presence(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_controller_has_live_tail_reflects_tail_presence``."""
    return not_ported(RUST_MODULE, "plan_controller_has_live_tail_reflects_tail_presence")

def controller_live_tail_keeps_uncommitted_table_cell_newline_gated(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_live_tail_keeps_uncommitted_table_cell_newline_gated``."""
    return not_ported(RUST_MODULE, "controller_live_tail_keeps_uncommitted_table_cell_newline_gated")

def controller_live_tail_requires_table_holdback_state(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_live_tail_requires_table_holdback_state``."""
    return not_ported(RUST_MODULE, "controller_live_tail_requires_table_holdback_state")

def controller_live_tail_rerenders_table_tail_after_resize(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_live_tail_rerenders_table_tail_after_resize``."""
    return not_ported(RUST_MODULE, "controller_live_tail_rerenders_table_tail_after_resize")

def controller_set_width_partial_drain_no_lost_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_partial_drain_no_lost_lines``."""
    return not_ported(RUST_MODULE, "controller_set_width_partial_drain_no_lost_lines")

def controller_set_width_partial_drain_keeps_pending_queue(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_partial_drain_keeps_pending_queue``."""
    return not_ported(RUST_MODULE, "controller_set_width_partial_drain_keeps_pending_queue")

def controller_set_width_preserves_in_flight_tail(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_preserves_in_flight_tail``."""
    return not_ported(RUST_MODULE, "controller_set_width_preserves_in_flight_tail")

def controller_set_width_preserves_table_tail_when_queue_is_empty(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_preserves_table_tail_when_queue_is_empty``."""
    return not_ported(RUST_MODULE, "controller_set_width_preserves_table_tail_when_queue_is_empty")

def plan_controller_set_width_preserves_in_flight_tail(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_controller_set_width_preserves_in_flight_tail``."""
    return not_ported(RUST_MODULE, "plan_controller_set_width_preserves_in_flight_tail")

def plan_controller_holds_table_header_as_live_tail(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_controller_holds_table_header_as_live_tail``."""
    return not_ported(RUST_MODULE, "plan_controller_holds_table_header_as_live_tail")

def controller_loose_vs_tight_with_commit_ticks_matches_full(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_loose_vs_tight_with_commit_ticks_matches_full``."""
    return not_ported(RUST_MODULE, "controller_loose_vs_tight_with_commit_ticks_matches_full")

def controller_streamed_table_matches_full_render_widths(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_streamed_table_matches_full_render_widths``."""
    return not_ported(RUST_MODULE, "controller_streamed_table_matches_full_render_widths")

def controller_holds_blockquoted_table_tail_until_stable(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_holds_blockquoted_table_tail_until_stable``."""
    return not_ported(RUST_MODULE, "controller_holds_blockquoted_table_tail_until_stable")

def controller_keeps_pre_table_lines_queued_when_table_is_confirmed(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_keeps_pre_table_lines_queued_when_table_is_confirmed``."""
    return not_ported(RUST_MODULE, "controller_keeps_pre_table_lines_queued_when_table_is_confirmed")

def controller_set_width_during_confirmed_table_stream_matches_finalize_render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_during_confirmed_table_stream_matches_finalize_render``."""
    return not_ported(RUST_MODULE, "controller_set_width_during_confirmed_table_stream_matches_finalize_render")

def controller_does_not_hold_back_pipe_prose_without_table_delimiter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_does_not_hold_back_pipe_prose_without_table_delimiter``."""
    return not_ported(RUST_MODULE, "controller_does_not_hold_back_pipe_prose_without_table_delimiter")

def controller_does_not_stall_repeated_pipe_prose_paragraphs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_does_not_stall_repeated_pipe_prose_paragraphs``."""
    return not_ported(RUST_MODULE, "controller_does_not_stall_repeated_pipe_prose_paragraphs")

def controller_handles_table_immediately_after_heading(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_handles_table_immediately_after_heading``."""
    return not_ported(RUST_MODULE, "controller_handles_table_immediately_after_heading")

def controller_renders_separators_for_multi_table_response_shape(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_renders_separators_for_multi_table_response_shape``."""
    return not_ported(RUST_MODULE, "controller_renders_separators_for_multi_table_response_shape")

def controller_renders_separators_for_no_outer_pipes_table_shape(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_renders_separators_for_no_outer_pipes_table_shape``."""
    return not_ported(RUST_MODULE, "controller_renders_separators_for_no_outer_pipes_table_shape")

def controller_stabilizes_first_no_outer_pipes_table_in_response(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_stabilizes_first_no_outer_pipes_table_in_response``."""
    return not_ported(RUST_MODULE, "controller_stabilizes_first_no_outer_pipes_table_in_response")

def controller_stabilizes_two_column_no_outer_table_in_response(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_stabilizes_two_column_no_outer_table_in_response``."""
    return not_ported(RUST_MODULE, "controller_stabilizes_two_column_no_outer_table_in_response")

def controller_converts_no_outer_table_between_preboxed_sections(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_converts_no_outer_table_between_preboxed_sections``."""
    return not_ported(RUST_MODULE, "controller_converts_no_outer_table_between_preboxed_sections")

def controller_keeps_markdown_fenced_tables_mutable_until_finalize(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_keeps_markdown_fenced_tables_mutable_until_finalize``."""
    return not_ported(RUST_MODULE, "controller_keeps_markdown_fenced_tables_mutable_until_finalize")

def controller_keeps_markdown_fenced_no_outer_tables_mutable_until_finalize(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_keeps_markdown_fenced_no_outer_tables_mutable_until_finalize``."""
    return not_ported(RUST_MODULE, "controller_keeps_markdown_fenced_no_outer_tables_mutable_until_finalize")

def controller_live_view_matches_render_during_interleaved_table_streaming(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_live_view_matches_render_during_interleaved_table_streaming``."""
    return not_ported(RUST_MODULE, "controller_live_view_matches_render_during_interleaved_table_streaming")

def finalized_stream_table_preserves_semantic_url_fragments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::finalized_stream_table_preserves_semantic_url_fragments``."""
    return not_ported(RUST_MODULE, "finalized_stream_table_preserves_semantic_url_fragments")

def controller_keeps_non_markdown_fenced_tables_as_code(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_keeps_non_markdown_fenced_tables_as_code``."""
    return not_ported(RUST_MODULE, "controller_keeps_non_markdown_fenced_tables_as_code")

def plan_controller_streamed_table_matches_final_render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_controller_streamed_table_matches_final_render``."""
    return not_ported(RUST_MODULE, "plan_controller_streamed_table_matches_final_render")

def finalized_plan_stream_preserves_semantic_url_fragments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::finalized_plan_stream_preserves_semantic_url_fragments``."""
    return not_ported(RUST_MODULE, "finalized_plan_stream_preserves_semantic_url_fragments")

def plan_controller_streamed_markdown_fenced_table_matches_final_render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::plan_controller_streamed_markdown_fenced_table_matches_final_render``."""
    return not_ported(RUST_MODULE, "plan_controller_streamed_markdown_fenced_table_matches_final_render")

def table_holdback_state_detects_header_plus_delimiter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::table_holdback_state_detects_header_plus_delimiter``."""
    return not_ported(RUST_MODULE, "table_holdback_state_detects_header_plus_delimiter")

def table_holdback_state_detects_single_column_header_plus_delimiter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::table_holdback_state_detects_single_column_header_plus_delimiter``."""
    return not_ported(RUST_MODULE, "table_holdback_state_detects_single_column_header_plus_delimiter")

def table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence``."""
    return not_ported(RUST_MODULE, "table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence")

def table_holdback_state_treats_indented_fence_text_as_plain_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::table_holdback_state_treats_indented_fence_text_as_plain_content``."""
    return not_ported(RUST_MODULE, "table_holdback_state_treats_indented_fence_text_as_plain_content")

def table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence``."""
    return not_ported(RUST_MODULE, "table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence")

def incremental_holdback_matches_stateless_scan_per_chunk(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::incremental_holdback_matches_stateless_scan_per_chunk``."""
    return not_ported(RUST_MODULE, "incremental_holdback_matches_stateless_scan_per_chunk")

def incremental_holdback_detects_header_delimiter_across_chunk_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::incremental_holdback_detects_header_delimiter_across_chunk_boundary``."""
    return not_ported(RUST_MODULE, "incremental_holdback_detects_header_delimiter_across_chunk_boundary")

def controller_set_width_after_first_line_emit_does_not_requeue_first_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_after_first_line_emit_does_not_requeue_first_line``."""
    return not_ported(RUST_MODULE, "controller_set_width_after_first_line_emit_does_not_requeue_first_line")

def controller_set_width_partial_wrapped_emit_preserves_remaining_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_partial_wrapped_emit_preserves_remaining_content``."""
    return not_ported(RUST_MODULE, "controller_set_width_partial_wrapped_emit_preserves_remaining_content")

def controller_set_width_partial_wrapped_emit_keeps_wrapped_remainder(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``streaming::controller::controller_set_width_partial_wrapped_emit_keeps_wrapped_remainder``."""
    return not_ported(RUST_MODULE, "controller_set_width_partial_wrapped_emit_keeps_wrapped_remainder")

__all__ = [
    "PlanStreamController",
    "RUST_MODULE",
    "StablePrefixLenCache",
    "StreamController",
    "StreamCore",
    "collect_plan_streamed_lines",
    "collect_streamed_lines",
    "controller_converts_no_outer_table_between_preboxed_sections",
    "controller_does_not_hold_back_pipe_prose_without_table_delimiter",
    "controller_does_not_stall_repeated_pipe_prose_paragraphs",
    "controller_handles_table_immediately_after_heading",
    "controller_has_live_tail_reflects_tail_presence",
    "controller_holds_blockquoted_table_tail_until_stable",
    "controller_keeps_markdown_fenced_no_outer_tables_mutable_until_finalize",
    "controller_keeps_markdown_fenced_tables_mutable_until_finalize",
    "controller_keeps_non_markdown_fenced_tables_as_code",
    "controller_keeps_pre_table_lines_queued_when_table_is_confirmed",
    "controller_live_tail_keeps_uncommitted_table_cell_newline_gated",
    "controller_live_tail_requires_table_holdback_state",
    "controller_live_tail_rerenders_table_tail_after_resize",
    "controller_live_view_matches_render_during_interleaved_table_streaming",
    "controller_loose_vs_tight_with_commit_ticks_matches_full",
    "controller_renders_separators_for_multi_table_response_shape",
    "controller_renders_separators_for_no_outer_pipes_table_shape",
    "controller_set_width_after_first_line_emit_does_not_requeue_first_line",
    "controller_set_width_during_confirmed_table_stream_matches_finalize_render",
    "controller_set_width_no_duplicate_after_emit",
    "controller_set_width_partial_drain_keeps_pending_queue",
    "controller_set_width_partial_drain_no_lost_lines",
    "controller_set_width_partial_wrapped_emit_keeps_wrapped_remainder",
    "controller_set_width_partial_wrapped_emit_preserves_remaining_content",
    "controller_set_width_preserves_in_flight_tail",
    "controller_set_width_preserves_table_tail_when_queue_is_empty",
    "controller_set_width_rebuilds_queued_lines",
    "controller_stabilizes_first_no_outer_pipes_table_in_response",
    "controller_stabilizes_two_column_no_outer_table_in_response",
    "controller_streamed_table_matches_full_render_widths",
    "controller_tick_batch_zero_is_noop",
    "finalized_plan_stream_preserves_semantic_url_fragments",
    "finalized_stream_table_preserves_semantic_url_fragments",
    "hyperlink_lines_to_plain_strings",
    "incremental_holdback_detects_header_delimiter_across_chunk_boundary",
    "incremental_holdback_matches_stateless_scan_per_chunk",
    "lines_to_plain_strings",
    "plan_controller_has_live_tail_reflects_tail_presence",
    "plan_controller_holds_table_header_as_live_tail",
    "plan_controller_set_width_preserves_in_flight_tail",
    "plan_controller_streamed_markdown_fenced_table_matches_final_render",
    "plan_controller_streamed_table_matches_final_render",
    "plan_stream_controller",
    "stream_controller",
    "table_holdback_state_detects_header_plus_delimiter",
    "table_holdback_state_detects_single_column_header_plus_delimiter",
    "table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence",
    "table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence",
    "table_holdback_state_treats_indented_fence_text_as_plain_content",
    "test_cwd",
]
