"""Python interface scaffold for Rust ``codex-tui::chatwidget``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget", source="codex/codex-rs/tui/src/chatwidget.rs")

DEFAULT_MODEL_DISPLAY_NAME: Any = None

MULTI_AGENT_ENABLE_TITLE: Any = None

MULTI_AGENT_ENABLE_YES: Any = None

MULTI_AGENT_ENABLE_NO: Any = None

MULTI_AGENT_ENABLE_NOTICE: Any = None

TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING: Any = None

MEMORIES_DOC_URL: Any = None

MEMORIES_ENABLE_TITLE: Any = None

MEMORIES_ENABLE_YES: Any = None

MEMORIES_ENABLE_NO: Any = None

MEMORIES_ENABLE_NOTICE: Any = None

PLAN_MODE_REASONING_SCOPE_TITLE: Any = None

PLAN_MODE_REASONING_SCOPE_PLAN_ONLY: Any = None

PLAN_MODE_REASONING_SCOPE_ALL_MODES: Any = None

CONNECTORS_SELECTION_VIEW_ID: Any = None

PET_SELECTION_LOADING_VIEW_ID: Any = None

AMBIENT_PET_WRAP_GAP_COLUMNS: Any = None

TUI_STUB_MESSAGE: Any = None

def queued_message_edit_binding_for_terminal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::queued_message_edit_binding_for_terminal``."""
    return not_ported(RUST_MODULE, "queued_message_edit_binding_for_terminal")

def queued_message_edit_hint_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::queued_message_edit_hint_binding``."""
    return not_ported(RUST_MODULE, "queued_message_edit_hint_binding")

USER_SHELL_COMMAND_HELP_TITLE: Any = None

USER_SHELL_COMMAND_HELP_HINT: Any = None

AUTO_REVIEW_DESCRIPTION: Any = None

DEFAULT_OPENAI_BASE_URL: Any = None

DEFAULT_STATUS_LINE_ITEMS: Any = None

MAX_AGENT_COPY_HISTORY: Any = None

@dataclass
class ChatWidgetInit:
    """Python boundary for Rust ``chatwidget::ChatWidgetInit``."""
    _payload: Any = None

class ExternalEditorState(Enum):
    """Python boundary for Rust enum ``chatwidget::ExternalEditorState``."""
    UNPORTED = "unported"

@dataclass
class ChatWidget:
    """Python boundary for Rust ``chatwidget::ChatWidget``."""
    _payload: Any = None

    def set_collab_agent_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_collab_agent_metadata")

    def collab_agent_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.collab_agent_metadata")

    def realtime_conversation_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.realtime_conversation_enabled")

    def realtime_audio_device_selection_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.realtime_audio_device_selection_enabled")

    def restore_retry_status_header_if_present(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.restore_retry_status_header_if_present")

    def record_agent_markdown(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.record_agent_markdown")

    def record_visible_user_turn_for_copy(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.record_visible_user_turn_for_copy")

    def open_feedback_note(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_feedback_note")

    def show_feedback_note(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.show_feedback_note")

    def open_app_link_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_app_link_view")

    def dismiss_app_server_request(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.dismiss_app_server_request")

    def open_feedback_consent(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_feedback_consent")

    def open_multi_agent_enable_prompt(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_multi_agent_enable_prompt")

    def open_memories_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_memories_popup")

    def open_memories_enable_prompt(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.open_memories_enable_prompt")

    def set_memory_settings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_memory_settings")

    def set_token_info(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_token_info")

    def apply_token_info(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.apply_token_info")

    def context_remaining_percent(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.context_remaining_percent")

    def context_used_tokens(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.context_used_tokens")

    def restore_pre_review_token_info(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.restore_pre_review_token_info")

    def handle_history_entry_response(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.handle_history_entry_response")

    def pre_draw_tick(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.pre_draw_tick")

    def flush_active_cell(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.flush_active_cell")

    def add_to_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_to_history")

    def add_boxed_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_boxed_history")

    def enter_review_mode_with_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.enter_review_mode_with_hint")

    def exit_review_mode_after_item(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.exit_review_mode_after_item")

    def on_committed_user_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_committed_user_message")

    def on_user_message_display(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_user_message_display")

    def request_immediate_exit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.request_immediate_exit")

    def request_quit_without_confirmation(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.request_quit_without_confirmation")

    def show_shutdown_in_progress(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.show_shutdown_in_progress")

    def request_redraw(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.request_redraw")

    def bump_active_cell_revision(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.bump_active_cell_revision")

    def finalize_active_cell_as_failed(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.finalize_active_cell_as_failed")

    def set_pending_thread_approvals(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_pending_thread_approvals")

    def clear_thread_rename_block(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.clear_thread_rename_block")

    def set_thread_rename_block_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_thread_rename_block_message")

    def set_interrupted_turn_notice_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_interrupted_turn_notice_mode")

    def add_diff_in_progress(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_diff_in_progress")

    def on_diff_complete(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_diff_complete")

    def add_debug_config_output(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_debug_config_output")

    def add_ps_output(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_ps_output")

    def clean_background_terminals(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.clean_background_terminals")

    def plugins_for_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.plugins_for_mentions")

    def placeholder_session_header_cell(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.placeholder_session_header_cell")

    def apply_session_info_cell(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.apply_session_info_cell")

    def add_info_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_info_message")

    def add_memories_enable_notice(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_memories_enable_notice")

    def add_plain_history_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_plain_history_lines")

    def add_warning_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_warning_message")

    def add_error_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_error_message")

    def add_app_server_stub_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_app_server_stub_message")

    def rename_confirmation_cell(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.rename_confirmation_cell")

    def add_mcp_output(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.add_mcp_output")

    def clear_mcp_inventory_loading(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.clear_mcp_inventory_loading")

    def apply_file_search_result(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.apply_file_search_result")

    def current_stream_width(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.current_stream_width")

    def raw_output_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.raw_output_mode")

    def history_render_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.history_render_mode")

    def set_raw_output_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_raw_output_mode")

    def raw_output_mode_notice(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.raw_output_mode_notice")

    def set_raw_output_mode_and_notify(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_raw_output_mode_and_notify")

    def toggle_raw_output_mode_and_notify(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.toggle_raw_output_mode_and_notify")

    def on_terminal_resize(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_terminal_resize")

    def has_active_agent_stream(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.has_active_agent_stream")

    def has_active_plan_stream(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.has_active_plan_stream")

    def is_plan_streaming_in_tui(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.is_plan_streaming_in_tui")

    def composer_is_empty(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.composer_is_empty")

    def is_task_running_for_test(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.is_task_running_for_test")

    def toggle_vim_mode_and_notify(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.toggle_vim_mode_and_notify")

    def is_normal_backtrack_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.is_normal_backtrack_mode")

    def should_handle_vim_insert_escape(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.should_handle_vim_insert_escape")

    def insert_str(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.insert_str")

    def set_composer_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_composer_text")

    def set_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.set_remote_image_urls")

    def take_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.take_remote_image_urls")

    def remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.remote_image_urls")

    def pending_thread_approvals(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.pending_thread_approvals")

    def has_active_view(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.has_active_view")

    def show_esc_backtrack_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.show_esc_backtrack_hint")

    def clear_esc_backtrack_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.clear_esc_backtrack_hint")

    def refresh_skills_for_current_cwd(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.refresh_skills_for_current_cwd")

    def submit_op(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.submit_op")

    def append_message_history_entry(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.append_message_history_entry")

    def prepare_local_op_submission(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.prepare_local_op_submission")

    def on_list_skills(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_list_skills")

    def refresh_plugin_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.refresh_plugin_mentions")

    def on_plugin_mentions_loaded(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.on_plugin_mentions_loaded")

    def sync_plugin_mentions_config(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.sync_plugin_mentions_config")

    def token_usage(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.token_usage")

    def thread_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.thread_id")

    def thread_name(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.thread_name")

    def rollout_path(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.rollout_path")

    def active_cell_transcript_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.active_cell_transcript_key")

    def active_cell_transcript_hyperlink_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.active_cell_transcript_hyperlink_lines")

    def active_cell_transcript_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.active_cell_transcript_lines")

    def config_ref(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.config_ref")

    def status_line_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.status_line_text")

    def clear_token_usage(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.clear_token_usage")

    def update_recording_meter_in_place(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.update_recording_meter_in_place")

    def remove_recording_meter_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatWidget.remove_recording_meter_placeholder")

class CodexOpTarget(Enum):
    """Python boundary for Rust enum ``chatwidget::CodexOpTarget``."""
    UNPORTED = "unported"

@dataclass
class ActiveCellTranscriptKey:
    """Python boundary for Rust ``chatwidget::ActiveCellTranscriptKey``."""
    _payload: Any = None

class InterruptedTurnNoticeMode(Enum):
    """Python boundary for Rust enum ``chatwidget::InterruptedTurnNoticeMode``."""
    UNPORTED = "unported"

class ReplayKind(Enum):
    """Python boundary for Rust enum ``chatwidget::ReplayKind``."""
    UNPORTED = "unported"

class SessionConfiguredDisplay(Enum):
    """Python boundary for Rust enum ``chatwidget::SessionConfiguredDisplay``."""
    UNPORTED = "unported"

class PlanModeNudgeScope(Enum):
    """Python boundary for Rust enum ``chatwidget::PlanModeNudgeScope``."""
    UNPORTED = "unported"

class TurnAbortReason(Enum):
    """Python boundary for Rust enum ``chatwidget::TurnAbortReason``."""
    UNPORTED = "unported"

def contains_plan_keyword(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::contains_plan_keyword``."""
    return not_ported(RUST_MODULE, "contains_plan_keyword")

class ThreadItemRenderSource(Enum):
    """Python boundary for Rust enum ``chatwidget::ThreadItemRenderSource``."""
    UNPORTED = "unported"

def exec_approval_request_from_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::exec_approval_request_from_params``."""
    return not_ported(RUST_MODULE, "exec_approval_request_from_params")

def patch_approval_request_from_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::patch_approval_request_from_params``."""
    return not_ported(RUST_MODULE, "patch_approval_request_from_params")

def request_permissions_from_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::request_permissions_from_params``."""
    return not_ported(RUST_MODULE, "request_permissions_from_params")

def token_usage_info_from_app_server(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::token_usage_info_from_app_server``."""
    return not_ported(RUST_MODULE, "token_usage_info_from_app_server")

def has_websocket_timing_metrics(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::has_websocket_timing_metrics``."""
    return not_ported(RUST_MODULE, "has_websocket_timing_metrics")

def drop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::drop``."""
    return not_ported(RUST_MODULE, "drop")

PLACEHOLDERS: Any = None

SIDE_PLACEHOLDERS: Any = None

def extract_first_bold(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::extract_first_bold``."""
    return not_ported(RUST_MODULE, "extract_first_bold")

__all__ = [
    "AMBIENT_PET_WRAP_GAP_COLUMNS",
    "AUTO_REVIEW_DESCRIPTION",
    "ActiveCellTranscriptKey",
    "CONNECTORS_SELECTION_VIEW_ID",
    "ChatWidget",
    "ChatWidgetInit",
    "CodexOpTarget",
    "DEFAULT_MODEL_DISPLAY_NAME",
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_STATUS_LINE_ITEMS",
    "ExternalEditorState",
    "InterruptedTurnNoticeMode",
    "MAX_AGENT_COPY_HISTORY",
    "MEMORIES_DOC_URL",
    "MEMORIES_ENABLE_NO",
    "MEMORIES_ENABLE_NOTICE",
    "MEMORIES_ENABLE_TITLE",
    "MEMORIES_ENABLE_YES",
    "MULTI_AGENT_ENABLE_NO",
    "MULTI_AGENT_ENABLE_NOTICE",
    "MULTI_AGENT_ENABLE_TITLE",
    "MULTI_AGENT_ENABLE_YES",
    "PET_SELECTION_LOADING_VIEW_ID",
    "PLACEHOLDERS",
    "PLAN_MODE_REASONING_SCOPE_ALL_MODES",
    "PLAN_MODE_REASONING_SCOPE_PLAN_ONLY",
    "PLAN_MODE_REASONING_SCOPE_TITLE",
    "PlanModeNudgeScope",
    "RUST_MODULE",
    "ReplayKind",
    "SIDE_PLACEHOLDERS",
    "SessionConfiguredDisplay",
    "TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING",
    "TUI_STUB_MESSAGE",
    "ThreadItemRenderSource",
    "TurnAbortReason",
    "USER_SHELL_COMMAND_HELP_HINT",
    "USER_SHELL_COMMAND_HELP_TITLE",
    "contains_plan_keyword",
    "drop",
    "exec_approval_request_from_params",
    "extract_first_bold",
    "has_websocket_timing_metrics",
    "patch_approval_request_from_params",
    "queued_message_edit_binding_for_terminal",
    "queued_message_edit_hint_binding",
    "request_permissions_from_params",
    "token_usage_info_from_app_server",
]
