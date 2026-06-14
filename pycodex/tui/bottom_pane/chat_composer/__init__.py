"""Python interface scaffold for Rust ``codex-tui::bottom_pane::chat_composer``.

Upstream source: ``codex/codex-rs/tui/src/bottom_pane/chat_composer.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane::chat_composer", source="codex/codex-rs/tui/src/bottom_pane/chat_composer.rs")

LARGE_PASTE_CHAR_THRESHOLD: Any = None

def user_input_too_large_message(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::user_input_too_large_message``."""
    return not_ported(RUST_MODULE, "user_input_too_large_message")

class InputResult(Enum):
    """Python boundary for Rust enum ``bottom_pane::chat_composer::InputResult``."""
    UNPORTED = "unported"

class QueuedInputAction(Enum):
    """Python boundary for Rust enum ``bottom_pane::chat_composer::QueuedInputAction``."""
    UNPORTED = "unported"

@dataclass
class ChatComposerConfig:
    """Python boundary for Rust ``bottom_pane::chat_composer::ChatComposerConfig``."""
    _payload: Any = None

def default(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::default``."""
    return not_ported(RUST_MODULE, "default")

@dataclass
class ChatComposer:
    """Python boundary for Rust ``bottom_pane::chat_composer::ChatComposer``."""
    _payload: Any = None

    def slash_input(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.slash_input")

    def builtin_command_flags(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.builtin_command_flags")

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.new")

    def new_with_config(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.new_with_config")

    def next_id(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.next_id")

    def set_frame_requester(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_frame_requester")

    def set_skill_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_skill_mentions")

    def set_plugin_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_plugin_mentions")

    def set_plugins_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_plugins_command_enabled")

    def set_mentions_v2_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_mentions_v2_enabled")

    def set_image_paste_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_image_paste_enabled")

    def set_connector_mentions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_connector_mentions")

    def take_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.take_mention_bindings")

    def set_collaboration_modes_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_collaboration_modes_enabled")

    def set_connectors_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_connectors_enabled")

    def set_service_tier_commands_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_service_tier_commands_enabled")

    def set_service_tier_commands(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_service_tier_commands")

    def set_goal_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_goal_command_enabled")

    def set_keymap_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_keymap_bindings")

    def set_collaboration_mode_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_collaboration_mode_indicator")

    def set_goal_status_indicator(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_goal_status_indicator")

    def set_ide_context_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_ide_context_active")

    def set_personality_command_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_personality_command_enabled")

    def set_realtime_conversation_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_realtime_conversation_enabled")

    def set_audio_device_selection_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_audio_device_selection_enabled")

    def set_side_conversation_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_side_conversation_active")

    def set_steer_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_steer_enabled")

    def popups_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.popups_enabled")

    def slash_commands_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.slash_commands_enabled")

    def image_paste_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.image_paste_enabled")

    def set_windows_degraded_sandbox_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_windows_degraded_sandbox_active")

    def layout_areas(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.layout_areas")

    def layout_areas_with_textarea_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.layout_areas_with_textarea_right_reserve")

    def footer_spacing(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.footer_spacing")

    def cursor_pos(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.cursor_pos")

    def cursor_pos_with_textarea_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.cursor_pos_with_textarea_right_reserve")

    def is_empty(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.is_empty")

    def set_history_metadata(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_history_metadata")

    def on_history_entry_response(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.on_history_entry_response")

    def handle_paste(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_paste")

    def handle_paste_image_path(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_paste_image_path")

    def set_disable_paste_burst(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_disable_paste_burst")

    def apply_external_edit(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.apply_external_edit")

    def set_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_vim_enabled")

    def toggle_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.toggle_vim_enabled")

    def is_vim_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.is_vim_enabled")

    def should_handle_vim_insert_escape(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.should_handle_vim_insert_escape")

    def vim_mode_indicator_span(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.vim_mode_indicator_span")

    def mode_indicator_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.mode_indicator_line")

    def right_footer_line_with_context(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.right_footer_line_with_context")

    def current_text_with_pending(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_text_with_pending")

    def input_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.input_enabled")

    def pending_pastes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.pending_pastes")

    def set_pending_pastes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_pending_pastes")

    def set_footer_hint_override(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_footer_hint_override")

    def set_plan_mode_nudge_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_plan_mode_nudge_visible")

    def plan_mode_nudge_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.plan_mode_nudge_visible")

    def set_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_remote_image_urls")

    def remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.remote_image_urls")

    def take_remote_image_urls(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.take_remote_image_urls")

    def show_footer_flash(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.show_footer_flash")

    def set_text_content(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_text_content")

    def set_text_content_with_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_text_content_with_mention_bindings")

    def current_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_cursor")

    def history_navigation_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.history_navigation_cursor")

    def set_current_cursor(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_current_cursor")

    def current_text_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_text_elements")

    def shift_text_element(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.shift_text_element")

    def snapshot_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.snapshot_draft")

    def restore_draft(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.restore_draft")

    def set_placeholder_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_placeholder_text")

    def move_cursor_to_end(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.move_cursor_to_end")

    def move_cursor_to_history_entry_end(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.move_cursor_to_history_entry_end")

    def imported_text_for_textarea(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.imported_text_for_textarea")

    def clear_for_ctrl_c(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.clear_for_ctrl_c")

    def current_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_text")

    def apply_history_entry(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.apply_history_entry")

    def text_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.text_elements")

    def draft_snapshot(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.draft_snapshot")

    def local_image_paths(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.local_image_paths")

    def status_line_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.status_line_text")

    def local_images(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.local_images")

    def mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.mention_bindings")

    def take_recent_submission_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.take_recent_submission_mention_bindings")

    def record_pending_slash_command_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.record_pending_slash_command_history")

    def attach_image(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.attach_image")

    def take_recent_submission_images(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.take_recent_submission_images")

    def take_recent_submission_images_with_placeholders(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.take_recent_submission_images_with_placeholders")

    def flush_paste_burst_if_due(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.flush_paste_burst_if_due")

    def is_in_paste_burst(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.is_in_paste_burst")

    def recommended_paste_flush_delay(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.recommended_paste_flush_delay")

    def on_file_search_result(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.on_file_search_result")

    def show_quit_shortcut_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.show_quit_shortcut_hint")

    def clear_quit_shortcut_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.clear_quit_shortcut_hint")

    def quit_shortcut_hint_visible(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.quit_shortcut_hint_visible")

    def next_large_paste_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.next_large_paste_placeholder")

    def insert_str(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.insert_str")

    def handle_key_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event")

    def popup_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.popup_active")

    def clamp_to_char_boundary(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.clamp_to_char_boundary")

    def handle_non_ascii_char(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_non_ascii_char")

    def handle_key_event_with_file_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event_with_file_popup")

    def handle_key_event_with_skill_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event_with_skill_popup")

    def handle_key_event_with_mentions_v2_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event_with_mentions_v2_popup")

    def is_image_path(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.is_image_path")

    def insert_selected_file_path(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.insert_selected_file_path")

    def trim_text_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.trim_text_elements")

    def expand_pending_pastes(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.expand_pending_pastes")

    def skills(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.skills")

    def plugins(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.plugins")

    def mentions_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.mentions_enabled")

    def current_prefixed_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_prefixed_token")

    def current_at_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_at_token")

    def current_mentions_v2_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_mentions_v2_token")

    def current_mention_token(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_mention_token")

    def insert_selected_path(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.insert_selected_path")

    def insert_selected_mention(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.insert_selected_mention")

    def mention_name_from_insert_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.mention_name_from_insert_text")

    def current_mention_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.current_mention_elements")

    def snapshot_mention_bindings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.snapshot_mention_bindings")

    def bind_mentions_from_snapshot(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.bind_mentions_from_snapshot")

    def prepare_submission_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.prepare_submission_text")

    def prepare_submission_text_with_options(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.prepare_submission_text_with_options")

    def handle_submission(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_submission")

    def reset_vim_mode_after_successful_dispatch(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.reset_vim_mode_after_successful_dispatch")

    def handle_submission_with_time(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_submission_with_time")

    def try_dispatch_bare_slash_command(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.try_dispatch_bare_slash_command")

    def try_dispatch_slash_command_with_args(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.try_dispatch_slash_command_with_args")

    def prepare_inline_args_submission(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.prepare_inline_args_submission")

    def reject_slash_command_if_unavailable(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.reject_slash_command_if_unavailable")

    def stage_slash_command_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.stage_slash_command_history")

    def stage_selected_slash_command_history(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.stage_selected_slash_command_history")

    def stage_slash_command_history_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.stage_slash_command_history_text")

    def handle_remote_image_selection_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_remote_image_selection_key")

    def handle_key_event_without_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_key_event_without_popup")

    def is_bang_shell_command(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.is_bang_shell_command")

    def shell_mode_footer_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.shell_mode_footer_line")

    def handle_paste_burst_flush(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_paste_burst_flush")

    def handle_input_basic(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_input_basic")

    def handle_input_basic_with_time(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_input_basic_with_time")

    def sync_bash_mode_from_text(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_bash_mode_from_text")

    def reconcile_deleted_elements(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.reconcile_deleted_elements")

    def handle_shortcut_overlay_key(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.handle_shortcut_overlay_key")

    def footer_props(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.footer_props")

    def footer_mode(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.footer_mode")

    def custom_footer_height(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.custom_footer_height")

    def sync_popups(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_popups")

    def sync_command_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_command_popup")

    def sync_file_search_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_file_search_popup")

    def sync_mention_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_mention_popup")

    def sync_mentions_v2_popup(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.sync_mentions_v2_popup")

    def mention_items(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.mention_items")

    def connector_brief_description(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.connector_brief_description")

    def connector_description(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.connector_description")

    def set_has_focus(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_has_focus")

    def set_input_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_input_enabled")

    def show_shutdown_in_progress(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.show_shutdown_in_progress")

    def set_task_running(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_task_running")

    def set_queue_submissions(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_queue_submissions")

    def set_context_window(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_context_window")

    def set_esc_backtrack_hint(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_esc_backtrack_hint")

    def set_status_line(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_status_line")

    def set_status_line_hyperlink(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_status_line_hyperlink")

    def set_status_line_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_status_line_enabled")

    def set_side_conversation_context_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_side_conversation_context_label")

    def set_active_agent_label(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.set_active_agent_label")

    def update_recording_meter_in_place(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.update_recording_meter_in_place")

    def insert_recording_meter_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.insert_recording_meter_placeholder")

    def remove_recording_meter_placeholder(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.remove_recording_meter_placeholder")

    def desired_height_with_textarea_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.desired_height_with_textarea_right_reserve")

    def render_with_mask(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.render_with_mask")

    def render_with_mask_and_textarea_right_reserve(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ChatComposer.render_with_mask_and_textarea_right_reserve")

@dataclass
class ComposerDraft:
    """Python boundary for Rust ``bottom_pane::chat_composer::ComposerDraft``."""
    _payload: Any = None

@dataclass
class ComposerDraftSnapshot:
    """Python boundary for Rust ``bottom_pane::chat_composer::ComposerDraftSnapshot``."""
    _payload: Any = None

FOOTER_SPACING_HEIGHT: Any = None

def plan_mode_nudge_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::plan_mode_nudge_line``."""
    return not_ported(RUST_MODULE, "plan_mode_nudge_line")

def footer_insert_newline_key(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_insert_newline_key``."""
    return not_ported(RUST_MODULE, "footer_insert_newline_key")

def skill_description(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::skill_description``."""
    return not_ported(RUST_MODULE, "skill_description")

def is_mention_name_char(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::is_mention_name_char``."""
    return not_ported(RUST_MODULE, "is_mention_name_char")

def find_next_mention_token_range(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::find_next_mention_token_range``."""
    return not_ported(RUST_MODULE, "find_next_mention_token_range")

def cursor_pos(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::cursor_pos``."""
    return not_ported(RUST_MODULE, "cursor_pos")

def cursor_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::cursor_style``."""
    return not_ported(RUST_MODULE, "cursor_style")

def desired_height(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::desired_height``."""
    return not_ported(RUST_MODULE, "desired_height")

def render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::render``."""
    return not_ported(RUST_MODULE, "render")

def footer_hint_row_is_separated_from_composer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_hint_row_is_separated_from_composer``."""
    return not_ported(RUST_MODULE, "footer_hint_row_is_separated_from_composer")

def footer_flash_overrides_footer_hint_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_flash_overrides_footer_hint_override``."""
    return not_ported(RUST_MODULE, "footer_flash_overrides_footer_hint_override")

def remove_recording_meter_placeholder_clears_placeholder_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remove_recording_meter_placeholder_clears_placeholder_text``."""
    return not_ported(RUST_MODULE, "remove_recording_meter_placeholder_clears_placeholder_text")

def footer_flash_expires_and_falls_back_to_hint_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_flash_expires_and_falls_back_to_hint_override``."""
    return not_ported(RUST_MODULE, "footer_flash_expires_and_falls_back_to_hint_override")

def snapshot_composer_state_with_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::snapshot_composer_state_with_width``."""
    return not_ported(RUST_MODULE, "snapshot_composer_state_with_width")

def snapshot_composer_state(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::snapshot_composer_state``."""
    return not_ported(RUST_MODULE, "snapshot_composer_state")

def footer_mode_snapshots(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_mode_snapshots``."""
    return not_ported(RUST_MODULE, "footer_mode_snapshots")

def shell_command_cursor_uses_absorbed_prefix(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shell_command_cursor_uses_absorbed_prefix``."""
    return not_ported(RUST_MODULE, "shell_command_cursor_uses_absorbed_prefix")

def shell_command_uses_shell_accent_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shell_command_uses_shell_accent_style``."""
    return not_ported(RUST_MODULE, "shell_command_uses_shell_accent_style")

def status_line_hyperlink_marks_pr_number_cells(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::status_line_hyperlink_marks_pr_number_cells``."""
    return not_ported(RUST_MODULE, "status_line_hyperlink_marks_pr_number_cells")

def esc_exits_empty_shell_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::esc_exits_empty_shell_mode``."""
    return not_ported(RUST_MODULE, "esc_exits_empty_shell_mode")

def esc_keeps_shell_mode_when_paste_burst_flushes_pending_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::esc_keeps_shell_mode_when_paste_burst_flushes_pending_text``."""
    return not_ported(RUST_MODULE, "esc_keeps_shell_mode_when_paste_burst_flushes_pending_text")

def footer_collapse_snapshots(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::footer_collapse_snapshots``."""
    return not_ported(RUST_MODULE, "footer_collapse_snapshots")

def setup_collab_footer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::setup_collab_footer``."""
    return not_ported(RUST_MODULE, "setup_collab_footer")

def esc_hint_stays_hidden_with_draft_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::esc_hint_stays_hidden_with_draft_content``."""
    return not_ported(RUST_MODULE, "esc_hint_stays_hidden_with_draft_content")

def empty_vim_insert_escape_enters_normal_without_esc_hint(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::empty_vim_insert_escape_enters_normal_without_esc_hint``."""
    return not_ported(RUST_MODULE, "empty_vim_insert_escape_enters_normal_without_esc_hint")

def slash_opens_command_popup_in_vim_normal_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_opens_command_popup_in_vim_normal_mode``."""
    return not_ported(RUST_MODULE, "slash_opens_command_popup_in_vim_normal_mode")

def slash_command_can_be_typed_and_dispatched_after_vim_normal_slash(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_command_can_be_typed_and_dispatched_after_vim_normal_slash``."""
    return not_ported(RUST_MODULE, "slash_command_can_be_typed_and_dispatched_after_vim_normal_slash")

def inline_slash_command_dispatch_resets_vim_mode_to_normal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::inline_slash_command_dispatch_resets_vim_mode_to_normal``."""
    return not_ported(RUST_MODULE, "inline_slash_command_dispatch_resets_vim_mode_to_normal")

def bang_enters_shell_mode_in_vim_normal_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::bang_enters_shell_mode_in_vim_normal_mode``."""
    return not_ported(RUST_MODULE, "bang_enters_shell_mode_in_vim_normal_mode")

def shell_command_can_be_typed_after_vim_normal_bang(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shell_command_can_be_typed_after_vim_normal_bang``."""
    return not_ported(RUST_MODULE, "shell_command_can_be_typed_after_vim_normal_bang")

def base_footer_mode_tracks_empty_state_after_quit_hint_expires(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::base_footer_mode_tracks_empty_state_after_quit_hint_expires``."""
    return not_ported(RUST_MODULE, "base_footer_mode_tracks_empty_state_after_quit_hint_expires")

def clear_for_ctrl_c_records_cleared_draft(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::clear_for_ctrl_c_records_cleared_draft``."""
    return not_ported(RUST_MODULE, "clear_for_ctrl_c_records_cleared_draft")

def clear_for_ctrl_c_preserves_pending_paste_history_entry(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::clear_for_ctrl_c_preserves_pending_paste_history_entry``."""
    return not_ported(RUST_MODULE, "clear_for_ctrl_c_preserves_pending_paste_history_entry")

def large_paste_numbering_reuses_after_ctrl_c_clear(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::large_paste_numbering_reuses_after_ctrl_c_clear``."""
    return not_ported(RUST_MODULE, "large_paste_numbering_reuses_after_ctrl_c_clear")

def vim_mode_resets_to_normal_after_submission(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_mode_resets_to_normal_after_submission``."""
    return not_ported(RUST_MODULE, "vim_mode_resets_to_normal_after_submission")

def vim_mode_resets_to_normal_after_queued_submission(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_mode_resets_to_normal_after_queued_submission``."""
    return not_ported(RUST_MODULE, "vim_mode_resets_to_normal_after_queued_submission")

def vim_mode_stays_insert_after_suppressed_submission(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_mode_stays_insert_after_suppressed_submission``."""
    return not_ported(RUST_MODULE, "vim_mode_stays_insert_after_suppressed_submission")

def esc_switches_vim_insert_to_normal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::esc_switches_vim_insert_to_normal``."""
    return not_ported(RUST_MODULE, "esc_switches_vim_insert_to_normal")

def vim_insert_uses_bar_cursor_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_insert_uses_bar_cursor_style``."""
    return not_ported(RUST_MODULE, "vim_insert_uses_bar_cursor_style")

def clear_for_ctrl_c_preserves_image_draft_state(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::clear_for_ctrl_c_preserves_image_draft_state``."""
    return not_ported(RUST_MODULE, "clear_for_ctrl_c_preserves_image_draft_state")

def clear_for_ctrl_c_preserves_remote_offset_image_labels(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::clear_for_ctrl_c_preserves_remote_offset_image_labels``."""
    return not_ported(RUST_MODULE, "clear_for_ctrl_c_preserves_remote_offset_image_labels")

def apply_history_entry_preserves_local_placeholders_after_remote_prefix(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_history_entry_preserves_local_placeholders_after_remote_prefix``."""
    return not_ported(RUST_MODULE, "apply_history_entry_preserves_local_placeholders_after_remote_prefix")

def question_mark_only_toggles_on_first_char(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::question_mark_only_toggles_on_first_char``."""
    return not_ported(RUST_MODULE, "question_mark_only_toggles_on_first_char")

def shift_question_mark_toggles_shortcut_overlay_when_empty(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shift_question_mark_toggles_shortcut_overlay_when_empty``."""
    return not_ported(RUST_MODULE, "shift_question_mark_toggles_shortcut_overlay_when_empty")

def question_mark_does_not_toggle_during_paste_burst(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::question_mark_does_not_toggle_during_paste_burst``."""
    return not_ported(RUST_MODULE, "question_mark_does_not_toggle_during_paste_burst")

def set_connector_mentions_refreshes_open_mention_popup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_connector_mentions_refreshes_open_mention_popup``."""
    return not_ported(RUST_MODULE, "set_connector_mentions_refreshes_open_mention_popup")

def set_connector_mentions_skips_disabled_connectors(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_connector_mentions_skips_disabled_connectors``."""
    return not_ported(RUST_MODULE, "set_connector_mentions_skips_disabled_connectors")

def set_plugin_mentions_refreshes_open_mention_popup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_plugin_mentions_refreshes_open_mention_popup``."""
    return not_ported(RUST_MODULE, "set_plugin_mentions_refreshes_open_mention_popup")

def set_skill_mentions_refreshes_open_mention_popup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_skill_mentions_refreshes_open_mention_popup``."""
    return not_ported(RUST_MODULE, "set_skill_mentions_refreshes_open_mention_popup")

def mention_items_show_plugin_owned_skill_and_app_duplicates(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::mention_items_show_plugin_owned_skill_and_app_duplicates``."""
    return not_ported(RUST_MODULE, "mention_items_show_plugin_owned_skill_and_app_duplicates")

def plugin_mention_popup_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::plugin_mention_popup_snapshot``."""
    return not_ported(RUST_MODULE, "plugin_mention_popup_snapshot")

def mention_popup_type_prefixes_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::mention_popup_type_prefixes_snapshot``."""
    return not_ported(RUST_MODULE, "mention_popup_type_prefixes_snapshot")

def set_connector_mentions_excludes_disabled_apps_from_mention_popup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_connector_mentions_excludes_disabled_apps_from_mention_popup``."""
    return not_ported(RUST_MODULE, "set_connector_mentions_excludes_disabled_apps_from_mention_popup")

def shortcut_overlay_persists_while_task_running(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shortcut_overlay_persists_while_task_running``."""
    return not_ported(RUST_MODULE, "shortcut_overlay_persists_while_task_running")

def test_current_at_token_basic_cases(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_basic_cases``."""
    return not_ported(RUST_MODULE, "test_current_at_token_basic_cases")

def test_current_at_token_cursor_positions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_cursor_positions``."""
    return not_ported(RUST_MODULE, "test_current_at_token_cursor_positions")

def test_current_at_token_whitespace_boundaries(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_whitespace_boundaries``."""
    return not_ported(RUST_MODULE, "test_current_at_token_whitespace_boundaries")

def test_current_at_token_tracks_tokens_with_second_at(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_tracks_tokens_with_second_at``."""
    return not_ported(RUST_MODULE, "test_current_at_token_tracks_tokens_with_second_at")

def test_current_at_token_allows_file_queries_with_second_at(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_allows_file_queries_with_second_at``."""
    return not_ported(RUST_MODULE, "test_current_at_token_allows_file_queries_with_second_at")

def test_current_at_token_ignores_mid_word_at(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_current_at_token_ignores_mid_word_at``."""
    return not_ported(RUST_MODULE, "test_current_at_token_ignores_mid_word_at")

def enter_submits_when_file_popup_has_no_selection(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::enter_submits_when_file_popup_has_no_selection``."""
    return not_ported(RUST_MODULE, "enter_submits_when_file_popup_has_no_selection")

def ascii_prefix_survives_non_ascii_followup(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::ascii_prefix_survives_non_ascii_followup``."""
    return not_ported(RUST_MODULE, "ascii_prefix_survives_non_ascii_followup")

def non_ascii_char_inserts_immediately_without_burst_state(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::non_ascii_char_inserts_immediately_without_burst_state``."""
    return not_ported(RUST_MODULE, "non_ascii_char_inserts_immediately_without_burst_state")

def non_ascii_burst_buffers_enter_and_flushes_multiline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::non_ascii_burst_buffers_enter_and_flushes_multiline``."""
    return not_ported(RUST_MODULE, "non_ascii_burst_buffers_enter_and_flushes_multiline")

def non_ascii_burst_preserves_ideographic_space_and_ascii(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::non_ascii_burst_preserves_ideographic_space_and_ascii``."""
    return not_ported(RUST_MODULE, "non_ascii_burst_preserves_ideographic_space_and_ascii")

def non_ascii_burst_buffers_large_multiline_mixed_ascii_and_unicode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::non_ascii_burst_buffers_large_multiline_mixed_ascii_and_unicode``."""
    return not_ported(RUST_MODULE, "non_ascii_burst_buffers_large_multiline_mixed_ascii_and_unicode")

LARGE_MIXED_PAYLOAD: Any = None

def ascii_burst_treats_enter_as_newline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::ascii_burst_treats_enter_as_newline``."""
    return not_ported(RUST_MODULE, "ascii_burst_treats_enter_as_newline")

def queued_submission_flushes_ascii_burst_instead_of_inserting_newline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::queued_submission_flushes_ascii_burst_instead_of_inserting_newline``."""
    return not_ported(RUST_MODULE, "queued_submission_flushes_ascii_burst_instead_of_inserting_newline")

def slash_context_enter_ignores_paste_burst_enter_suppression(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_context_enter_ignores_paste_burst_enter_suppression``."""
    return not_ported(RUST_MODULE, "slash_context_enter_ignores_paste_burst_enter_suppression")

def non_char_key_flushes_active_burst_before_input(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::non_char_key_flushes_active_burst_before_input``."""
    return not_ported(RUST_MODULE, "non_char_key_flushes_active_burst_before_input")

def disable_paste_burst_flushes_pending_first_char_and_inserts_immediately(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::disable_paste_burst_flushes_pending_first_char_and_inserts_immediately``."""
    return not_ported(RUST_MODULE, "disable_paste_burst_flushes_pending_first_char_and_inserts_immediately")

def handle_paste_small_inserts_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::handle_paste_small_inserts_text``."""
    return not_ported(RUST_MODULE, "handle_paste_small_inserts_text")

def empty_enter_returns_none(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::empty_enter_returns_none``."""
    return not_ported(RUST_MODULE, "empty_enter_returns_none")

def handle_paste_large_uses_placeholder_and_replaces_on_submit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::handle_paste_large_uses_placeholder_and_replaces_on_submit``."""
    return not_ported(RUST_MODULE, "handle_paste_large_uses_placeholder_and_replaces_on_submit")

def submit_at_character_limit_succeeds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::submit_at_character_limit_succeeds``."""
    return not_ported(RUST_MODULE, "submit_at_character_limit_succeeds")

def oversized_submit_reports_error_and_restores_draft(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::oversized_submit_reports_error_and_restores_draft``."""
    return not_ported(RUST_MODULE, "oversized_submit_reports_error_and_restores_draft")

def oversized_queued_submission_reports_error_and_restores_draft(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::oversized_queued_submission_reports_error_and_restores_draft``."""
    return not_ported(RUST_MODULE, "oversized_queued_submission_reports_error_and_restores_draft")

def edit_clears_pending_paste(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::edit_clears_pending_paste``."""
    return not_ported(RUST_MODULE, "edit_clears_pending_paste")

def ui_snapshots(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::ui_snapshots``."""
    return not_ported(RUST_MODULE, "ui_snapshots")

def image_placeholder_snapshots(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::image_placeholder_snapshots``."""
    return not_ported(RUST_MODULE, "image_placeholder_snapshots")

def remote_image_rows_snapshots(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remote_image_rows_snapshots``."""
    return not_ported(RUST_MODULE, "remote_image_rows_snapshots")

def slash_popup_model_first_for_mo_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_model_first_for_mo_ui``."""
    return not_ported(RUST_MODULE, "slash_popup_model_first_for_mo_ui")

def slash_popup_model_first_for_mo_logic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_model_first_for_mo_logic``."""
    return not_ported(RUST_MODULE, "slash_popup_model_first_for_mo_logic")

def slash_popup_resume_for_res_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_resume_for_res_ui``."""
    return not_ported(RUST_MODULE, "slash_popup_resume_for_res_ui")

def slash_popup_resume_for_res_logic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_resume_for_res_logic``."""
    return not_ported(RUST_MODULE, "slash_popup_resume_for_res_logic")

def slash_popup_pets_for_pet_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_pets_for_pet_ui``."""
    return not_ported(RUST_MODULE, "slash_popup_pets_for_pet_ui")

def slash_popup_pets_for_pet_logic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_pets_for_pet_logic``."""
    return not_ported(RUST_MODULE, "slash_popup_pets_for_pet_logic")

def slash_popup_btw_for_bt_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_btw_for_bt_ui``."""
    return not_ported(RUST_MODULE, "slash_popup_btw_for_bt_ui")

def slash_popup_btw_for_bt_logic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_btw_for_bt_logic``."""
    return not_ported(RUST_MODULE, "slash_popup_btw_for_bt_logic")

def slash_popup_side_for_si_ui(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_side_for_si_ui``."""
    return not_ported(RUST_MODULE, "slash_popup_side_for_si_ui")

def slash_popup_side_for_si_logic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_side_for_si_logic``."""
    return not_ported(RUST_MODULE, "slash_popup_side_for_si_logic")

def service_tier_slash_command_dispatches_from_catalog_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::service_tier_slash_command_dispatches_from_catalog_name``."""
    return not_ported(RUST_MODULE, "service_tier_slash_command_dispatches_from_catalog_name")

def flush_after_paste_burst(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::flush_after_paste_burst``."""
    return not_ported(RUST_MODULE, "flush_after_paste_burst")

def type_chars_humanlike(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::type_chars_humanlike``."""
    return not_ported(RUST_MODULE, "type_chars_humanlike")

def slash_init_dispatches_command_and_does_not_submit_literal_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_init_dispatches_command_and_does_not_submit_literal_text``."""
    return not_ported(RUST_MODULE, "slash_init_dispatches_command_and_does_not_submit_literal_text")

def kill_buffer_persists_after_submit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::kill_buffer_persists_after_submit``."""
    return not_ported(RUST_MODULE, "kill_buffer_persists_after_submit")

def kill_buffer_persists_after_slash_command_dispatch(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::kill_buffer_persists_after_slash_command_dispatch``."""
    return not_ported(RUST_MODULE, "kill_buffer_persists_after_slash_command_dispatch")

def slash_command_disabled_while_task_running_keeps_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_command_disabled_while_task_running_keeps_text``."""
    return not_ported(RUST_MODULE, "slash_command_disabled_while_task_running_keeps_text")

def enter_queues_when_queue_submissions_is_enabled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::enter_queues_when_queue_submissions_is_enabled``."""
    return not_ported(RUST_MODULE, "enter_queues_when_queue_submissions_is_enabled")

def tab_queues_slash_led_prompts_while_task_running_without_validation(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::tab_queues_slash_led_prompts_while_task_running_without_validation``."""
    return not_ported(RUST_MODULE, "tab_queues_slash_led_prompts_while_task_running_without_validation")

def assert_queued_slash(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::assert_queued_slash``."""
    return not_ported(RUST_MODULE, "assert_queued_slash")

def remapped_submit_does_not_fall_back_to_enter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remapped_submit_does_not_fall_back_to_enter``."""
    return not_ported(RUST_MODULE, "remapped_submit_does_not_fall_back_to_enter")

def remapped_queue_does_not_fall_back_to_tab(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remapped_queue_does_not_fall_back_to_tab``."""
    return not_ported(RUST_MODULE, "remapped_queue_does_not_fall_back_to_tab")

def remapped_history_search_does_not_fall_back_to_ctrl_r(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remapped_history_search_does_not_fall_back_to_ctrl_r``."""
    return not_ported(RUST_MODULE, "remapped_history_search_does_not_fall_back_to_ctrl_r")

def tab_queues_leading_space_slash_as_plain_text_while_task_running(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::tab_queues_leading_space_slash_as_plain_text_while_task_running``."""
    return not_ported(RUST_MODULE, "tab_queues_leading_space_slash_as_plain_text_while_task_running")

def tab_queues_bang_shell_prompts_while_task_running_without_execution(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::tab_queues_bang_shell_prompts_while_task_running_without_execution``."""
    return not_ported(RUST_MODULE, "tab_queues_bang_shell_prompts_while_task_running_without_execution")

def assert_queued_shell(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::assert_queued_shell``."""
    return not_ported(RUST_MODULE, "assert_queued_shell")

def slash_tab_completion_moves_cursor_to_end(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_tab_completion_moves_cursor_to_end``."""
    return not_ported(RUST_MODULE, "slash_tab_completion_moves_cursor_to_end")

def slash_tab_completion_wins_over_queueing_while_task_running(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_tab_completion_wins_over_queueing_while_task_running``."""
    return not_ported(RUST_MODULE, "slash_tab_completion_wins_over_queueing_while_task_running")

def slash_key_completes_selected_slash_command_as_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_key_completes_selected_slash_command_as_text``."""
    return not_ported(RUST_MODULE, "slash_key_completes_selected_slash_command_as_text")

def slash_tab_then_enter_dispatches_builtin_command(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_tab_then_enter_dispatches_builtin_command``."""
    return not_ported(RUST_MODULE, "slash_tab_then_enter_dispatches_builtin_command")

def slash_command_elementizes_on_space(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_command_elementizes_on_space``."""
    return not_ported(RUST_MODULE, "slash_command_elementizes_on_space")

def slash_command_elementizes_only_known_commands(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_command_elementizes_only_known_commands``."""
    return not_ported(RUST_MODULE, "slash_command_elementizes_only_known_commands")

def slash_command_element_removed_when_not_at_start(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_command_element_removed_when_not_at_start``."""
    return not_ported(RUST_MODULE, "slash_command_element_removed_when_not_at_start")

def tab_submits_when_no_task_running(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::tab_submits_when_no_task_running``."""
    return not_ported(RUST_MODULE, "tab_submits_when_no_task_running")

def tab_does_not_submit_for_bang_shell_command(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::tab_does_not_submit_for_bang_shell_command``."""
    return not_ported(RUST_MODULE, "tab_does_not_submit_for_bang_shell_command")

def bang_prefixed_slash_text_submits_literal_shell_command(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::bang_prefixed_slash_text_submits_literal_shell_command``."""
    return not_ported(RUST_MODULE, "bang_prefixed_slash_text_submits_literal_shell_command")

def slash_mention_dispatches_command_and_inserts_at(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_mention_dispatches_command_and_inserts_at``."""
    return not_ported(RUST_MODULE, "slash_mention_dispatches_command_and_inserts_at")

def slash_plan_args_preserve_text_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_plan_args_preserve_text_elements``."""
    return not_ported(RUST_MODULE, "slash_plan_args_preserve_text_elements")

def file_completion_preserves_large_paste_placeholder_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::file_completion_preserves_large_paste_placeholder_elements``."""
    return not_ported(RUST_MODULE, "file_completion_preserves_large_paste_placeholder_elements")

def test_multiple_pastes_submission(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_multiple_pastes_submission``."""
    return not_ported(RUST_MODULE, "test_multiple_pastes_submission")

def test_placeholder_deletion(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_placeholder_deletion``."""
    return not_ported(RUST_MODULE, "test_placeholder_deletion")

def deleting_duplicate_length_pastes_removes_only_target(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::deleting_duplicate_length_pastes_removes_only_target``."""
    return not_ported(RUST_MODULE, "deleting_duplicate_length_pastes_removes_only_target")

def large_paste_numbering_continues_with_same_length_placeholder(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::large_paste_numbering_continues_with_same_length_placeholder``."""
    return not_ported(RUST_MODULE, "large_paste_numbering_continues_with_same_length_placeholder")

def large_paste_numbering_reuses_after_all_deleted(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::large_paste_numbering_reuses_after_all_deleted``."""
    return not_ported(RUST_MODULE, "large_paste_numbering_reuses_after_all_deleted")

def test_partial_placeholder_deletion(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::test_partial_placeholder_deletion``."""
    return not_ported(RUST_MODULE, "test_partial_placeholder_deletion")

def attach_image_and_submit_includes_local_image_paths(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::attach_image_and_submit_includes_local_image_paths``."""
    return not_ported(RUST_MODULE, "attach_image_and_submit_includes_local_image_paths")

def submit_captures_recent_mention_bindings_before_clearing_textarea(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::submit_captures_recent_mention_bindings_before_clearing_textarea``."""
    return not_ported(RUST_MODULE, "submit_captures_recent_mention_bindings_before_clearing_textarea")

def history_navigation_restores_remote_and_local_image_attachments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::history_navigation_restores_remote_and_local_image_attachments``."""
    return not_ported(RUST_MODULE, "history_navigation_restores_remote_and_local_image_attachments")

def history_navigation_restores_remote_only_submissions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::history_navigation_restores_remote_only_submissions``."""
    return not_ported(RUST_MODULE, "history_navigation_restores_remote_only_submissions")

def history_navigation_leaves_cursor_at_end_of_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::history_navigation_leaves_cursor_at_end_of_line``."""
    return not_ported(RUST_MODULE, "history_navigation_leaves_cursor_at_end_of_line")

def vim_normal_j_k_navigate_history_at_history_boundaries(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_normal_j_k_navigate_history_at_history_boundaries``."""
    return not_ported(RUST_MODULE, "vim_normal_j_k_navigate_history_at_history_boundaries")

def remapped_vim_normal_history_navigation_does_not_fall_back_to_j_k(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remapped_vim_normal_history_navigation_does_not_fall_back_to_j_k``."""
    return not_ported(RUST_MODULE, "remapped_vim_normal_history_navigation_does_not_fall_back_to_j_k")

def vim_normal_j_k_fall_back_to_multiline_cursor_movement(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_normal_j_k_fall_back_to_multiline_cursor_movement``."""
    return not_ported(RUST_MODULE, "vim_normal_j_k_fall_back_to_multiline_cursor_movement")

def vim_normal_operator_motion_does_not_navigate_history(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_normal_operator_motion_does_not_navigate_history``."""
    return not_ported(RUST_MODULE, "vim_normal_operator_motion_does_not_navigate_history")

def vim_normal_operator_pending_consumes_submit_key(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_normal_operator_pending_consumes_submit_key``."""
    return not_ported(RUST_MODULE, "vim_normal_operator_pending_consumes_submit_key")

def remapped_editor_history_navigation_does_not_fall_back_to_up(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remapped_editor_history_navigation_does_not_fall_back_to_up``."""
    return not_ported(RUST_MODULE, "remapped_editor_history_navigation_does_not_fall_back_to_up")

def history_navigation_from_start_of_bang_command_recalls_older_entry(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::history_navigation_from_start_of_bang_command_recalls_older_entry``."""
    return not_ported(RUST_MODULE, "history_navigation_from_start_of_bang_command_recalls_older_entry")

def vim_normal_history_navigation_from_start_of_bang_command_recalls_older_entry(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::vim_normal_history_navigation_from_start_of_bang_command_recalls_older_entry``."""
    return not_ported(RUST_MODULE, "vim_normal_history_navigation_from_start_of_bang_command_recalls_older_entry")

def set_text_content_reattaches_images_without_placeholder_metadata(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::set_text_content_reattaches_images_without_placeholder_metadata``."""
    return not_ported(RUST_MODULE, "set_text_content_reattaches_images_without_placeholder_metadata")

def large_paste_preserves_image_text_elements_on_submit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::large_paste_preserves_image_text_elements_on_submit``."""
    return not_ported(RUST_MODULE, "large_paste_preserves_image_text_elements_on_submit")

def large_paste_with_leading_whitespace_trims_and_shifts_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::large_paste_with_leading_whitespace_trims_and_shifts_elements``."""
    return not_ported(RUST_MODULE, "large_paste_with_leading_whitespace_trims_and_shifts_elements")

def pasted_crlf_normalizes_newlines_for_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::pasted_crlf_normalizes_newlines_for_elements``."""
    return not_ported(RUST_MODULE, "pasted_crlf_normalizes_newlines_for_elements")

def suppressed_submission_restores_pending_paste_payload(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::suppressed_submission_restores_pending_paste_payload``."""
    return not_ported(RUST_MODULE, "suppressed_submission_restores_pending_paste_payload")

def attach_image_without_text_submits_empty_text_and_images(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::attach_image_without_text_submits_empty_text_and_images``."""
    return not_ported(RUST_MODULE, "attach_image_without_text_submits_empty_text_and_images")

def duplicate_image_placeholders_get_suffix(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::duplicate_image_placeholders_get_suffix``."""
    return not_ported(RUST_MODULE, "duplicate_image_placeholders_get_suffix")

def image_placeholder_backspace_behaves_like_text_placeholder(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::image_placeholder_backspace_behaves_like_text_placeholder``."""
    return not_ported(RUST_MODULE, "image_placeholder_backspace_behaves_like_text_placeholder")

def backspace_with_multibyte_text_before_placeholder_does_not_panic(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::backspace_with_multibyte_text_before_placeholder_does_not_panic``."""
    return not_ported(RUST_MODULE, "backspace_with_multibyte_text_before_placeholder_does_not_panic")

def deleting_one_of_duplicate_image_placeholders_removes_one_entry(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::deleting_one_of_duplicate_image_placeholders_removes_one_entry``."""
    return not_ported(RUST_MODULE, "deleting_one_of_duplicate_image_placeholders_removes_one_entry")

def deleting_reordered_image_one_renumbers_text_in_place(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::deleting_reordered_image_one_renumbers_text_in_place``."""
    return not_ported(RUST_MODULE, "deleting_reordered_image_one_renumbers_text_in_place")

def deleting_first_text_element_renumbers_following_text_element(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::deleting_first_text_element_renumbers_following_text_element``."""
    return not_ported(RUST_MODULE, "deleting_first_text_element_renumbers_following_text_element")

def pasting_filepath_attaches_image(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::pasting_filepath_attaches_image``."""
    return not_ported(RUST_MODULE, "pasting_filepath_attaches_image")

def slash_path_input_submits_without_command_error(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_path_input_submits_without_command_error``."""
    return not_ported(RUST_MODULE, "slash_path_input_submits_without_command_error")

def slash_with_leading_space_submits_as_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_with_leading_space_submits_as_text``."""
    return not_ported(RUST_MODULE, "slash_with_leading_space_submits_as_text")

def pending_first_ascii_char_flushes_as_typed(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::pending_first_ascii_char_flushes_as_typed``."""
    return not_ported(RUST_MODULE, "pending_first_ascii_char_flushes_as_typed")

def burst_paste_fast_small_buffers_and_flushes_on_stop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::burst_paste_fast_small_buffers_and_flushes_on_stop``."""
    return not_ported(RUST_MODULE, "burst_paste_fast_small_buffers_and_flushes_on_stop")

def burst_paste_fast_large_inserts_placeholder_on_flush(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::burst_paste_fast_large_inserts_placeholder_on_flush``."""
    return not_ported(RUST_MODULE, "burst_paste_fast_large_inserts_placeholder_on_flush")

def humanlike_typing_1000_chars_appears_live_no_placeholder(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::humanlike_typing_1000_chars_appears_live_no_placeholder``."""
    return not_ported(RUST_MODULE, "humanlike_typing_1000_chars_appears_live_no_placeholder")

def slash_popup_not_activated_for_slash_space_text_history_like_input(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_not_activated_for_slash_space_text_history_like_input``."""
    return not_ported(RUST_MODULE, "slash_popup_not_activated_for_slash_space_text_history_like_input")

def slash_popup_activated_for_bare_slash_and_valid_prefixes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::slash_popup_activated_for_bare_slash_and_valid_prefixes``."""
    return not_ported(RUST_MODULE, "slash_popup_activated_for_bare_slash_and_valid_prefixes")

def bare_slash_command_can_be_recalled_after_recording_pending_history(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::bare_slash_command_can_be_recalled_after_recording_pending_history``."""
    return not_ported(RUST_MODULE, "bare_slash_command_can_be_recalled_after_recording_pending_history")

def popup_selected_slash_command_records_canonical_command_history(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::popup_selected_slash_command_records_canonical_command_history``."""
    return not_ported(RUST_MODULE, "popup_selected_slash_command_records_canonical_command_history")

def inline_slash_command_can_be_recalled_after_recording_pending_history(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::inline_slash_command_can_be_recalled_after_recording_pending_history``."""
    return not_ported(RUST_MODULE, "inline_slash_command_can_be_recalled_after_recording_pending_history")

def apply_external_edit_rebuilds_text_and_attachments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_rebuilds_text_and_attachments``."""
    return not_ported(RUST_MODULE, "apply_external_edit_rebuilds_text_and_attachments")

def apply_external_edit_absorbs_bash_prefix_without_duplication(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_absorbs_bash_prefix_without_duplication``."""
    return not_ported(RUST_MODULE, "apply_external_edit_absorbs_bash_prefix_without_duplication")

def apply_external_edit_can_leave_bash_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_can_leave_bash_mode``."""
    return not_ported(RUST_MODULE, "apply_external_edit_can_leave_bash_mode")

def apply_external_edit_can_enter_bash_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_can_enter_bash_mode``."""
    return not_ported(RUST_MODULE, "apply_external_edit_can_enter_bash_mode")

def apply_external_edit_drops_missing_attachments(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_drops_missing_attachments``."""
    return not_ported(RUST_MODULE, "apply_external_edit_drops_missing_attachments")

def apply_external_edit_renumbers_image_placeholders(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_renumbers_image_placeholders``."""
    return not_ported(RUST_MODULE, "apply_external_edit_renumbers_image_placeholders")

def current_text_with_pending_expands_placeholders(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::current_text_with_pending_expands_placeholders``."""
    return not_ported(RUST_MODULE, "current_text_with_pending_expands_placeholders")

def current_text_with_pending_expands_overlapping_placeholders(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::current_text_with_pending_expands_overlapping_placeholders``."""
    return not_ported(RUST_MODULE, "current_text_with_pending_expands_overlapping_placeholders")

def apply_external_edit_limits_duplicates_to_occurrences(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::apply_external_edit_limits_duplicates_to_occurrences``."""
    return not_ported(RUST_MODULE, "apply_external_edit_limits_duplicates_to_occurrences")

def remote_images_do_not_modify_textarea_text_or_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::remote_images_do_not_modify_textarea_text_or_elements``."""
    return not_ported(RUST_MODULE, "remote_images_do_not_modify_textarea_text_or_elements")

def attach_image_after_remote_prefix_uses_offset_label(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::attach_image_after_remote_prefix_uses_offset_label``."""
    return not_ported(RUST_MODULE, "attach_image_after_remote_prefix_uses_offset_label")

def prepare_submission_keeps_remote_offset_local_placeholder_numbering(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::prepare_submission_keeps_remote_offset_local_placeholder_numbering``."""
    return not_ported(RUST_MODULE, "prepare_submission_keeps_remote_offset_local_placeholder_numbering")

def prepare_submission_with_only_remote_images_returns_empty_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::prepare_submission_with_only_remote_images_returns_empty_text``."""
    return not_ported(RUST_MODULE, "prepare_submission_with_only_remote_images_returns_empty_text")

def delete_selected_remote_image_relabels_local_placeholders(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::delete_selected_remote_image_relabels_local_placeholders``."""
    return not_ported(RUST_MODULE, "delete_selected_remote_image_relabels_local_placeholders")

def input_disabled_ignores_keypresses_and_hides_cursor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::input_disabled_ignores_keypresses_and_hides_cursor``."""
    return not_ported(RUST_MODULE, "input_disabled_ignores_keypresses_and_hides_cursor")

def shutdown_in_progress_disables_input_and_uses_hint_without_footer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``bottom_pane::chat_composer::shutdown_in_progress_disables_input_and_uses_hint_without_footer``."""
    return not_ported(RUST_MODULE, "shutdown_in_progress_disables_input_and_uses_hint_without_footer")

__all__ = [
    "ChatComposer",
    "ChatComposerConfig",
    "ComposerDraft",
    "ComposerDraftSnapshot",
    "FOOTER_SPACING_HEIGHT",
    "InputResult",
    "LARGE_MIXED_PAYLOAD",
    "LARGE_PASTE_CHAR_THRESHOLD",
    "QueuedInputAction",
    "RUST_MODULE",
    "apply_external_edit_absorbs_bash_prefix_without_duplication",
    "apply_external_edit_can_enter_bash_mode",
    "apply_external_edit_can_leave_bash_mode",
    "apply_external_edit_drops_missing_attachments",
    "apply_external_edit_limits_duplicates_to_occurrences",
    "apply_external_edit_rebuilds_text_and_attachments",
    "apply_external_edit_renumbers_image_placeholders",
    "apply_history_entry_preserves_local_placeholders_after_remote_prefix",
    "ascii_burst_treats_enter_as_newline",
    "ascii_prefix_survives_non_ascii_followup",
    "assert_queued_shell",
    "assert_queued_slash",
    "attach_image_after_remote_prefix_uses_offset_label",
    "attach_image_and_submit_includes_local_image_paths",
    "attach_image_without_text_submits_empty_text_and_images",
    "backspace_with_multibyte_text_before_placeholder_does_not_panic",
    "bang_enters_shell_mode_in_vim_normal_mode",
    "bang_prefixed_slash_text_submits_literal_shell_command",
    "bare_slash_command_can_be_recalled_after_recording_pending_history",
    "base_footer_mode_tracks_empty_state_after_quit_hint_expires",
    "burst_paste_fast_large_inserts_placeholder_on_flush",
    "burst_paste_fast_small_buffers_and_flushes_on_stop",
    "clear_for_ctrl_c_preserves_image_draft_state",
    "clear_for_ctrl_c_preserves_pending_paste_history_entry",
    "clear_for_ctrl_c_preserves_remote_offset_image_labels",
    "clear_for_ctrl_c_records_cleared_draft",
    "current_text_with_pending_expands_overlapping_placeholders",
    "current_text_with_pending_expands_placeholders",
    "cursor_pos",
    "cursor_style",
    "default",
    "delete_selected_remote_image_relabels_local_placeholders",
    "deleting_duplicate_length_pastes_removes_only_target",
    "deleting_first_text_element_renumbers_following_text_element",
    "deleting_one_of_duplicate_image_placeholders_removes_one_entry",
    "deleting_reordered_image_one_renumbers_text_in_place",
    "desired_height",
    "disable_paste_burst_flushes_pending_first_char_and_inserts_immediately",
    "duplicate_image_placeholders_get_suffix",
    "edit_clears_pending_paste",
    "empty_enter_returns_none",
    "empty_vim_insert_escape_enters_normal_without_esc_hint",
    "enter_queues_when_queue_submissions_is_enabled",
    "enter_submits_when_file_popup_has_no_selection",
    "esc_exits_empty_shell_mode",
    "esc_hint_stays_hidden_with_draft_content",
    "esc_keeps_shell_mode_when_paste_burst_flushes_pending_text",
    "esc_switches_vim_insert_to_normal",
    "file_completion_preserves_large_paste_placeholder_elements",
    "find_next_mention_token_range",
    "flush_after_paste_burst",
    "footer_collapse_snapshots",
    "footer_flash_expires_and_falls_back_to_hint_override",
    "footer_flash_overrides_footer_hint_override",
    "footer_hint_row_is_separated_from_composer",
    "footer_insert_newline_key",
    "footer_mode_snapshots",
    "handle_paste_large_uses_placeholder_and_replaces_on_submit",
    "handle_paste_small_inserts_text",
    "history_navigation_from_start_of_bang_command_recalls_older_entry",
    "history_navigation_leaves_cursor_at_end_of_line",
    "history_navigation_restores_remote_and_local_image_attachments",
    "history_navigation_restores_remote_only_submissions",
    "humanlike_typing_1000_chars_appears_live_no_placeholder",
    "image_placeholder_backspace_behaves_like_text_placeholder",
    "image_placeholder_snapshots",
    "inline_slash_command_can_be_recalled_after_recording_pending_history",
    "inline_slash_command_dispatch_resets_vim_mode_to_normal",
    "input_disabled_ignores_keypresses_and_hides_cursor",
    "is_mention_name_char",
    "kill_buffer_persists_after_slash_command_dispatch",
    "kill_buffer_persists_after_submit",
    "large_paste_numbering_continues_with_same_length_placeholder",
    "large_paste_numbering_reuses_after_all_deleted",
    "large_paste_numbering_reuses_after_ctrl_c_clear",
    "large_paste_preserves_image_text_elements_on_submit",
    "large_paste_with_leading_whitespace_trims_and_shifts_elements",
    "mention_items_show_plugin_owned_skill_and_app_duplicates",
    "mention_popup_type_prefixes_snapshot",
    "non_ascii_burst_buffers_enter_and_flushes_multiline",
    "non_ascii_burst_buffers_large_multiline_mixed_ascii_and_unicode",
    "non_ascii_burst_preserves_ideographic_space_and_ascii",
    "non_ascii_char_inserts_immediately_without_burst_state",
    "non_char_key_flushes_active_burst_before_input",
    "oversized_queued_submission_reports_error_and_restores_draft",
    "oversized_submit_reports_error_and_restores_draft",
    "pasted_crlf_normalizes_newlines_for_elements",
    "pasting_filepath_attaches_image",
    "pending_first_ascii_char_flushes_as_typed",
    "plan_mode_nudge_line",
    "plugin_mention_popup_snapshot",
    "popup_selected_slash_command_records_canonical_command_history",
    "prepare_submission_keeps_remote_offset_local_placeholder_numbering",
    "prepare_submission_with_only_remote_images_returns_empty_text",
    "question_mark_does_not_toggle_during_paste_burst",
    "question_mark_only_toggles_on_first_char",
    "queued_submission_flushes_ascii_burst_instead_of_inserting_newline",
    "remapped_editor_history_navigation_does_not_fall_back_to_up",
    "remapped_history_search_does_not_fall_back_to_ctrl_r",
    "remapped_queue_does_not_fall_back_to_tab",
    "remapped_submit_does_not_fall_back_to_enter",
    "remapped_vim_normal_history_navigation_does_not_fall_back_to_j_k",
    "remote_image_rows_snapshots",
    "remote_images_do_not_modify_textarea_text_or_elements",
    "remove_recording_meter_placeholder_clears_placeholder_text",
    "render",
    "service_tier_slash_command_dispatches_from_catalog_name",
    "set_connector_mentions_excludes_disabled_apps_from_mention_popup",
    "set_connector_mentions_refreshes_open_mention_popup",
    "set_connector_mentions_skips_disabled_connectors",
    "set_plugin_mentions_refreshes_open_mention_popup",
    "set_skill_mentions_refreshes_open_mention_popup",
    "set_text_content_reattaches_images_without_placeholder_metadata",
    "setup_collab_footer",
    "shell_command_can_be_typed_after_vim_normal_bang",
    "shell_command_cursor_uses_absorbed_prefix",
    "shell_command_uses_shell_accent_style",
    "shift_question_mark_toggles_shortcut_overlay_when_empty",
    "shortcut_overlay_persists_while_task_running",
    "shutdown_in_progress_disables_input_and_uses_hint_without_footer",
    "skill_description",
    "slash_command_can_be_typed_and_dispatched_after_vim_normal_slash",
    "slash_command_disabled_while_task_running_keeps_text",
    "slash_command_element_removed_when_not_at_start",
    "slash_command_elementizes_on_space",
    "slash_command_elementizes_only_known_commands",
    "slash_context_enter_ignores_paste_burst_enter_suppression",
    "slash_init_dispatches_command_and_does_not_submit_literal_text",
    "slash_key_completes_selected_slash_command_as_text",
    "slash_mention_dispatches_command_and_inserts_at",
    "slash_opens_command_popup_in_vim_normal_mode",
    "slash_path_input_submits_without_command_error",
    "slash_plan_args_preserve_text_elements",
    "slash_popup_activated_for_bare_slash_and_valid_prefixes",
    "slash_popup_btw_for_bt_logic",
    "slash_popup_btw_for_bt_ui",
    "slash_popup_model_first_for_mo_logic",
    "slash_popup_model_first_for_mo_ui",
    "slash_popup_not_activated_for_slash_space_text_history_like_input",
    "slash_popup_pets_for_pet_logic",
    "slash_popup_pets_for_pet_ui",
    "slash_popup_resume_for_res_logic",
    "slash_popup_resume_for_res_ui",
    "slash_popup_side_for_si_logic",
    "slash_popup_side_for_si_ui",
    "slash_tab_completion_moves_cursor_to_end",
    "slash_tab_completion_wins_over_queueing_while_task_running",
    "slash_tab_then_enter_dispatches_builtin_command",
    "slash_with_leading_space_submits_as_text",
    "snapshot_composer_state",
    "snapshot_composer_state_with_width",
    "status_line_hyperlink_marks_pr_number_cells",
    "submit_at_character_limit_succeeds",
    "submit_captures_recent_mention_bindings_before_clearing_textarea",
    "suppressed_submission_restores_pending_paste_payload",
    "tab_does_not_submit_for_bang_shell_command",
    "tab_queues_bang_shell_prompts_while_task_running_without_execution",
    "tab_queues_leading_space_slash_as_plain_text_while_task_running",
    "tab_queues_slash_led_prompts_while_task_running_without_validation",
    "tab_submits_when_no_task_running",
    "test_current_at_token_allows_file_queries_with_second_at",
    "test_current_at_token_basic_cases",
    "test_current_at_token_cursor_positions",
    "test_current_at_token_ignores_mid_word_at",
    "test_current_at_token_tracks_tokens_with_second_at",
    "test_current_at_token_whitespace_boundaries",
    "test_multiple_pastes_submission",
    "test_partial_placeholder_deletion",
    "test_placeholder_deletion",
    "type_chars_humanlike",
    "ui_snapshots",
    "user_input_too_large_message",
    "vim_insert_uses_bar_cursor_style",
    "vim_mode_resets_to_normal_after_queued_submission",
    "vim_mode_resets_to_normal_after_submission",
    "vim_mode_stays_insert_after_suppressed_submission",
    "vim_normal_history_navigation_from_start_of_bang_command_recalls_older_entry",
    "vim_normal_j_k_fall_back_to_multiline_cursor_movement",
    "vim_normal_j_k_navigate_history_at_history_boundaries",
    "vim_normal_operator_motion_does_not_navigate_history",
    "vim_normal_operator_pending_consumes_submit_key",
]
