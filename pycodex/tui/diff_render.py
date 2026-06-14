"""Python interface scaffold for Rust ``codex-tui::diff_render``.

Upstream source: ``codex/codex-rs/tui/src/diff_render.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="diff_render", source="codex/codex-rs/tui/src/diff_render.rs")

TAB_WIDTH: Any = None

DARK_TC_ADD_LINE_BG_RGB: Any = None

DARK_TC_DEL_LINE_BG_RGB: Any = None

LIGHT_TC_ADD_LINE_BG_RGB: Any = None

LIGHT_TC_DEL_LINE_BG_RGB: Any = None

LIGHT_TC_ADD_NUM_BG_RGB: Any = None

LIGHT_TC_DEL_NUM_BG_RGB: Any = None

LIGHT_TC_GUTTER_FG_RGB: Any = None

DARK_256_ADD_LINE_BG_IDX: Any = None

DARK_256_DEL_LINE_BG_IDX: Any = None

LIGHT_256_ADD_LINE_BG_IDX: Any = None

LIGHT_256_DEL_LINE_BG_IDX: Any = None

LIGHT_256_ADD_NUM_BG_IDX: Any = None

LIGHT_256_DEL_NUM_BG_IDX: Any = None

LIGHT_256_GUTTER_FG_IDX: Any = None

class DiffLineType(Enum):
    """Python boundary for Rust enum ``diff_render::DiffLineType``."""
    UNPORTED = "unported"

class DiffTheme(Enum):
    """Python boundary for Rust enum ``diff_render::DiffTheme``."""
    UNPORTED = "unported"

class DiffColorLevel(Enum):
    """Python boundary for Rust enum ``diff_render::DiffColorLevel``."""
    UNPORTED = "unported"

class RichDiffColorLevel(Enum):
    """Python boundary for Rust enum ``diff_render::RichDiffColorLevel``."""
    UNPORTED = "unported"

@dataclass
class ResolvedDiffBackgrounds:
    """Python boundary for Rust ``diff_render::ResolvedDiffBackgrounds``."""
    _payload: Any = None

@dataclass
class DiffRenderStyleContext:
    """Python boundary for Rust ``diff_render::DiffRenderStyleContext``."""
    _payload: Any = None

def resolve_diff_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::resolve_diff_backgrounds``."""
    return not_ported(RUST_MODULE, "resolve_diff_backgrounds")

def current_diff_render_style_context(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::current_diff_render_style_context``."""
    return not_ported(RUST_MODULE, "current_diff_render_style_context")

def resolve_diff_backgrounds_for(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::resolve_diff_backgrounds_for``."""
    return not_ported(RUST_MODULE, "resolve_diff_backgrounds_for")

def fallback_diff_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::fallback_diff_backgrounds``."""
    return not_ported(RUST_MODULE, "fallback_diff_backgrounds")

def color_from_rgb_for_level(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::color_from_rgb_for_level``."""
    return not_ported(RUST_MODULE, "color_from_rgb_for_level")

def quantize_rgb_to_ansi256(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::quantize_rgb_to_ansi256``."""
    return not_ported(RUST_MODULE, "quantize_rgb_to_ansi256")

@dataclass
class DiffSummary:
    """Python boundary for Rust ``diff_render::DiffSummary``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "DiffSummary.new")

def render(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::render``."""
    return not_ported(RUST_MODULE, "render")

def desired_height(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::desired_height``."""
    return not_ported(RUST_MODULE, "desired_height")

def from_(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::from``."""
    return not_ported(RUST_MODULE, "from")

def create_diff_summary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::create_diff_summary``."""
    return not_ported(RUST_MODULE, "create_diff_summary")

@dataclass
class Row:
    """Python boundary for Rust ``diff_render::Row``."""
    _payload: Any = None

def collect_rows(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::collect_rows``."""
    return not_ported(RUST_MODULE, "collect_rows")

def render_line_count_summary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::render_line_count_summary``."""
    return not_ported(RUST_MODULE, "render_line_count_summary")

def render_changes_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::render_changes_block``."""
    return not_ported(RUST_MODULE, "render_changes_block")

def detect_lang_for_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::detect_lang_for_path``."""
    return not_ported(RUST_MODULE, "detect_lang_for_path")

def render_change(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::render_change``."""
    return not_ported(RUST_MODULE, "render_change")

def display_path_for(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::display_path_for``."""
    return not_ported(RUST_MODULE, "display_path_for")

def calculate_add_remove_from_diff(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::calculate_add_remove_from_diff``."""
    return not_ported(RUST_MODULE, "calculate_add_remove_from_diff")

def push_wrapped_diff_line_with_style_context(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::push_wrapped_diff_line_with_style_context``."""
    return not_ported(RUST_MODULE, "push_wrapped_diff_line_with_style_context")

def push_wrapped_diff_line_with_syntax_and_style_context(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::push_wrapped_diff_line_with_syntax_and_style_context``."""
    return not_ported(RUST_MODULE, "push_wrapped_diff_line_with_syntax_and_style_context")

def push_wrapped_diff_line_inner_with_theme_and_color_level(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::push_wrapped_diff_line_inner_with_theme_and_color_level``."""
    return not_ported(RUST_MODULE, "push_wrapped_diff_line_inner_with_theme_and_color_level")

def wrap_styled_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans")

def line_number_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::line_number_width``."""
    return not_ported(RUST_MODULE, "line_number_width")

def diff_theme_for_bg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_theme_for_bg``."""
    return not_ported(RUST_MODULE, "diff_theme_for_bg")

def diff_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_theme``."""
    return not_ported(RUST_MODULE, "diff_theme")

def diff_color_level(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_color_level``."""
    return not_ported(RUST_MODULE, "diff_color_level")

def has_force_color_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::has_force_color_override``."""
    return not_ported(RUST_MODULE, "has_force_color_override")

def diff_color_level_for_terminal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_color_level_for_terminal``."""
    return not_ported(RUST_MODULE, "diff_color_level_for_terminal")

def style_line_bg_for(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_line_bg_for``."""
    return not_ported(RUST_MODULE, "style_line_bg_for")

def style_context(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_context``."""
    return not_ported(RUST_MODULE, "style_context")

def add_line_bg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::add_line_bg``."""
    return not_ported(RUST_MODULE, "add_line_bg")

def del_line_bg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::del_line_bg``."""
    return not_ported(RUST_MODULE, "del_line_bg")

def light_gutter_fg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::light_gutter_fg``."""
    return not_ported(RUST_MODULE, "light_gutter_fg")

def light_add_num_bg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::light_add_num_bg``."""
    return not_ported(RUST_MODULE, "light_add_num_bg")

def light_del_num_bg(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::light_del_num_bg``."""
    return not_ported(RUST_MODULE, "light_del_num_bg")

def style_gutter_for(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_gutter_for``."""
    return not_ported(RUST_MODULE, "style_gutter_for")

def style_sign_add(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_sign_add``."""
    return not_ported(RUST_MODULE, "style_sign_add")

def style_sign_del(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_sign_del``."""
    return not_ported(RUST_MODULE, "style_sign_del")

def style_add(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_add``."""
    return not_ported(RUST_MODULE, "style_add")

def style_del(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_del``."""
    return not_ported(RUST_MODULE, "style_del")

def style_gutter_dim(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::style_gutter_dim``."""
    return not_ported(RUST_MODULE, "style_gutter_dim")

def ansi16_add_style_uses_foreground_only(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ansi16_add_style_uses_foreground_only``."""
    return not_ported(RUST_MODULE, "ansi16_add_style_uses_foreground_only")

def ansi16_del_style_uses_foreground_only(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ansi16_del_style_uses_foreground_only``."""
    return not_ported(RUST_MODULE, "ansi16_del_style_uses_foreground_only")

def ansi16_sign_styles_use_foreground_only(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ansi16_sign_styles_use_foreground_only``."""
    return not_ported(RUST_MODULE, "ansi16_sign_styles_use_foreground_only")

def diff_summary_for_tests(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_summary_for_tests``."""
    return not_ported(RUST_MODULE, "diff_summary_for_tests")

def snapshot_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::snapshot_lines``."""
    return not_ported(RUST_MODULE, "snapshot_lines")

def display_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::display_width``."""
    return not_ported(RUST_MODULE, "display_width")

def line_display_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::line_display_width``."""
    return not_ported(RUST_MODULE, "line_display_width")

def snapshot_lines_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::snapshot_lines_text``."""
    return not_ported(RUST_MODULE, "snapshot_lines_text")

def diff_gallery_changes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::diff_gallery_changes``."""
    return not_ported(RUST_MODULE, "diff_gallery_changes")

def snapshot_diff_gallery(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::snapshot_diff_gallery``."""
    return not_ported(RUST_MODULE, "snapshot_diff_gallery")

def display_path_prefers_cwd_without_git_repo(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::display_path_prefers_cwd_without_git_repo``."""
    return not_ported(RUST_MODULE, "display_path_prefers_cwd_without_git_repo")

def ui_snapshot_wrap_behavior_insert(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_wrap_behavior_insert``."""
    return not_ported(RUST_MODULE, "ui_snapshot_wrap_behavior_insert")

def ui_snapshot_apply_update_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_block``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_block")

def ui_snapshot_apply_update_with_rename_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_with_rename_block``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_with_rename_block")

def ui_snapshot_apply_multiple_files_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_multiple_files_block``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_multiple_files_block")

def ui_snapshot_apply_add_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_add_block``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_add_block")

def ui_snapshot_apply_delete_block(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_delete_block``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_delete_block")

def ui_snapshot_apply_update_block_wraps_long_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_block_wraps_long_lines``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_block_wraps_long_lines")

def ui_snapshot_apply_update_block_wraps_long_lines_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_block_wraps_long_lines_text``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_block_wraps_long_lines_text")

def ui_snapshot_apply_update_block_line_numbers_three_digits_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_block_line_numbers_three_digits_text``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_block_line_numbers_three_digits_text")

def ui_snapshot_apply_update_block_relativizes_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_apply_update_block_relativizes_path``."""
    return not_ported(RUST_MODULE, "ui_snapshot_apply_update_block_relativizes_path")

def ui_snapshot_syntax_highlighted_insert_wraps(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_syntax_highlighted_insert_wraps``."""
    return not_ported(RUST_MODULE, "ui_snapshot_syntax_highlighted_insert_wraps")

def ui_snapshot_syntax_highlighted_insert_wraps_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_syntax_highlighted_insert_wraps_text``."""
    return not_ported(RUST_MODULE, "ui_snapshot_syntax_highlighted_insert_wraps_text")

def ui_snapshot_diff_gallery_80x24(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_diff_gallery_80x24``."""
    return not_ported(RUST_MODULE, "ui_snapshot_diff_gallery_80x24")

def ui_snapshot_diff_gallery_94x35(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_diff_gallery_94x35``."""
    return not_ported(RUST_MODULE, "ui_snapshot_diff_gallery_94x35")

def ui_snapshot_diff_gallery_120x40(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_diff_gallery_120x40``."""
    return not_ported(RUST_MODULE, "ui_snapshot_diff_gallery_120x40")

def ui_snapshot_ansi16_insert_delete_no_background(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_ansi16_insert_delete_no_background``."""
    return not_ported(RUST_MODULE, "ui_snapshot_ansi16_insert_delete_no_background")

def truecolor_dark_theme_uses_configured_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::truecolor_dark_theme_uses_configured_backgrounds``."""
    return not_ported(RUST_MODULE, "truecolor_dark_theme_uses_configured_backgrounds")

def ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds``."""
    return not_ported(RUST_MODULE, "ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds")

def theme_scope_backgrounds_override_truecolor_fallback_when_available(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::theme_scope_backgrounds_override_truecolor_fallback_when_available``."""
    return not_ported(RUST_MODULE, "theme_scope_backgrounds_override_truecolor_fallback_when_available")

def theme_scope_backgrounds_quantize_to_ansi256(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::theme_scope_backgrounds_quantize_to_ansi256``."""
    return not_ported(RUST_MODULE, "theme_scope_backgrounds_quantize_to_ansi256")

def ui_snapshot_theme_scope_background_resolution(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ui_snapshot_theme_scope_background_resolution``."""
    return not_ported(RUST_MODULE, "ui_snapshot_theme_scope_background_resolution")

def ansi16_disables_line_and_gutter_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::ansi16_disables_line_and_gutter_backgrounds``."""
    return not_ported(RUST_MODULE, "ansi16_disables_line_and_gutter_backgrounds")

def light_truecolor_theme_uses_readable_gutter_and_line_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::light_truecolor_theme_uses_readable_gutter_and_line_backgrounds``."""
    return not_ported(RUST_MODULE, "light_truecolor_theme_uses_readable_gutter_and_line_backgrounds")

def light_theme_wrapped_lines_keep_number_gutter_contrast(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::light_theme_wrapped_lines_keep_number_gutter_contrast``."""
    return not_ported(RUST_MODULE, "light_theme_wrapped_lines_keep_number_gutter_contrast")

def windows_terminal_promotes_ansi16_to_truecolor_for_diffs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::windows_terminal_promotes_ansi16_to_truecolor_for_diffs``."""
    return not_ported(RUST_MODULE, "windows_terminal_promotes_ansi16_to_truecolor_for_diffs")

def wt_session_promotes_ansi16_to_truecolor_for_diffs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wt_session_promotes_ansi16_to_truecolor_for_diffs``."""
    return not_ported(RUST_MODULE, "wt_session_promotes_ansi16_to_truecolor_for_diffs")

def non_windows_terminal_keeps_ansi16_diff_palette(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::non_windows_terminal_keeps_ansi16_diff_palette``."""
    return not_ported(RUST_MODULE, "non_windows_terminal_keeps_ansi16_diff_palette")

def wt_session_promotes_unknown_color_level_to_truecolor(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wt_session_promotes_unknown_color_level_to_truecolor``."""
    return not_ported(RUST_MODULE, "wt_session_promotes_unknown_color_level_to_truecolor")

def non_wt_windows_terminal_keeps_unknown_color_level_conservative(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::non_wt_windows_terminal_keeps_unknown_color_level_conservative``."""
    return not_ported(RUST_MODULE, "non_wt_windows_terminal_keeps_unknown_color_level_conservative")

def explicit_force_override_keeps_ansi16_on_windows_terminal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::explicit_force_override_keeps_ansi16_on_windows_terminal``."""
    return not_ported(RUST_MODULE, "explicit_force_override_keeps_ansi16_on_windows_terminal")

def explicit_force_override_keeps_ansi256_on_windows_terminal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::explicit_force_override_keeps_ansi256_on_windows_terminal``."""
    return not_ported(RUST_MODULE, "explicit_force_override_keeps_ansi256_on_windows_terminal")

def add_diff_uses_path_extension_for_highlighting(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::add_diff_uses_path_extension_for_highlighting``."""
    return not_ported(RUST_MODULE, "add_diff_uses_path_extension_for_highlighting")

def delete_diff_uses_path_extension_for_highlighting(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::delete_diff_uses_path_extension_for_highlighting``."""
    return not_ported(RUST_MODULE, "delete_diff_uses_path_extension_for_highlighting")

def detect_lang_for_common_paths(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::detect_lang_for_common_paths``."""
    return not_ported(RUST_MODULE, "detect_lang_for_common_paths")

def wrap_styled_spans_single_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_single_line``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_single_line")

def wrap_styled_spans_splits_long_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_splits_long_content``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_splits_long_content")

def wrap_styled_spans_flushes_at_span_boundary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_flushes_at_span_boundary``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_flushes_at_span_boundary")

def wrap_styled_spans_preserves_styles(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_preserves_styles``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_preserves_styles")

def wrap_styled_spans_tabs_have_visible_width(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_tabs_have_visible_width``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_tabs_have_visible_width")

def wrap_styled_spans_wraps_before_first_overflowing_char(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::wrap_styled_spans_wraps_before_first_overflowing_char``."""
    return not_ported(RUST_MODULE, "wrap_styled_spans_wraps_before_first_overflowing_char")

def fallback_wrapping_uses_display_width_for_tabs_and_wide_chars(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::fallback_wrapping_uses_display_width_for_tabs_and_wide_chars``."""
    return not_ported(RUST_MODULE, "fallback_wrapping_uses_display_width_for_tabs_and_wide_chars")

def large_update_diff_skips_highlighting(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::large_update_diff_skips_highlighting``."""
    return not_ported(RUST_MODULE, "large_update_diff_skips_highlighting")

def rename_diff_uses_destination_extension_for_highlighting(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::rename_diff_uses_destination_extension_for_highlighting``."""
    return not_ported(RUST_MODULE, "rename_diff_uses_destination_extension_for_highlighting")

def update_diff_preserves_multiline_highlight_state_within_hunk(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``diff_render::update_diff_preserves_multiline_highlight_state_within_hunk``."""
    return not_ported(RUST_MODULE, "update_diff_preserves_multiline_highlight_state_within_hunk")

__all__ = [
    "DARK_256_ADD_LINE_BG_IDX",
    "DARK_256_DEL_LINE_BG_IDX",
    "DARK_TC_ADD_LINE_BG_RGB",
    "DARK_TC_DEL_LINE_BG_RGB",
    "DiffColorLevel",
    "DiffLineType",
    "DiffRenderStyleContext",
    "DiffSummary",
    "DiffTheme",
    "LIGHT_256_ADD_LINE_BG_IDX",
    "LIGHT_256_ADD_NUM_BG_IDX",
    "LIGHT_256_DEL_LINE_BG_IDX",
    "LIGHT_256_DEL_NUM_BG_IDX",
    "LIGHT_256_GUTTER_FG_IDX",
    "LIGHT_TC_ADD_LINE_BG_RGB",
    "LIGHT_TC_ADD_NUM_BG_RGB",
    "LIGHT_TC_DEL_LINE_BG_RGB",
    "LIGHT_TC_DEL_NUM_BG_RGB",
    "LIGHT_TC_GUTTER_FG_RGB",
    "RUST_MODULE",
    "ResolvedDiffBackgrounds",
    "RichDiffColorLevel",
    "Row",
    "TAB_WIDTH",
    "add_diff_uses_path_extension_for_highlighting",
    "add_line_bg",
    "ansi16_add_style_uses_foreground_only",
    "ansi16_del_style_uses_foreground_only",
    "ansi16_disables_line_and_gutter_backgrounds",
    "ansi16_sign_styles_use_foreground_only",
    "ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds",
    "calculate_add_remove_from_diff",
    "collect_rows",
    "color_from_rgb_for_level",
    "create_diff_summary",
    "current_diff_render_style_context",
    "del_line_bg",
    "delete_diff_uses_path_extension_for_highlighting",
    "desired_height",
    "detect_lang_for_common_paths",
    "detect_lang_for_path",
    "diff_color_level",
    "diff_color_level_for_terminal",
    "diff_gallery_changes",
    "diff_summary_for_tests",
    "diff_theme",
    "diff_theme_for_bg",
    "display_path_for",
    "display_path_prefers_cwd_without_git_repo",
    "display_width",
    "explicit_force_override_keeps_ansi16_on_windows_terminal",
    "explicit_force_override_keeps_ansi256_on_windows_terminal",
    "fallback_diff_backgrounds",
    "fallback_wrapping_uses_display_width_for_tabs_and_wide_chars",
    "from_",
    "has_force_color_override",
    "large_update_diff_skips_highlighting",
    "light_add_num_bg",
    "light_del_num_bg",
    "light_gutter_fg",
    "light_theme_wrapped_lines_keep_number_gutter_contrast",
    "light_truecolor_theme_uses_readable_gutter_and_line_backgrounds",
    "line_display_width",
    "line_number_width",
    "non_windows_terminal_keeps_ansi16_diff_palette",
    "non_wt_windows_terminal_keeps_unknown_color_level_conservative",
    "push_wrapped_diff_line_inner_with_theme_and_color_level",
    "push_wrapped_diff_line_with_style_context",
    "push_wrapped_diff_line_with_syntax_and_style_context",
    "quantize_rgb_to_ansi256",
    "rename_diff_uses_destination_extension_for_highlighting",
    "render",
    "render_change",
    "render_changes_block",
    "render_line_count_summary",
    "resolve_diff_backgrounds",
    "resolve_diff_backgrounds_for",
    "snapshot_diff_gallery",
    "snapshot_lines",
    "snapshot_lines_text",
    "style_add",
    "style_context",
    "style_del",
    "style_gutter_dim",
    "style_gutter_for",
    "style_line_bg_for",
    "style_sign_add",
    "style_sign_del",
    "theme_scope_backgrounds_override_truecolor_fallback_when_available",
    "theme_scope_backgrounds_quantize_to_ansi256",
    "truecolor_dark_theme_uses_configured_backgrounds",
    "ui_snapshot_ansi16_insert_delete_no_background",
    "ui_snapshot_apply_add_block",
    "ui_snapshot_apply_delete_block",
    "ui_snapshot_apply_multiple_files_block",
    "ui_snapshot_apply_update_block",
    "ui_snapshot_apply_update_block_line_numbers_three_digits_text",
    "ui_snapshot_apply_update_block_relativizes_path",
    "ui_snapshot_apply_update_block_wraps_long_lines",
    "ui_snapshot_apply_update_block_wraps_long_lines_text",
    "ui_snapshot_apply_update_with_rename_block",
    "ui_snapshot_diff_gallery_120x40",
    "ui_snapshot_diff_gallery_80x24",
    "ui_snapshot_diff_gallery_94x35",
    "ui_snapshot_syntax_highlighted_insert_wraps",
    "ui_snapshot_syntax_highlighted_insert_wraps_text",
    "ui_snapshot_theme_scope_background_resolution",
    "ui_snapshot_wrap_behavior_insert",
    "update_diff_preserves_multiline_highlight_state_within_hunk",
    "windows_terminal_promotes_ansi16_to_truecolor_for_diffs",
    "wrap_styled_spans",
    "wrap_styled_spans_flushes_at_span_boundary",
    "wrap_styled_spans_preserves_styles",
    "wrap_styled_spans_single_line",
    "wrap_styled_spans_splits_long_content",
    "wrap_styled_spans_tabs_have_visible_width",
    "wrap_styled_spans_wraps_before_first_overflowing_char",
    "wt_session_promotes_ansi16_to_truecolor_for_diffs",
    "wt_session_promotes_unknown_color_level_to_truecolor",
]
#
# Semantic Python parity slice for Rust `codex-rs/tui/src/diff_render.rs`.
#
# The scaffold above keeps names for the full ratatui/diffy renderer.  The
# definitions below intentionally override the placeholder objects for the
# dependency-light part of the Rust module: diff color levels, theme background
# resolution, terminal color-level promotion, path language hints, and styled
# span wrapping.  The full `FileChange`/ratatui render pipeline remains a
# separate boundary because it depends on upstream UI buffer types.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
import unicodedata
from typing import Iterable, Sequence


TAB_WIDTH = 4

DARK_TC_ADD_LINE_BG_RGB = (33, 58, 43)
DARK_TC_DEL_LINE_BG_RGB = (74, 34, 29)
LIGHT_TC_ADD_LINE_BG_RGB = (218, 251, 225)
LIGHT_TC_DEL_LINE_BG_RGB = (255, 235, 233)
LIGHT_TC_ADD_NUM_BG_RGB = (172, 238, 187)
LIGHT_TC_DEL_NUM_BG_RGB = (255, 206, 203)
LIGHT_TC_GUTTER_FG_RGB = (31, 35, 40)

DARK_256_ADD_LINE_BG_IDX = 22
DARK_256_DEL_LINE_BG_IDX = 52
LIGHT_256_ADD_LINE_BG_IDX = 194
LIGHT_256_DEL_LINE_BG_IDX = 224
LIGHT_256_ADD_NUM_BG_IDX = 157
LIGHT_256_DEL_NUM_BG_IDX = 217
LIGHT_256_GUTTER_FG_IDX = 236


class DiffLineType(Enum):
    Insert = "insert"
    Delete = "delete"
    Context = "context"


class DiffTheme(Enum):
    Dark = "dark"
    Light = "light"


class DiffColorLevel(Enum):
    TrueColor = "truecolor"
    Ansi256 = "ansi256"
    Ansi16 = "ansi16"


class RichDiffColorLevel(Enum):
    TrueColor = "truecolor"
    Ansi256 = "ansi256"

    @classmethod
    def from_diff_color_level(
        cls, color_level: DiffColorLevel
    ) -> "RichDiffColorLevel | None":
        if color_level is DiffColorLevel.TrueColor:
            return cls.TrueColor
        if color_level is DiffColorLevel.Ansi256:
            return cls.Ansi256
        return None


Color = tuple[str, int, int, int] | tuple[str, int] | str


def rgb_color(rgb: Sequence[int]) -> tuple[str, int, int, int]:
    r, g, b = rgb
    return ("rgb", int(r), int(g), int(b))


def indexed_color(index: int) -> tuple[str, int]:
    return ("indexed", int(index))


@dataclass(frozen=True)
class Style:
    fg: Color | None = None
    bg: Color | None = None
    modifiers: tuple[str, ...] = ()

    def with_fg(self, fg: Color | None) -> "Style":
        return Style(fg=fg, bg=self.bg, modifiers=self.modifiers)

    def with_bg(self, bg: Color | None) -> "Style":
        return Style(fg=self.fg, bg=bg, modifiers=self.modifiers)

    def add_modifier(self, modifier: str) -> "Style":
        if modifier in self.modifiers:
            return self
        return Style(fg=self.fg, bg=self.bg, modifiers=(*self.modifiers, modifier))


@dataclass(frozen=True)
class Span:
    content: str
    style: Style = field(default_factory=Style)


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...] = ()
    style: Style = field(default_factory=Style)

    @classmethod
    def from_spans(cls, spans: Iterable[Span]) -> "Line":
        return cls(tuple(spans))

    def text(self) -> str:
        return "".join(span.content for span in self.spans)


@dataclass(frozen=True)
class ResolvedDiffBackgrounds:
    add: Color | None = None
    delete: Color | None = None

    @property
    def del_(self) -> Color | None:
        return self.delete


@dataclass(frozen=True)
class DiffRenderStyleContext:
    theme: DiffTheme
    color_level: DiffColorLevel
    diff_backgrounds: ResolvedDiffBackgrounds


def _coerce_theme(theme: DiffTheme | str) -> DiffTheme:
    if isinstance(theme, DiffTheme):
        return theme
    normalized = str(theme).lower()
    if normalized == "light":
        return DiffTheme.Light
    if normalized == "dark":
        return DiffTheme.Dark
    raise ValueError(f"unknown diff theme: {theme!r}")


def _coerce_color_level(color_level: DiffColorLevel | str) -> DiffColorLevel:
    if isinstance(color_level, DiffColorLevel):
        return color_level
    normalized = str(color_level).replace("_", "").replace("-", "").lower()
    if normalized in {"truecolor", "truecolour", "rgb"}:
        return DiffColorLevel.TrueColor
    if normalized in {"ansi256", "256"}:
        return DiffColorLevel.Ansi256
    if normalized in {"ansi16", "16", "ansi"}:
        return DiffColorLevel.Ansi16
    raise ValueError(f"unknown diff color level: {color_level!r}")


def fallback_diff_backgrounds(
    theme: DiffTheme | str, color_level: DiffColorLevel | str
) -> ResolvedDiffBackgrounds:
    theme = _coerce_theme(theme)
    color_level = _coerce_color_level(color_level)
    if color_level is DiffColorLevel.Ansi16:
        return ResolvedDiffBackgrounds()
    if color_level is DiffColorLevel.TrueColor:
        if theme is DiffTheme.Light:
            return ResolvedDiffBackgrounds(
                add=rgb_color(LIGHT_TC_ADD_LINE_BG_RGB),
                delete=rgb_color(LIGHT_TC_DEL_LINE_BG_RGB),
            )
        return ResolvedDiffBackgrounds(
            add=rgb_color(DARK_TC_ADD_LINE_BG_RGB),
            delete=rgb_color(DARK_TC_DEL_LINE_BG_RGB),
        )
    if theme is DiffTheme.Light:
        return ResolvedDiffBackgrounds(
            add=indexed_color(LIGHT_256_ADD_LINE_BG_IDX),
            delete=indexed_color(LIGHT_256_DEL_LINE_BG_IDX),
        )
    return ResolvedDiffBackgrounds(
        add=indexed_color(DARK_256_ADD_LINE_BG_IDX),
        delete=indexed_color(DARK_256_DEL_LINE_BG_IDX),
    )


def quantize_rgb_to_ansi256(rgb: Sequence[int]) -> int:
    """Map RGB to the nearest xterm-256 color cube entry.

    Rust delegates this to the terminal color model; Python keeps the semantic
    model dependency-free and deterministic.
    """

    r, g, b = [max(0, min(255, int(component))) for component in rgb]
    if (r, g, b) == (0, 95, 0):
        return 22
    levels = [0, 95, 135, 175, 215, 255]

    def nearest_index(value: int) -> int:
        return min(range(6), key=lambda idx: abs(levels[idx] - value))

    ri, gi, bi = nearest_index(r), nearest_index(g), nearest_index(b)
    cube_index = 16 + (36 * ri) + (6 * gi) + bi

    gray = round((r + g + b) / 3)
    gray_index = max(0, min(23, round((gray - 8) / 10)))
    gray_value = 8 + gray_index * 10

    cube_rgb = (levels[ri], levels[gi], levels[bi])
    cube_distance = sum((a - b) ** 2 for a, b in zip((r, g, b), cube_rgb))
    gray_distance = sum((component - gray_value) ** 2 for component in (r, g, b))
    if gray_distance < cube_distance:
        return 232 + gray_index
    return cube_index


def color_from_rgb_for_level(
    rgb: Sequence[int], color_level: RichDiffColorLevel | DiffColorLevel | str
) -> Color:
    if isinstance(color_level, RichDiffColorLevel):
        rich_level = color_level
    else:
        rich_level = RichDiffColorLevel.from_diff_color_level(
            _coerce_color_level(color_level)
        )
    if rich_level is RichDiffColorLevel.TrueColor:
        return rgb_color(rgb)
    if rich_level is RichDiffColorLevel.Ansi256:
        return indexed_color(quantize_rgb_to_ansi256(rgb))
    raise ValueError("ANSI16 has no rich RGB color mapping")


def resolve_diff_backgrounds_for(
    theme: DiffTheme | str,
    color_level: DiffColorLevel | str,
    scope_backgrounds: dict[str, Sequence[int] | Color | None] | None = None,
) -> ResolvedDiffBackgrounds:
    color_level = _coerce_color_level(color_level)
    resolved = fallback_diff_backgrounds(theme, color_level)
    rich_level = RichDiffColorLevel.from_diff_color_level(color_level)
    if rich_level is None or not scope_backgrounds:
        return resolved

    def convert(value: Sequence[int] | Color | None) -> Color | None:
        if value is None:
            return None
        if isinstance(value, tuple) and value and isinstance(value[0], str):
            return value
        return color_from_rgb_for_level(value, rich_level)

    add = convert(
        scope_backgrounds.get("inserted")
        or scope_backgrounds.get("add")
        or scope_backgrounds.get("addition")
    )
    delete = convert(
        scope_backgrounds.get("deleted")
        or scope_backgrounds.get("delete")
        or scope_backgrounds.get("deletion")
    )
    return ResolvedDiffBackgrounds(
        add=resolved.add if add is None else add,
        delete=resolved.delete if delete is None else delete,
    )


def add_line_bg(theme: DiffTheme | str, color_level: DiffColorLevel | str) -> Color | None:
    return fallback_diff_backgrounds(theme, color_level).add


def del_line_bg(theme: DiffTheme | str, color_level: DiffColorLevel | str) -> Color | None:
    return fallback_diff_backgrounds(theme, color_level).delete


def light_add_num_bg(color_level: DiffColorLevel | str) -> Color | None:
    color_level = _coerce_color_level(color_level)
    if color_level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_ADD_NUM_BG_RGB)
    if color_level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_ADD_NUM_BG_IDX)
    return None


def light_del_num_bg(color_level: DiffColorLevel | str) -> Color | None:
    color_level = _coerce_color_level(color_level)
    if color_level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_DEL_NUM_BG_RGB)
    if color_level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_DEL_NUM_BG_IDX)
    return None


def light_gutter_fg(color_level: DiffColorLevel | str) -> Color | None:
    color_level = _coerce_color_level(color_level)
    if color_level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_GUTTER_FG_RGB)
    if color_level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_GUTTER_FG_IDX)
    return "black"


def style_line_bg_for(
    line_type: DiffLineType, backgrounds: ResolvedDiffBackgrounds
) -> Style:
    if line_type is DiffLineType.Insert:
        return Style(bg=backgrounds.add)
    if line_type is DiffLineType.Delete:
        return Style(bg=backgrounds.delete)
    return Style()


def style_gutter_for(
    line_type: DiffLineType, theme: DiffTheme | str, color_level: DiffColorLevel | str
) -> Style:
    theme = _coerce_theme(theme)
    color_level = _coerce_color_level(color_level)
    if theme is DiffTheme.Light:
        if line_type is DiffLineType.Insert:
            return Style(fg=light_gutter_fg(color_level), bg=light_add_num_bg(color_level))
        if line_type is DiffLineType.Delete:
            return Style(fg=light_gutter_fg(color_level), bg=light_del_num_bg(color_level))
        return Style(fg=light_gutter_fg(color_level))
    if line_type in {DiffLineType.Insert, DiffLineType.Delete}:
        return Style().add_modifier("dim")
    return Style()


def diff_color_level_for_terminal(
    stdout_level: DiffColorLevel | str | None,
    terminal_name: str | None = None,
    *,
    has_wt_session: bool = False,
    has_force_color_override: bool = False,
) -> DiffColorLevel:
    level = DiffColorLevel.Ansi16 if stdout_level is None else _coerce_color_level(stdout_level)
    if has_force_color_override:
        return level
    terminal = (terminal_name or "").lower()
    is_windows_terminal = terminal in {"windows_terminal", "windows-terminal", "wt"}
    if level is DiffColorLevel.Ansi16 and (is_windows_terminal or has_wt_session):
        return DiffColorLevel.TrueColor
    if stdout_level is None and (is_windows_terminal or has_wt_session):
        return DiffColorLevel.TrueColor
    return level


def detect_lang_for_path(path: str | None) -> str | None:
    if not path:
        return None
    name = str(path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name in {"Makefile", "Dockerfile"}:
        return name.lower()
    if "." not in name or name.endswith("."):
        return None
    extension = name.rsplit(".", 1)[1].lower()
    return extension or None


def line_number_width(max_line_number: int | None) -> int:
    if max_line_number is None or max_line_number <= 0:
        return 1
    return len(str(max_line_number))


def char_display_width(char: str) -> int:
    if char == "\t":
        return TAB_WIDTH
    if not char or unicodedata.combining(char):
        return 0
    if unicodedata.category(char)[0] == "C":
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W"}:
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(char_display_width(char) for char in text)


def _take_display_prefix(text: str, max_cols: int) -> tuple[str, str]:
    if max_cols <= 0:
        return "", text
    width = 0
    split_at = 0
    for idx, char in enumerate(text):
        next_width = char_display_width(char)
        if width + next_width > max_cols:
            break
        width += next_width
        split_at = idx + 1
    return text[:split_at], text[split_at:]


def wrap_styled_spans(spans: Iterable[Span], max_cols: int) -> list[Line]:
    if max_cols <= 0:
        return [Line()]

    lines: list[list[Span]] = [[]]
    col = 0

    def push_span(text: str, style: Style) -> None:
        nonlocal col
        remaining = text
        while remaining:
            prefix, suffix = _take_display_prefix(remaining, max_cols - col)
            if not prefix:
                lines.append([])
                col = 0
                continue
            lines[-1].append(Span(prefix, style))
            col += display_width(prefix)
            remaining = suffix
            if remaining:
                lines.append([])
                col = 0

    for span in spans:
        parts = re.split("(\n)", span.content)
        for part in parts:
            if part == "":
                continue
            if part == "\n":
                lines.append([])
                col = 0
                continue
            push_span(part, span.style)

    return [Line.from_spans(line_spans) for line_spans in lines]


def line_display_width(line: Line) -> int:
    return display_width(line.text())


__all__ = [
    "TAB_WIDTH",
    "DARK_TC_ADD_LINE_BG_RGB",
    "DARK_TC_DEL_LINE_BG_RGB",
    "LIGHT_TC_ADD_LINE_BG_RGB",
    "LIGHT_TC_DEL_LINE_BG_RGB",
    "LIGHT_TC_ADD_NUM_BG_RGB",
    "LIGHT_TC_DEL_NUM_BG_RGB",
    "LIGHT_TC_GUTTER_FG_RGB",
    "DARK_256_ADD_LINE_BG_IDX",
    "DARK_256_DEL_LINE_BG_IDX",
    "LIGHT_256_ADD_LINE_BG_IDX",
    "LIGHT_256_DEL_LINE_BG_IDX",
    "LIGHT_256_ADD_NUM_BG_IDX",
    "LIGHT_256_DEL_NUM_BG_IDX",
    "LIGHT_256_GUTTER_FG_IDX",
    "DiffLineType",
    "DiffTheme",
    "DiffColorLevel",
    "RichDiffColorLevel",
    "Style",
    "Span",
    "Line",
    "ResolvedDiffBackgrounds",
    "DiffRenderStyleContext",
    "rgb_color",
    "indexed_color",
    "fallback_diff_backgrounds",
    "quantize_rgb_to_ansi256",
    "color_from_rgb_for_level",
    "resolve_diff_backgrounds_for",
    "add_line_bg",
    "del_line_bg",
    "light_add_num_bg",
    "light_del_num_bg",
    "light_gutter_fg",
    "style_line_bg_for",
    "style_gutter_for",
    "diff_color_level_for_terminal",
    "detect_lang_for_path",
    "line_number_width",
    "char_display_width",
    "display_width",
    "wrap_styled_spans",
    "line_display_width",
]
