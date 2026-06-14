"""Python interface scaffold for Rust ``codex-tui::keymap_setup``.

Upstream source: ``codex/codex-rs/tui/src/keymap_setup.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="keymap_setup", source="codex/codex-rs/tui/src/keymap_setup.rs")

KEYMAP_ACTION_MENU_VIEW_ID: Any = None

KEYMAP_REPLACE_BINDING_MENU_VIEW_ID: Any = None

class KeymapEditOutcome(Enum):
    """Python boundary for Rust enum ``keymap_setup::KeymapEditOutcome``."""
    UNPORTED = "unported"

def key_binding_span(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_binding_span``."""
    return not_ported(RUST_MODULE, "key_binding_span")

def keymap_action_menu_hint_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_action_menu_hint_line``."""
    return not_ported(RUST_MODULE, "keymap_action_menu_hint_line")

def open_capture_action(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::open_capture_action``."""
    return not_ported(RUST_MODULE, "open_capture_action")

def action_menu_item(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::action_menu_item``."""
    return not_ported(RUST_MODULE, "action_menu_item")

def build_keymap_action_menu_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::build_keymap_action_menu_params``."""
    return not_ported(RUST_MODULE, "build_keymap_action_menu_params")

def build_keymap_replace_binding_menu_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::build_keymap_replace_binding_menu_params``."""
    return not_ported(RUST_MODULE, "build_keymap_replace_binding_menu_params")

def build_keymap_conflict_params(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::build_keymap_conflict_params``."""
    return not_ported(RUST_MODULE, "build_keymap_conflict_params")

def build_keymap_capture_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::build_keymap_capture_view``."""
    return not_ported(RUST_MODULE, "build_keymap_capture_view")

def keymap_with_replacement(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_with_replacement``."""
    return not_ported(RUST_MODULE, "keymap_with_replacement")

def keymap_with_edit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_with_edit``."""
    return not_ported(RUST_MODULE, "keymap_with_edit")

def keymap_with_bindings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_with_bindings``."""
    return not_ported(RUST_MODULE, "keymap_with_bindings")

def active_binding_specs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::active_binding_specs``."""
    return not_ported(RUST_MODULE, "active_binding_specs")

def dedup_bindings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::dedup_bindings``."""
    return not_ported(RUST_MODULE, "dedup_bindings")

def keymap_without_custom_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_without_custom_binding``."""
    return not_ported(RUST_MODULE, "keymap_without_custom_binding")

def has_custom_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::has_custom_binding``."""
    return not_ported(RUST_MODULE, "has_custom_binding")

@dataclass
class KeymapCaptureView:
    """Python boundary for Rust ``keymap_setup::KeymapCaptureView``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "KeymapCaptureView.new")

    def lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "KeymapCaptureView.lines")

def render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render``."""
    return not_ported(RUST_MODULE, "render")

def desired_height(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::desired_height``."""
    return not_ported(RUST_MODULE, "desired_height")

def handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::handle_key_event``."""
    return not_ported(RUST_MODULE, "handle_key_event")

def is_complete(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::is_complete``."""
    return not_ported(RUST_MODULE, "is_complete")

def on_ctrl_c(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::on_ctrl_c``."""
    return not_ported(RUST_MODULE, "on_ctrl_c")

def prefer_esc_to_handle_key_event(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::prefer_esc_to_handle_key_event``."""
    return not_ported(RUST_MODULE, "prefer_esc_to_handle_key_event")

def key_event_to_config_key_spec(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_event_to_config_key_spec``."""
    return not_ported(RUST_MODULE, "key_event_to_config_key_spec")

def binding_to_config_key_spec(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::binding_to_config_key_spec``."""
    return not_ported(RUST_MODULE, "binding_to_config_key_spec")

def key_parts_to_config_key_spec(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_parts_to_config_key_spec``."""
    return not_ported(RUST_MODULE, "key_parts_to_config_key_spec")

def format_key_spec(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::format_key_spec``."""
    return not_ported(RUST_MODULE, "format_key_spec")

def app_event_sender(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::app_event_sender``."""
    return not_ported(RUST_MODULE, "app_event_sender")

def render_capture(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render_capture``."""
    return not_ported(RUST_MODULE, "render_capture")

def render_debug(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render_debug``."""
    return not_ported(RUST_MODULE, "render_debug")

def render_picker(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render_picker``."""
    return not_ported(RUST_MODULE, "render_picker")

def render_picker_from_view(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render_picker_from_view``."""
    return not_ported(RUST_MODULE, "render_picker_from_view")

def fast_mode_action_filter(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::fast_mode_action_filter``."""
    return not_ported(RUST_MODULE, "fast_mode_action_filter")

def render_buffer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::render_buffer``."""
    return not_ported(RUST_MODULE, "render_buffer")

def test_pane(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::test_pane``."""
    return not_ported(RUST_MODULE, "test_pane")

def selection_tab(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::selection_tab``."""
    return not_ported(RUST_MODULE, "selection_tab")

def selection_item(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::selection_item``."""
    return not_ported(RUST_MODULE, "selection_item")

def action_menu_rows(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::action_menu_rows``."""
    return not_ported(RUST_MODULE, "action_menu_rows")

def picker_covers_every_replaceable_action(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_covers_every_replaceable_action``."""
    return not_ported(RUST_MODULE, "picker_covers_every_replaceable_action")

def picker_hides_fast_mode_action_when_feature_is_disabled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_hides_fast_mode_action_when_feature_is_disabled``."""
    return not_ported(RUST_MODULE, "picker_hides_fast_mode_action_when_feature_is_disabled")

def picker_shows_fast_mode_action_when_feature_is_enabled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_shows_fast_mode_action_when_feature_is_enabled``."""
    return not_ported(RUST_MODULE, "picker_shows_fast_mode_action_when_feature_is_enabled")

def keymap_picker_fast_mode_enabled_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::keymap_picker_fast_mode_enabled_snapshot``."""
    return not_ported(RUST_MODULE, "keymap_picker_fast_mode_enabled_snapshot")

def picker_common_tab_lists_curated_actions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_common_tab_lists_curated_actions``."""
    return not_ported(RUST_MODULE, "picker_common_tab_lists_curated_actions")

def picker_approval_tab_lists_all_approval_actions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_approval_tab_lists_all_approval_actions``."""
    return not_ported(RUST_MODULE, "picker_approval_tab_lists_all_approval_actions")

def picker_content_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_content_snapshot``."""
    return not_ported(RUST_MODULE, "picker_content_snapshot")

def picker_customized_tab_contains_root_overrides(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_customized_tab_contains_root_overrides``."""
    return not_ported(RUST_MODULE, "picker_customized_tab_contains_root_overrides")

def picker_unbound_tab_lists_default_unbound_actions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_unbound_tab_lists_default_unbound_actions``."""
    return not_ported(RUST_MODULE, "picker_unbound_tab_lists_default_unbound_actions")

def picker_debug_tab_is_last_and_opens_inspector(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_debug_tab_is_last_and_opens_inspector``."""
    return not_ported(RUST_MODULE, "picker_debug_tab_is_last_and_opens_inspector")

def picker_selected_action_starts_on_matching_all_tab_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_selected_action_starts_on_matching_all_tab_row``."""
    return not_ported(RUST_MODULE, "picker_selected_action_starts_on_matching_all_tab_row")

def picker_all_tab_items_remain_searchable(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_all_tab_items_remain_searchable``."""
    return not_ported(RUST_MODULE, "picker_all_tab_items_remain_searchable")

def picker_wide_render_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_wide_render_snapshot``."""
    return not_ported(RUST_MODULE, "picker_wide_render_snapshot")

def picker_narrow_render_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_narrow_render_snapshot``."""
    return not_ported(RUST_MODULE, "picker_narrow_render_snapshot")

def picker_custom_render_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_custom_render_snapshot``."""
    return not_ported(RUST_MODULE, "picker_custom_render_snapshot")

def picker_narrow_uses_compact_tabs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::picker_narrow_uses_compact_tabs``."""
    return not_ported(RUST_MODULE, "picker_narrow_uses_compact_tabs")

def action_menu_content_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::action_menu_content_snapshot``."""
    return not_ported(RUST_MODULE, "action_menu_content_snapshot")

def action_menu_disables_clear_when_action_has_no_custom_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::action_menu_disables_clear_when_action_has_no_custom_binding``."""
    return not_ported(RUST_MODULE, "action_menu_disables_clear_when_action_has_no_custom_binding")

def capture_view_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::capture_view_snapshot``."""
    return not_ported(RUST_MODULE, "capture_view_snapshot")

def debug_view_initial_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::debug_view_initial_snapshot``."""
    return not_ported(RUST_MODULE, "debug_view_initial_snapshot")

def debug_view_shows_delayed_missing_key_hint(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::debug_view_shows_delayed_missing_key_hint``."""
    return not_ported(RUST_MODULE, "debug_view_shows_delayed_missing_key_hint")

def debug_view_reports_detected_key_and_matching_actions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::debug_view_reports_detected_key_and_matching_actions``."""
    return not_ported(RUST_MODULE, "debug_view_reports_detected_key_and_matching_actions")

def debug_view_uses_custom_binding_source(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::debug_view_uses_custom_binding_source``."""
    return not_ported(RUST_MODULE, "debug_view_uses_custom_binding_source")

def debug_view_labels_custom_global_fallback_source(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::debug_view_labels_custom_global_fallback_source``."""
    return not_ported(RUST_MODULE, "debug_view_labels_custom_global_fallback_source")

def capture_completion_returns_to_selected_keymap_picker_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::capture_completion_returns_to_selected_keymap_picker_row``."""
    return not_ported(RUST_MODULE, "capture_completion_returns_to_selected_keymap_picker_row")

def clear_completion_returns_to_selected_keymap_picker_row(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::clear_completion_returns_to_selected_keymap_picker_row``."""
    return not_ported(RUST_MODULE, "clear_completion_returns_to_selected_keymap_picker_row")

def replace_one_completion_drops_focused_keymap_submenus(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replace_one_completion_drops_focused_keymap_submenus``."""
    return not_ported(RUST_MODULE, "replace_one_completion_drops_focused_keymap_submenus")

def key_capture_serializes_modifier_order_for_config(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_capture_serializes_modifier_order_for_config``."""
    return not_ported(RUST_MODULE, "key_capture_serializes_modifier_order_for_config")

def key_capture_serializes_special_keys(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_capture_serializes_special_keys``."""
    return not_ported(RUST_MODULE, "key_capture_serializes_special_keys")

def key_capture_serializes_c0_control_chars_as_ctrl_bindings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_capture_serializes_c0_control_chars_as_ctrl_bindings``."""
    return not_ported(RUST_MODULE, "key_capture_serializes_c0_control_chars_as_ctrl_bindings")

def key_capture_serializes_minus_as_named_key(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::key_capture_serializes_minus_as_named_key``."""
    return not_ported(RUST_MODULE, "key_capture_serializes_minus_as_named_key")

def replacement_sets_single_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replacement_sets_single_binding``."""
    return not_ported(RUST_MODULE, "replacement_sets_single_binding")

def replace_all_collapses_multi_binding_to_single(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replace_all_collapses_multi_binding_to_single``."""
    return not_ported(RUST_MODULE, "replace_all_collapses_multi_binding_to_single")

def add_alternate_grows_single_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::add_alternate_grows_single_binding``."""
    return not_ported(RUST_MODULE, "add_alternate_grows_single_binding")

def add_alternate_grows_default_multi_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::add_alternate_grows_default_multi_binding``."""
    return not_ported(RUST_MODULE, "add_alternate_grows_default_multi_binding")

def add_alternate_duplicate_is_noop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::add_alternate_duplicate_is_noop``."""
    return not_ported(RUST_MODULE, "add_alternate_duplicate_is_noop")

def replace_one_preserves_other_bindings(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replace_one_preserves_other_bindings``."""
    return not_ported(RUST_MODULE, "replace_one_preserves_other_bindings")

def replace_one_deduplicates_replacement(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replace_one_deduplicates_replacement``."""
    return not_ported(RUST_MODULE, "replace_one_deduplicates_replacement")

def replace_one_rejects_stale_old_key(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replace_one_rejects_stale_old_key``."""
    return not_ported(RUST_MODULE, "replace_one_rejects_stale_old_key")

def clear_removes_custom_binding(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::clear_removes_custom_binding``."""
    return not_ported(RUST_MODULE, "clear_removes_custom_binding")

def replacement_rejects_unknown_action(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``keymap_setup::replacement_rejects_unknown_action``."""
    return not_ported(RUST_MODULE, "replacement_rejects_unknown_action")

__all__ = [
    "KEYMAP_ACTION_MENU_VIEW_ID",
    "KEYMAP_REPLACE_BINDING_MENU_VIEW_ID",
    "KeymapCaptureView",
    "KeymapEditOutcome",
    "RUST_MODULE",
    "action_menu_content_snapshot",
    "action_menu_disables_clear_when_action_has_no_custom_binding",
    "action_menu_item",
    "action_menu_rows",
    "active_binding_specs",
    "add_alternate_duplicate_is_noop",
    "add_alternate_grows_default_multi_binding",
    "add_alternate_grows_single_binding",
    "app_event_sender",
    "binding_to_config_key_spec",
    "build_keymap_action_menu_params",
    "build_keymap_capture_view",
    "build_keymap_conflict_params",
    "build_keymap_replace_binding_menu_params",
    "capture_completion_returns_to_selected_keymap_picker_row",
    "capture_view_snapshot",
    "clear_completion_returns_to_selected_keymap_picker_row",
    "clear_removes_custom_binding",
    "debug_view_initial_snapshot",
    "debug_view_labels_custom_global_fallback_source",
    "debug_view_reports_detected_key_and_matching_actions",
    "debug_view_shows_delayed_missing_key_hint",
    "debug_view_uses_custom_binding_source",
    "dedup_bindings",
    "desired_height",
    "fast_mode_action_filter",
    "format_key_spec",
    "handle_key_event",
    "has_custom_binding",
    "is_complete",
    "key_binding_span",
    "key_capture_serializes_c0_control_chars_as_ctrl_bindings",
    "key_capture_serializes_minus_as_named_key",
    "key_capture_serializes_modifier_order_for_config",
    "key_capture_serializes_special_keys",
    "key_event_to_config_key_spec",
    "key_parts_to_config_key_spec",
    "keymap_action_menu_hint_line",
    "keymap_picker_fast_mode_enabled_snapshot",
    "keymap_with_bindings",
    "keymap_with_edit",
    "keymap_with_replacement",
    "keymap_without_custom_binding",
    "on_ctrl_c",
    "open_capture_action",
    "picker_all_tab_items_remain_searchable",
    "picker_approval_tab_lists_all_approval_actions",
    "picker_common_tab_lists_curated_actions",
    "picker_content_snapshot",
    "picker_covers_every_replaceable_action",
    "picker_custom_render_snapshot",
    "picker_customized_tab_contains_root_overrides",
    "picker_debug_tab_is_last_and_opens_inspector",
    "picker_hides_fast_mode_action_when_feature_is_disabled",
    "picker_narrow_render_snapshot",
    "picker_narrow_uses_compact_tabs",
    "picker_selected_action_starts_on_matching_all_tab_row",
    "picker_shows_fast_mode_action_when_feature_is_enabled",
    "picker_unbound_tab_lists_default_unbound_actions",
    "picker_wide_render_snapshot",
    "prefer_esc_to_handle_key_event",
    "render",
    "render_buffer",
    "render_capture",
    "render_debug",
    "render_picker",
    "render_picker_from_view",
    "replace_all_collapses_multi_binding_to_single",
    "replace_one_completion_drops_focused_keymap_submenus",
    "replace_one_deduplicates_replacement",
    "replace_one_preserves_other_bindings",
    "replace_one_rejects_stale_old_key",
    "replacement_rejects_unknown_action",
    "replacement_sets_single_binding",
    "selection_item",
    "selection_tab",
    "test_pane",
]
