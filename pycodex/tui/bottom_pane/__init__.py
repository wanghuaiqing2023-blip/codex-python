"""Python interface scaffold for Rust ``codex-tui::bottom_pane``.

Upstream source: ``codex/codex-rs/tui/src/bottom_pane/mod.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane", source="codex/codex-rs/tui/src/bottom_pane/mod.rs")

@dataclass
class LocalImageAttachment:
    """Python boundary for Rust ``bottom_pane::LocalImageAttachment``."""
    placeholder: str = ""
    path: Any = None

@dataclass
class MentionBinding:
    """Python boundary for Rust ``bottom_pane::MentionBinding``."""
    mention: str = ""
    path: str = ""

QUIT_SHORTCUT_TIMEOUT = timedelta(seconds=1)

APPROVAL_PROMPT_TYPING_IDLE_DELAY = timedelta(seconds=1)

DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED = False

class CancellationEvent(Enum):
    """Python boundary for Rust enum ``bottom_pane::CancellationEvent``."""
    HANDLED = "handled"
    NOT_HANDLED = "not_handled"

@dataclass
class DelayedApprovalRequest:
    """Python boundary for Rust ``bottom_pane::DelayedApprovalRequest``."""
    _payload: Any = None

@dataclass
class BottomPane:
    """Python boundary for Rust ``bottom_pane::BottomPane``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.new")

    def set_skills(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_skills")

    def set_image_paste_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_image_paste_enabled")

    def set_connectors_snapshot(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_connectors_snapshot")

    def set_plugin_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_plugin_mentions")

    def set_plugins_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_plugins_command_enabled")

    def set_mentions_v2_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_mentions_v2_enabled")

    def take_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.take_mention_bindings")

    def take_recent_submission_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.take_recent_submission_mention_bindings")

    def record_pending_slash_command_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.record_pending_slash_command_history")

    def set_keymap_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_keymap_bindings")

    def drain_pending_submission_state(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.drain_pending_submission_state")

    def set_collaboration_modes_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_collaboration_modes_enabled")

    def set_connectors_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_connectors_enabled")

    def set_windows_degraded_sandbox_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_windows_degraded_sandbox_active")

    def set_collaboration_mode_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_collaboration_mode_indicator")

    def set_goal_status_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_goal_status_indicator")

    def set_ide_context_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_ide_context_active")

    def set_personality_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_personality_command_enabled")

    def set_service_tier_commands_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_service_tier_commands_enabled")

    def set_service_tier_commands(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_service_tier_commands")

    def set_goal_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_goal_command_enabled")

    def set_realtime_conversation_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_realtime_conversation_enabled")

    def set_audio_device_selection_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_audio_device_selection_enabled")

    def set_side_conversation_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_side_conversation_active")

    def set_placeholder_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_placeholder_text")

    def set_queued_message_edit_binding(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_queued_message_edit_binding")

    def set_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_vim_enabled")

    def toggle_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.toggle_vim_enabled")

    def status_widget(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.status_widget")

    def skills(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.skills")

    def plugins(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.plugins")

    def context_window_percent(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.context_window_percent")

    def context_window_used_tokens(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.context_window_used_tokens")

    def active_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.active_view")

    def push_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.push_view")

    def pop_active_view_with_completion(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.pop_active_view_with_completion")

    def on_view_stack_depth_decreased(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.on_view_stack_depth_decreased")

    def approval_prompt_delay_remaining(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.approval_prompt_delay_remaining")

    def record_composer_activity_at(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.record_composer_activity_at")

    def maybe_show_delayed_approval_requests_at(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.maybe_show_delayed_approval_requests_at")

    def handle_key_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.handle_key_event")

    def on_ctrl_c(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.on_ctrl_c")

    def handle_paste(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.handle_paste")

    def insert_str(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.insert_str")

    def pre_draw_tick(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.pre_draw_tick")

    def pre_draw_tick_at(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.pre_draw_tick_at")

    def schedule_active_view_frame(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.schedule_active_view_frame")

    def set_composer_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_composer_text")

    def set_composer_text_with_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_composer_text_with_mention_bindings")

    def set_composer_input_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_composer_input_enabled")

    def show_shutdown_in_progress(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.show_shutdown_in_progress")

    def clear_composer_for_ctrl_c(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.clear_composer_for_ctrl_c")

    def composer_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_text")

    def composer_draft_snapshot(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_draft_snapshot")

    def composer_text_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_text_elements")

    def composer_local_images(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_local_images")

    def composer_local_image_paths(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_local_image_paths")

    def composer_text_with_pending(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_text_with_pending")

    def composer_input_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_input_enabled")

    def composer_pending_pastes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_pending_pastes")

    def apply_external_edit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.apply_external_edit")

    def set_footer_hint_override(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_footer_hint_override")

    def set_plan_mode_nudge_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_plan_mode_nudge_visible")

    def plan_mode_nudge_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.plan_mode_nudge_visible")

    def set_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_remote_image_urls")

    def remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.remote_image_urls")

    def take_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.take_remote_image_urls")

    def set_composer_pending_pastes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_composer_pending_pastes")

    def update_status(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.update_status")

    def show_quit_shortcut_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.show_quit_shortcut_hint")

    def clear_quit_shortcut_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.clear_quit_shortcut_hint")

    def quit_shortcut_hint_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.quit_shortcut_hint_visible")

    def status_indicator_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.status_indicator_visible")

    def status_line_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.status_line_text")

    def show_esc_backtrack_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.show_esc_backtrack_hint")

    def clear_esc_backtrack_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.clear_esc_backtrack_hint")

    def set_task_running(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_task_running")

    def set_queue_submissions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_queue_submissions")

    def hide_status_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.hide_status_indicator")

    def ensure_status_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.ensure_status_indicator")

    def set_interrupt_hint_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_interrupt_hint_visible")

    def set_context_window(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_context_window")

    def show_selection_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.show_selection_view")

    def apply_standard_popup_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.apply_standard_popup_hint")

    def replace_selection_view_if_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.replace_selection_view_if_active")

    def standard_popup_hint_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.standard_popup_hint_line")

    def list_keymap(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.list_keymap")

    def replace_active_views_with_selection_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.replace_active_views_with_selection_view")

    def selected_index_for_active_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.selected_index_for_active_view")

    def active_tab_id_for_active_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.active_tab_id_for_active_view")

    def dismiss_active_view_if_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.dismiss_active_view_if_id")

    def set_pending_input_preview(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_pending_input_preview")

    def set_pending_thread_approvals(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_pending_thread_approvals")

    def pending_thread_approvals(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.pending_thread_approvals")

    def set_unified_exec_processes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_unified_exec_processes")

    def sync_status_inline_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.sync_status_inline_message")

    def composer_is_empty(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_is_empty")

    def composer_is_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_is_vim_enabled")

    def composer_should_handle_vim_insert_escape(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.composer_should_handle_vim_insert_escape")

    def is_task_running(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.is_task_running")

    def terminal_title_requires_action(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.terminal_title_requires_action")

    def has_active_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.has_active_view")

    def active_view_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.active_view_id")

    def is_normal_backtrack_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.is_normal_backtrack_mode")

    def can_launch_external_editor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.can_launch_external_editor")

    def no_modal_or_popup_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.no_modal_or_popup_active")

    def show_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.show_view")

    def push_approval_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.push_approval_request")

    def push_user_input_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.push_user_input_request")

    def push_mcp_server_elicitation_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.push_mcp_server_elicitation_request")

    def dismiss_app_server_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.dismiss_app_server_request")

    def on_active_view_complete(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.on_active_view_complete")

    def pause_status_timer_for_modal(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.pause_status_timer_for_modal")

    def resume_status_timer_after_modal(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.resume_status_timer_after_modal")

    def request_redraw(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.request_redraw")

    def request_redraw_in(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.request_redraw_in")

    def set_history_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_history_metadata")

    def flush_paste_burst_if_due(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.flush_paste_burst_if_due")

    def is_in_paste_burst(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.is_in_paste_burst")

    def on_history_entry_response(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.on_history_entry_response")

    def on_file_search_result(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.on_file_search_result")

    def attach_image(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.attach_image")

    def take_recent_submission_images(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.take_recent_submission_images")

    def take_recent_submission_images_with_placeholders(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.take_recent_submission_images_with_placeholders")

    def prepare_inline_args_submission(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.prepare_inline_args_submission")

    def as_renderable(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.as_renderable")

    def as_renderable_with_composer_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.as_renderable_with_composer_right_reserve")

    def render_with_composer_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.render_with_composer_right_reserve")

    def desired_height_with_composer_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.desired_height_with_composer_right_reserve")

    def cursor_pos_with_composer_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.cursor_pos_with_composer_right_reserve")

    def cursor_style_with_composer_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.cursor_style_with_composer_right_reserve")

    def set_status_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_status_line")

    def set_status_line_hyperlink(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_status_line_hyperlink")

    def set_status_line_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_status_line_enabled")

    def set_active_agent_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_active_agent_label")

    def set_side_conversation_context_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.set_side_conversation_context_label")

    def insert_recording_meter_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.insert_recording_meter_placeholder")

    def update_recording_meter_in_place(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.update_recording_meter_in_place")

    def remove_recording_meter_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "BottomPane.remove_recording_meter_placeholder")

@dataclass
class BottomPaneParams:
    """Python boundary for Rust ``bottom_pane::BottomPaneParams``."""
    _payload: Any = None

@dataclass
class ChatComposerRightReserveRenderable:
    """Python boundary for Rust ``bottom_pane::ChatComposerRightReserveRenderable``."""
    _payload: Any = None

def render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::render``."""
    return not_ported(RUST_MODULE, "render")

def desired_height(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::desired_height``."""
    return not_ported(RUST_MODULE, "desired_height")

def cursor_pos(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::cursor_pos``."""
    return not_ported(RUST_MODULE, "cursor_pos")

def cursor_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::cursor_style``."""
    return not_ported(RUST_MODULE, "cursor_style")

def snapshot_buffer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::snapshot_buffer``."""
    return not_ported(RUST_MODULE, "snapshot_buffer")

def render_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::render_snapshot``."""
    return not_ported(RUST_MODULE, "render_snapshot")

def test_pane(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::test_pane``."""
    return not_ported(RUST_MODULE, "test_pane")

def test_pane_with_disable_paste_burst(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::test_pane_with_disable_paste_burst``."""
    return not_ported(RUST_MODULE, "test_pane_with_disable_paste_burst")

def exec_request(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::exec_request``."""
    return not_ported(RUST_MODULE, "exec_request")

@dataclass
class DismissibleView:
    """Python boundary for Rust ``bottom_pane::DismissibleView``."""
    _payload: Any = None

def is_complete(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::is_complete``."""
    return not_ported(RUST_MODULE, "is_complete")

def view_id(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::view_id``."""
    return not_ported(RUST_MODULE, "view_id")

def dismiss_app_server_request(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::dismiss_app_server_request``."""
    return not_ported(RUST_MODULE, "dismiss_app_server_request")

@dataclass
class CompletingView:
    """Python boundary for Rust ``bottom_pane::CompletingView``."""
    _payload: Any = None

def handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::handle_key_event``."""
    return not_ported(RUST_MODULE, "handle_key_event")

def ctrl_c_on_modal_consumes_without_showing_quit_hint(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::ctrl_c_on_modal_consumes_without_showing_quit_hint``."""
    return not_ported(RUST_MODULE, "ctrl_c_on_modal_consumes_without_showing_quit_hint")

def ctrl_c_cancels_history_search_without_clearing_draft_or_showing_quit_hint(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::ctrl_c_cancels_history_search_without_clearing_draft_or_showing_quit_hint``."""
    return not_ported(RUST_MODULE, "ctrl_c_cancels_history_search_without_clearing_draft_or_showing_quit_hint")

def overlay_not_shown_above_approval_modal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::overlay_not_shown_above_approval_modal``."""
    return not_ported(RUST_MODULE, "overlay_not_shown_above_approval_modal")

def approval_request_shows_immediately_without_recent_typing(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::approval_request_shows_immediately_without_recent_typing``."""
    return not_ported(RUST_MODULE, "approval_request_shows_immediately_without_recent_typing")

def approval_request_is_delayed_after_recent_typing(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::approval_request_is_delayed_after_recent_typing``."""
    return not_ported(RUST_MODULE, "approval_request_is_delayed_after_recent_typing")

def continued_typing_resets_delayed_approval_idle_deadline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::continued_typing_resets_delayed_approval_idle_deadline``."""
    return not_ported(RUST_MODULE, "continued_typing_resets_delayed_approval_idle_deadline")

def typed_approval_shortcuts_during_delay_stay_in_composer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::typed_approval_shortcuts_during_delay_stay_in_composer``."""
    return not_ported(RUST_MODULE, "typed_approval_shortcuts_during_delay_stay_in_composer")

def delayed_approval_shortcut_works_after_idle_deadline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::delayed_approval_shortcut_works_after_idle_deadline``."""
    return not_ported(RUST_MODULE, "delayed_approval_shortcut_works_after_idle_deadline")

def dismiss_app_server_request_prunes_delayed_approval(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::dismiss_app_server_request_prunes_delayed_approval``."""
    return not_ported(RUST_MODULE, "dismiss_app_server_request_prunes_delayed_approval")

def dismiss_app_server_request_removes_matching_buried_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::dismiss_app_server_request_removes_matching_buried_view``."""
    return not_ported(RUST_MODULE, "dismiss_app_server_request_removes_matching_buried_view")

def dismiss_app_server_request_returns_false_when_no_view_matches(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::dismiss_app_server_request_returns_false_when_no_view_matches``."""
    return not_ported(RUST_MODULE, "dismiss_app_server_request_returns_false_when_no_view_matches")

def completing_top_view_preserves_underlying_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::completing_top_view_preserves_underlying_view``."""
    return not_ported(RUST_MODULE, "completing_top_view_preserves_underlying_view")

def composer_shown_after_denied_while_task_running(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::composer_shown_after_denied_while_task_running``."""
    return not_ported(RUST_MODULE, "composer_shown_after_denied_while_task_running")

def status_indicator_visible_during_command_execution(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::status_indicator_visible_during_command_execution``."""
    return not_ported(RUST_MODULE, "status_indicator_visible_during_command_execution")

def status_and_composer_fill_height_without_bottom_padding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::status_and_composer_fill_height_without_bottom_padding``."""
    return not_ported(RUST_MODULE, "status_and_composer_fill_height_without_bottom_padding")

def status_only_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::status_only_snapshot``."""
    return not_ported(RUST_MODULE, "status_only_snapshot")

def unified_exec_summary_does_not_increase_height_when_status_visible(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::unified_exec_summary_does_not_increase_height_when_status_visible``."""
    return not_ported(RUST_MODULE, "unified_exec_summary_does_not_increase_height_when_status_visible")

def status_with_details_and_queued_messages_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::status_with_details_and_queued_messages_snapshot``."""
    return not_ported(RUST_MODULE, "status_with_details_and_queued_messages_snapshot")

def queued_messages_visible_when_status_hidden_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::queued_messages_visible_when_status_hidden_snapshot``."""
    return not_ported(RUST_MODULE, "queued_messages_visible_when_status_hidden_snapshot")

def status_and_queued_messages_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::status_and_queued_messages_snapshot``."""
    return not_ported(RUST_MODULE, "status_and_queued_messages_snapshot")

def remote_images_render_above_composer_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::remote_images_render_above_composer_text``."""
    return not_ported(RUST_MODULE, "remote_images_render_above_composer_text")

def drain_pending_submission_state_clears_remote_image_urls(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::drain_pending_submission_state_clears_remote_image_urls``."""
    return not_ported(RUST_MODULE, "drain_pending_submission_state_clears_remote_image_urls")

def esc_with_skill_popup_does_not_interrupt_task(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_with_skill_popup_does_not_interrupt_task``."""
    return not_ported(RUST_MODULE, "esc_with_skill_popup_does_not_interrupt_task")

def esc_with_slash_command_popup_does_not_interrupt_task(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_with_slash_command_popup_does_not_interrupt_task``."""
    return not_ported(RUST_MODULE, "esc_with_slash_command_popup_does_not_interrupt_task")

def esc_with_agent_command_without_popup_does_not_interrupt_task(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_with_agent_command_without_popup_does_not_interrupt_task``."""
    return not_ported(RUST_MODULE, "esc_with_agent_command_without_popup_does_not_interrupt_task")

def esc_release_after_dismissing_agent_picker_does_not_interrupt_task(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_release_after_dismissing_agent_picker_does_not_interrupt_task``."""
    return not_ported(RUST_MODULE, "esc_release_after_dismissing_agent_picker_does_not_interrupt_task")

def esc_interrupts_running_task_when_no_popup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_interrupts_running_task_when_no_popup``."""
    return not_ported(RUST_MODULE, "esc_interrupts_running_task_when_no_popup")

def remapped_interrupt_turn_uses_configured_key_including_agent_drafts(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::remapped_interrupt_turn_uses_configured_key_including_agent_drafts``."""
    return not_ported(RUST_MODULE, "remapped_interrupt_turn_uses_configured_key_including_agent_drafts")

def selection_view_esc_respects_remapped_list_cancel(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::selection_view_esc_respects_remapped_list_cancel``."""
    return not_ported(RUST_MODULE, "selection_view_esc_respects_remapped_list_cancel")

def esc_routes_to_handle_key_event_when_requested(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::esc_routes_to_handle_key_event_when_requested``."""
    return not_ported(RUST_MODULE, "esc_routes_to_handle_key_event_when_requested")

@dataclass
class EscRoutingView:
    """Python boundary for Rust ``bottom_pane::EscRoutingView``."""
    _payload: Any = None

def on_ctrl_c(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::on_ctrl_c``."""
    return not_ported(RUST_MODULE, "on_ctrl_c")

def prefer_esc_to_handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::prefer_esc_to_handle_key_event``."""
    return not_ported(RUST_MODULE, "prefer_esc_to_handle_key_event")

def release_events_are_ignored_for_active_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::release_events_are_ignored_for_active_view``."""
    return not_ported(RUST_MODULE, "release_events_are_ignored_for_active_view")

@dataclass
class CountingView:
    """Python boundary for Rust ``bottom_pane::CountingView``."""
    _payload: Any = None

def paste_completion_clears_stacked_views_and_restores_composer_input(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::paste_completion_clears_stacked_views_and_restores_composer_input``."""
    return not_ported(RUST_MODULE, "paste_completion_clears_stacked_views_and_restores_composer_input")

@dataclass
class BlockingView:
    """Python boundary for Rust ``bottom_pane::BlockingView``."""
    _payload: Any = None

@dataclass
class PasteCompletesView:
    """Python boundary for Rust ``bottom_pane::PasteCompletesView``."""
    _payload: Any = None

def handle_paste(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::handle_paste``."""
    return not_ported(RUST_MODULE, "handle_paste")

__all__ = [
    "APPROVAL_PROMPT_TYPING_IDLE_DELAY",
    "BlockingView",
    "BottomPane",
    "BottomPaneParams",
    "CancellationEvent",
    "ChatComposerRightReserveRenderable",
    "CompletingView",
    "CountingView",
    "DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED",
    "DelayedApprovalRequest",
    "DismissibleView",
    "EscRoutingView",
    "LocalImageAttachment",
    "MentionBinding",
    "PasteCompletesView",
    "QUIT_SHORTCUT_TIMEOUT",
    "RUST_MODULE",
    "approval_request_is_delayed_after_recent_typing",
    "approval_request_shows_immediately_without_recent_typing",
    "completing_top_view_preserves_underlying_view",
    "composer_shown_after_denied_while_task_running",
    "continued_typing_resets_delayed_approval_idle_deadline",
    "ctrl_c_cancels_history_search_without_clearing_draft_or_showing_quit_hint",
    "ctrl_c_on_modal_consumes_without_showing_quit_hint",
    "cursor_pos",
    "cursor_style",
    "delayed_approval_shortcut_works_after_idle_deadline",
    "desired_height",
    "dismiss_app_server_request",
    "dismiss_app_server_request_prunes_delayed_approval",
    "dismiss_app_server_request_removes_matching_buried_view",
    "dismiss_app_server_request_returns_false_when_no_view_matches",
    "drain_pending_submission_state_clears_remote_image_urls",
    "esc_interrupts_running_task_when_no_popup",
    "esc_release_after_dismissing_agent_picker_does_not_interrupt_task",
    "esc_routes_to_handle_key_event_when_requested",
    "esc_with_agent_command_without_popup_does_not_interrupt_task",
    "esc_with_skill_popup_does_not_interrupt_task",
    "esc_with_slash_command_popup_does_not_interrupt_task",
    "exec_request",
    "handle_key_event",
    "handle_paste",
    "is_complete",
    "on_ctrl_c",
    "overlay_not_shown_above_approval_modal",
    "paste_completion_clears_stacked_views_and_restores_composer_input",
    "prefer_esc_to_handle_key_event",
    "queued_messages_visible_when_status_hidden_snapshot",
    "release_events_are_ignored_for_active_view",
    "remapped_interrupt_turn_uses_configured_key_including_agent_drafts",
    "remote_images_render_above_composer_text",
    "render",
    "render_snapshot",
    "selection_view_esc_respects_remapped_list_cancel",
    "snapshot_buffer",
    "status_and_composer_fill_height_without_bottom_padding",
    "status_and_queued_messages_snapshot",
    "status_indicator_visible_during_command_execution",
    "status_only_snapshot",
    "status_with_details_and_queued_messages_snapshot",
    "test_pane",
    "test_pane_with_disable_paste_burst",
    "typed_approval_shortcuts_during_delay_stay_in_composer",
    "unified_exec_summary_does_not_increase_height_when_status_visible",
    "view_id",
]
