# TUI Rust test parity

Tracks migration of Rust `codex-tui` module behavior and tests to Python.

| Rust module | Rust behavior/test | Python module/test | Status | Notes |
|---|---|---|---|---|
| `version.rs` | `CODEX_CLI_VERSION = env!("CARGO_PKG_VERSION")` | `tests/test_tui_version.py::test_codex_cli_version_matches_workspace_package_version` | complete | Ports the full module contract: Python exposes `CODEX_CLI_VERSION` matching the upstream workspace package version inherited by `codex-tui`; no runtime behavior or framework types are involved. |
| `debug_config.rs` | `debug_config_output_lists_all_layers_including_disabled`, `debug_config_output_lists_requirement_sources`, `debug_config_output_lists_session_flag_key_value_pairs`, `debug_config_output_shows_legacy_mdm_layer_value`, `debug_config_output_normalizes_empty_web_search_mode_list`, `debug_config_output_lists_managed_hooks_requirement`, `debug_config_output_formats_unix_socket_permissions`, `session_all_proxy_url_*` | `tests/test_tui_debug_config.py` | complete_slice | Ports debug-config visible text semantics: layer source/status/reason display, session flag TOML flattening, MDM raw value formatting, requirement row/source/value formatting, web-search disabled normalization, managed hooks summary, network domain/unix-socket constraint formatting, and session runtime proxy URLs. Python uses semantic config stack/source DTOs and strings instead of ratatui `Line`/`PlainHistoryCell` and upstream config crate types. |
| `cwd_prompt.rs` | `CwdPromptAction::{verb,past_participle}`, `CwdSelection::{next,prev}`, `CwdPromptScreen::{new,handle_key,set_highlight,select,is_done,selection}`, `run_cwd_selection_prompt`, Rust snapshot content and selection tests | `tests/test_tui_cwd_prompt.py` | complete_slice | Ports cwd prompt state-machine semantics: default Session highlight, Up/Down/j/k toggling, numeric selection, Enter/Esc choices, Ctrl-C/Ctrl-D exit, key-release ignore, frame scheduling, initial/draw/resize semantic redraws, paste ignore, default session fallback, and resume/fork render text. Concrete ratatui modal rendering and real Tui event stream remain framework boundaries. |
| `branch_summary.rs` | `current_branch_name`, `status_line_git_summary`, `branch_diff_stats_prefers_remote_default_ref_over_stale_local_branch`, `open_pull_request_uses_current_branch_view_first`, `open_pull_request_falls_back_to_parent_repo_commit_lookup`, `status_line_pr_view_parser_requires_open_pr`, `status_line_pr_fallback_searches_parent_repo_first` | `tests/test_tui_branch_summary.py` | complete_slice | Ports the status-line git/PR lookup semantics through an injected workspace-command runner: optional best-effort command failures, branch-name trimming, concurrent PR/diff summary aggregation, remote-default/default-local branch resolution, numstat parsing, current-branch PR lookup before commit fallback, open-only PR filtering, and parent-first repo search order. Real `git`/`gh` execution remains the `workspace_command` dependency boundary. |
| `additional_dirs.rs` | `returns_none_for_workspace_write`, `returns_none_for_danger_full_access`, `returns_none_for_external_sandbox`, `warns_for_read_only`, `warns_when_profile_can_write_elsewhere_but_not_cwd`, `returns_none_when_no_additional_dirs` plus parent-writable cwd coverage | `tests/test_tui_additional_dirs.py` | complete | Ports the full module warning contract: empty add-dir suppression, Disabled/External/full-disk/workspace-write no-warning paths, cwd write-permission gate, parent writable-root containment, and exact warning text/path joining. Python uses semantic permission/profile DTOs instead of `codex_protocol` types. |
| `width.rs` | `usable_content_width_returns_none_when_reserved_exhausts_width` | `tests/test_tui_width.py::test_usable_content_width_returns_none_when_reserved_exhausts_width` | complete | Ported strict-positive width contract. |
| `width.rs` | `usable_content_width_u16_matches_usize_variant` | `tests/test_tui_width.py::test_usable_content_width_u16_matches_usize_variant` | complete | Ported u16 wrapper parity. |
| `width.rs` | Python unsigned/u16 interface guardrails | `tests/test_tui_width.py::test_width_helpers_reject_values_outside_rust_unsigned_domains` | complete | Documents the Python boundary that rejects negative usize-compatible inputs and values above `u16::MAX`, matching Rust's unsigned function signatures rather than silently coercing invalid widths. |
| `line_truncation.rs` | `line_width` | `tests/test_tui_line_truncation.py::test_line_width_sums_span_display_widths` | complete | Rust has no local unit test; Python test captures function contract. |
| `line_truncation.rs` | `truncate_line_to_width` | `tests/test_tui_line_truncation.py::{test_truncate_line_to_width_preserves_line_metadata_and_span_styles,test_zero_width_truncation_drops_line_metadata_like_rust}` | complete | Uses Python semantic `Line`/`Span` instead of ratatui types and mirrors Rust empty-line return for zero max width. |
| `line_truncation.rs` | `truncate_line_to_width` zero-width span behavior | `tests/test_tui_line_truncation.py::test_truncate_line_to_width_keeps_zero_width_spans` | complete | Mirrors Rust zero-width span preservation. |
| `line_truncation.rs` | `truncate_line_with_ellipsis_if_overflow` | `tests/test_tui_line_truncation.py::test_truncate_line_with_ellipsis_if_overflow_appends_ellipsis` | complete_slice | Uses semantic ellipsis `鈥; local Rust checkout displays the literal with encoding damage. |
| `color.rs` | `is_light` | `tests/test_tui_color.py::test_is_light_uses_rust_luminance_threshold` | complete | Rust has no local unit test; Python test captures function contract. |
| `color.rs` | `blend` | `tests/test_tui_color.py::test_blend_truncates_like_rust_u8_cast` | complete | Mirrors Rust float blend and `as u8` truncation for normal channel values. |
| `color.rs` | `perceptual_distance` | `tests/test_tui_color.py::{test_perceptual_distance_is_zero_for_identical_colors,test_perceptual_distance_orders_obvious_contrast}` | complete | Implements the full Rust module contract: sRGB -> XYZ -> Lab conversion and CIE76-style Euclidean distance. |
| `terminal_hyperlinks.rs` | `only_web_destinations_receive_osc8` | `tests/test_tui_terminal_hyperlinks.py::test_only_web_destinations_receive_osc8` | complete_slice | Core OSC8 and safe web destination behavior ported. |
| `terminal_hyperlinks.rs` | `discovers_punctuated_web_url_columns` | `tests/test_tui_terminal_hyperlinks.py::test_discovers_punctuated_web_url_columns` | complete_slice | URL punctuation trimming and column range behavior ported. |
| `terminal_hyperlinks.rs` | `preserves_balanced_parentheses_in_bare_web_urls` | `tests/test_tui_terminal_hyperlinks.py::test_preserves_balanced_parentheses_in_bare_web_urls` | complete_slice | Balanced delimiter behavior ported. |
| `terminal_hyperlinks.rs` | `decorates_a_contiguous_web_link_with_one_osc8_pair` | `tests/test_tui_terminal_hyperlinks.py::test_decorates_a_contiguous_web_link_with_one_osc8_pair` | complete_slice | Uses Python semantic `Line`/`Span` instead of ratatui types. |
| `terminal_hyperlinks.rs` | `wrapping_maps_repeated_link_labels_by_source_position` | `tests/test_tui_terminal_hyperlinks.py::test_wrapping_maps_repeated_link_labels_by_source_position` | complete_slice | Source-position remapping behavior ported for already wrapped lines. |
| `terminal_hyperlinks.rs` | `mark_buffer_hyperlinks`, `mark_url_hyperlink`, `mark_underlined_hyperlink` semantic terminal buffer mutation | `tests/test_tui_terminal_hyperlinks.py::{test_mark_buffer_hyperlinks_wraps_visible_symbols_with_osc8,test_mark_url_and_underlined_hyperlinks_filter_matching_cells}` | complete_slice | Ports buffer-cell OSC8 mutation using Python `SemanticBuffer`/`SemanticCell` instead of ratatui `Buffer`; full ratatui paragraph wrapping fidelity remains a renderer boundary. |
| `terminal_hyperlinks.rs` | `HyperlinkLine::push_span` column measurement and web-destination filtering | `tests/test_tui_terminal_hyperlinks.py::test_push_span_records_web_destination_columns_and_skips_empty_or_unsafe_links` | complete_slice | Covers display-column range creation for appended web spans plus Rust guards for empty spans and non-web destinations. |
| `render/line_utils.rs` | `line_to_static` | `tests/test_tui_render_line_utils.py::test_line_to_static_clones_line_metadata_and_spans` | complete | Uses Python semantic `Line`/`Span` instead of ratatui types. |
| `render/line_utils.rs` | `push_owned_lines` | `tests/test_tui_render_line_utils.py::test_push_owned_lines_appends_cloned_lines` | complete | Mirrors owned-copy append behavior. |
| `render/line_utils.rs` | `is_blank_line_spaces_only` | `tests/test_tui_render_line_utils.py::test_is_blank_line_spaces_only_rejects_tabs_and_newlines` | complete | Mirrors test-only Rust helper semantics. |
| `render/line_utils.rs` | `prefix_lines` | `tests/test_tui_render_line_utils.py::test_prefix_lines_uses_initial_then_subsequent_prefixes` | complete | Mirrors first/subsequent prefix behavior, span ownership, line style preservation, and Rust's reconstructed-line alignment reset. |
| `style.rs` | `accent_style_uses_darker_cyan_on_light_backgrounds` | `tests/test_tui_style.py::test_accent_style_uses_darker_cyan_on_light_backgrounds` | complete | Uses Python semantic `Style`/`Color` instead of ratatui types. |
| `style.rs` | `accent_style_uses_cyan_on_dark_or_unknown_backgrounds` | `tests/test_tui_style.py::test_accent_style_uses_cyan_on_dark_or_unknown_backgrounds` | complete | Mirrors dark/unknown background accent behavior. |
| `style.rs` | `table_separator_blends_toward_dark_background` | `tests/test_tui_style.py::test_table_separator_blends_toward_dark_background` | complete | Mirrors true-color separator blend. |
| `style.rs` | `table_separator_blends_toward_light_background` | `tests/test_tui_style.py::test_table_separator_blends_toward_light_background` | complete | Mirrors light background separator blend. |
| `style.rs` | `table_separator_dims_when_palette_aware_color_is_unavailable` | `tests/test_tui_style.py::test_table_separator_dims_when_palette_aware_color_is_unavailable` | complete | Palette-specific reduction remains semantic until terminal_palette is fully ported. |
| `style.rs` | `user_message_style_for`, `proposed_plan_style_for`, `user_message_bg`, `proposed_plan_bg` | `tests/test_tui_style.py::test_user_message_and_proposed_plan_backgrounds_match_rust_blends` | complete | Ports light/dark background blending and `None` background no-op behavior; `proposed_plan_bg` aliases `user_message_bg` like Rust. |
| `terminal_palette.rs` | `rgb_color` / `indexed_color` | `tests/test_tui_terminal_palette.py::test_rgb_and_indexed_color_preserve_semantics` | complete_slice | Uses Python semantic `Color` instead of ratatui color. |
| `terminal_palette.rs` | `xterm_fixed_colors` | `tests/test_tui_terminal_palette.py::test_xterm_fixed_colors_skip_theme_dependent_first_sixteen` | complete_slice | Generates standard xterm 256 palette and skips first 16 colors. |
| `terminal_palette.rs` | `best_color` | `tests/test_tui_terminal_palette.py::test_best_color_truecolor_and_unknown_paths` | complete_slice | Color level can be injected for deterministic tests. |
| `terminal_palette.rs` | `best_color` ANSI256 selection | `tests/test_tui_terminal_palette.py::test_best_color_ansi256_selects_exact_fixed_color` | complete_slice | Mirrors closest fixed-color selection with perceptual distance. |
| `terminal_palette.rs` | `best_color` skips theme-dependent system colors | `tests/test_tui_terminal_palette.py::test_best_color_ansi256_never_selects_theme_dependent_system_colors` | complete_slice | Covers Rust `xterm_fixed_colors().skip(16)` behavior so ANSI256 fallback never chooses indices 0..15. |
| `terminal_palette.rs` | `default_fg` / `default_bg` startup probe cache | `tests/test_tui_terminal_palette.py::test_default_colors_can_be_seeded_from_startup_probe` | complete_slice | Real terminal querying remains a platform side effect; cache semantics ported. |
| `terminal_palette.rs` | `stdout_color_level`, `indexed_color` bounds | `tests/test_tui_terminal_palette.py::{test_stdout_color_level_uses_environment_approximation,test_indexed_color_rejects_out_of_u8_range}` | complete_slice | Uses a deterministic environment approximation for Rust `supports_color::on_cached(stdout)` and preserves u8 color-index boundaries; real terminal capability probing remains a platform side effect. |
| `ui_consts.rs` | `LIVE_PREFIX_COLS` / `FOOTER_INDENT_COLS` | `tests/test_tui_ui_consts.py::test_ui_layout_constants_match_rust_values` | complete | Constants match Rust layout semantics. |
| `text_formatting.rs` | `capitalize_first`, `truncate_text` boundary tests | `tests/test_tui_text_formatting.py::{test_capitalize_first_matches_rust_char_uppercase,test_truncate_text,test_truncate_boundaries,test_truncate_unicode_combining_characters}` | complete | Uses stdlib grapheme approximation for combining marks and mirrors Rust first-char uppercasing. |
| `text_formatting.rs` | `format_json_compact`, `format_and_truncate_tool_result` JSON/text examples | `tests/test_tui_text_formatting.py::{test_format_json_compact_examples,test_format_and_truncate_tool_result_compacts_json_before_truncating}` | complete | Mirrors compact single-line JSON formatting and Rust max-lines/width grapheme budget before truncation. |
| `text_formatting.rs` | `format_json_compact` string and escape state | `tests/test_tui_text_formatting.py::test_format_json_compact_preserves_commas_colons_and_escapes_inside_strings` | complete | Preserves commas, colons, and escaped quotes inside JSON strings while spacing only structural separators. |
| `text_formatting.rs` | `center_truncate_path` representative examples | `tests/test_tui_text_formatting.py::test_center_truncate_path_examples` | complete_slice | Uses semantic ellipsis `鈥; local Rust checkout displays the literal with encoding damage. |
| `text_formatting.rs` | `proper_join` | `tests/test_tui_text_formatting.py::test_proper_join` | complete | Mirrors English punctuation join behavior. |
| `table_detect.rs` | `parse_table_segments_*` Rust unit tests | `tests/test_tui_table_detect.py::test_parse_table_segments_rust_examples` | complete | Ports pipe segment trimming, optional outer pipes, single outer-pipe segment, empty/no-pipe None, and escaped pipe structure behavior. |
| `table_detect.rs` | `is_table_header_line_*` and delimiter tests | `tests/test_tui_table_detect.py::test_table_header_and_delimiter_detection` | complete | Ports GFM header/delimiter structural detection. |
| `table_detect.rs` | `FenceTracker` open/close and markdown fence tests | `tests/test_tui_table_detect.py::test_fence_tracker_rust_examples` | complete | Ports incremental fence state transitions for backtick, tilde, and markdown fences. |
| `table_detect.rs` | `FenceTracker` close edge cases | `tests/test_tui_table_detect.py::test_fence_tracker_close_rules` | complete | Ports shorter marker, mismatched marker, and trailing-content close rejection. |
| `table_detect.rs` | fence helper tests | `tests/test_tui_table_detect.py::test_fence_tracker_indentation_blockquote_and_helpers` | complete | Ports indentation ignore, blockquote stripping, fence marker parsing, markdown info detection, and blockquote helper behavior. |
| `render/renderable.rs` | primitive trait impls for `()`, strings, spans, lines, and semantic paragraph rows | `tests/test_tui_render_renderable.py::{test_text_and_none_renderables_match_basic_trait_impls,test_paragraph_renderable_counts_wrapped_lines_semantically}` | complete | Uses semantic `Buffer`/`Rect` and records visible draw calls instead of ratatui mutation; `ParagraphRenderable` preserves the `line_count(width)` height contract. |
| `render/renderable.rs` | `ColumnRenderable` stack layout and cursor forwarding | `tests/test_tui_render_renderable.py::test_column_renderable_stacks_children_and_forwards_cursor` | complete | Ports vertical child allocation, render forwarding, desired height sum, and first cursor style behavior. |
| `render/renderable.rs` | `FlexRenderable::allocate` flex layout | `tests/test_tui_render_renderable.py::test_flex_renderable_allocates_non_flex_then_flex_space` | complete | Ports non-flex allocation, proportional flex allocation, and last-flex remainder behavior. |
| `render/renderable.rs` | `RowRenderable` horizontal layout, max desired height, and cursor forwarding | `tests/test_tui_render_renderable.py::{test_row_renderable_lays_out_by_width_and_reports_max_height,test_row_renderable_forwards_cursor_style_from_first_cursor_child}` | complete | Ports saturating available-width behavior, max child height calculation, and first child cursor style forwarding. |
| `render/renderable.rs` | `InsetRenderable` area/height/cursor forwarding | `tests/test_tui_render_renderable.py::test_inset_renderable_shrinks_area_and_adds_height` | complete | Uses semantic `Insets`/`Rect.inset`; ratatui buffer details intentionally abstracted. |
| `render/renderable.rs` | `RenderableExt::inset` helper | `tests/test_tui_render_renderable.py::test_inset_helper_returns_renderable_item_and_default_cursor_style` | complete | Ports helper shape as module-level Python function returning a `RenderableItem`. |
| `render/mod.rs` | `Insets::tlbr` / `Insets::vh` | `tests/test_tui_render.py::test_insets_constructors_match_rust_field_order` | complete | Ports top/left/bottom/right and vertical/horizontal constructor semantics. |
| `render/mod.rs` | `RectExt::inset` saturating geometry | `tests/test_tui_render.py::test_rect_inset_uses_saturating_dimensions` | complete | Uses Python semantic `Rect`; mirrors Rust saturating width/height behavior. |
| `render/mod.rs` | extension trait helper shape | `tests/test_tui_render.py::test_rect_ext_static_helper_matches_free_function` | complete | Python exposes a `RectExt.inset` helper plus module-level `inset`. |
| `terminal_title.rs` | `sanitizes_terminal_title` | `tests/test_tui_terminal_title.py::test_sanitizes_terminal_title` | complete | Ports whitespace collapsing and control-character removal. |
| `terminal_title.rs` | `strips_invisible_format_chars_from_terminal_title` | `tests/test_tui_terminal_title.py::test_strips_invisible_format_chars_from_terminal_title` | complete | Ports Trojan-Source/bidi and invisible formatting character filtering. |
| `terminal_title.rs` | `truncates_terminal_title` | `tests/test_tui_terminal_title.py::test_truncates_terminal_title` | complete | Ports 240 Rust-char title bound. |
| `terminal_title.rs` | `truncation_prefers_visible_char_over_pending_space` | `tests/test_tui_terminal_title.py::test_truncation_prefers_visible_char_over_pending_space` | complete | Ports pending-space boundary behavior. |
| `terminal_title.rs` | `writes_osc_title_with_bel_terminator` | `tests/test_tui_terminal_title.py::test_writes_osc_title_with_bel_terminator` | complete | Ports OSC 0 title encoding with BEL terminator. |
| `terminal_title.rs` | `set_terminal_title` / `clear_terminal_title` terminal side effect boundary | `tests/test_tui_terminal_title.py::test_set_terminal_title_result_and_clear_terminal_title` | complete_slice | Uses injectable Python text stream to model Rust stdout terminal/no-terminal branches without touching real terminal. |
| `frames.rs` | 10 embedded frame variants with 36 frames each | `tests/test_tui_frames.py::test_all_frame_variants_match_rust_shape` | complete_slice | Python loads the authoritative upstream frame text files at import time instead of fabricating placeholders. |
| `frames.rs` | `FRAME_TICK_DEFAULT` | `tests/test_tui_frames.py::test_frame_tick_default_is_80ms` | complete | Ports Rust `Duration::from_millis(80)` as `datetime.timedelta(milliseconds=80)`. |
| `ascii_animation.rs` | `frame_tick_must_be_nonzero` | `tests/test_tui_ascii_animation.py::test_frame_tick_must_be_nonzero` | complete | Ports Rust test that default frame tick is non-zero. |
| `ascii_animation.rs` | `AsciiAnimation::with_variants` empty assertion and clamped index | `tests/test_tui_ascii_animation.py::test_with_variants_requires_non_empty_and_clamps_index` | complete | Ports construction invariants with injectable clock. |
| `ascii_animation.rs` | `AsciiAnimation::current_frame` tick-index behavior | `tests/test_tui_ascii_animation.py::test_current_frame_uses_elapsed_tick_index_and_empty_frames` | complete | Ports elapsed/tick modulo frame selection and empty-frame fallback. |
| `ascii_animation.rs` | zero tick immediate scheduling/current frame behavior | `tests/test_tui_ascii_animation.py::test_zero_tick_uses_first_frame_and_immediate_schedule` | complete | Rust source handles zero tick defensively; Python preserves that branch. |
| `ascii_animation.rs` | `schedule_next_frame` delay alignment | `tests/test_tui_ascii_animation.py::test_schedule_next_frame_aligns_to_next_tick` | complete | Ports next-tick delay calculation with semantic frame requester. |
| `ascii_animation.rs` | `pick_random_variant` avoids current variant and schedules frame | `tests/test_tui_ascii_animation.py::test_pick_random_variant_never_keeps_current_and_schedules_frame` | complete | Uses injectable rng to preserve Rust loop semantics deterministically. |

### ascii_animation.rs - complete

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `ascii_animation.rs` `AsciiAnimation::{new,with_variants,schedule_next_frame,current_frame,pick_random_variant}` and Rust test `frame_tick_must_be_nonzero` | `pycodex.tui.ascii_animation`; `tests/test_tui_ascii_animation.py` | `complete` | Module-scoped behavior contract is covered: non-empty variants assertion, index clamping, default `ALL_VARIANTS`, tick-aligned scheduling, zero-tick fallback, elapsed tick modulo frame selection, empty frame fallback, random variant selection that avoids the current index, and semantic frame requester callbacks. Python injects clock/RNG for deterministic parity tests instead of using real `Instant`/`rand`. |
| `terminal_probe.rs` | `parses_cursor_position_as_zero_based` | `tests/test_tui_terminal_probe.py::test_parses_cursor_position_as_zero_based` | complete | Ports CSI cursor-position parsing and zero-based conversion. |
| `terminal_probe.rs` | `parses_osc_colors_with_bel_and_st` | `tests/test_tui_terminal_probe.py::test_parses_osc_colors_with_bel_and_st` | complete | Ports OSC 10/11 parsing with BEL and ST terminators. |
| `terminal_probe.rs` | `parses_two_and_four_digit_color_components` | `tests/test_tui_terminal_probe.py::test_parses_two_and_four_digit_color_components` | complete | Ports two/four hex digit RGB/RGBA component behavior. |
| `terminal_probe.rs` | `parses_default_colors_from_one_buffer` | `tests/test_tui_terminal_probe.py::test_parses_default_colors_from_one_buffer` | complete | Ports foreground/background pairing and missing-pair None behavior. |
| `terminal_probe.rs` | `parses_keyboard_enhancement_flags_and_pda_fallback` | `tests/test_tui_terminal_probe.py::test_parses_keyboard_enhancement_flags_and_pda_fallback` | complete | Ports keyboard protocol state classification. |
| `terminal_probe.rs` | `startup_probe_parses_batched_terminal_responses` | `tests/test_tui_terminal_probe.py::test_startup_probe_parses_batched_terminal_responses` | complete | Ports batched update_startup_probe behavior and completion predicate. |
| `terminal_probe.rs` | startup finish after partial keyboard response | `tests/test_tui_terminal_probe.py::test_finish_startup_probe_promotes_seen_supported_keyboard` | complete_slice | Ports finish_startup_probe promotion rule; real TTY duplicate/poll remains explicit platform boundary. |
| `terminal_probe.rs` | `Tty::open`, `default_colors`, `startup` real terminal I/O | N/A | blocked | Requires real nonblocking terminal-handle implementation; Python parser/state behavior is ported, but platform probe side effect is not silently simulated. |
| `wrapping.rs` | basic `word_wrap_line` prose wrapping and indents | `tests/test_tui_wrapping.py::test_basic_word_wrap_and_indents` | complete_slice | Ports visible wrapping/indent behavior using Python semantic `Line`/`Span`. |
| `wrapping.rs` | empty input, leading spaces, repeated spaces, break_words=false, hyphen split | `tests/test_tui_wrapping.py::test_empty_leading_spaces_hyphen_and_break_words_behavior` | complete_slice | Captures representative Rust wrapping tests without cloning textwrap internals. |
| `wrapping.rs` | styled split within a span preserves style | `tests/test_tui_wrapping.py::test_styled_split_within_span_preserves_style` | complete_slice | Python semantic spans preserve style on split. |
| `wrapping.rs` | multi-line wrapping applies initial indent only once | `tests/test_tui_wrapping.py::test_word_wrap_lines_applies_initial_indent_once` | complete_slice | Ports Rust `word_wrap_lines` indent progression behavior. |
| `wrapping.rs` | URL-like token detection positives/negatives/custom scheme/ports | `tests/test_tui_wrapping.py::test_url_detection_matches_expected_tokens` | complete_slice | Ports URL heuristic contract. |
| `wrapping.rs` | line URL detection across spans and mixed-token decorative markers | `tests/test_tui_wrapping.py::test_line_url_detection_across_spans_and_mixed_markers` | complete_slice | Ports span flattening and decorative marker ignoring. |
| `wrapping.rs` | adaptive wrap keeps URL tokens intact and non-URLs wrappable | `tests/test_tui_wrapping.py::test_adaptive_wrap_preserves_url_and_wraps_non_url` | complete_slice | Ports URL-preserving adaptive wrapper behavior. |
| `wrapping.rs` | adaptive mixed URL/prose wrapping | `tests/test_tui_wrapping.py::test_adaptive_wrap_mixed_line_keeps_regular_words_intact` | complete_slice | Ports representative mixed URL/prose visible output contract. |
| `wrapping.rs` | exact `textwrap` owned/borrowed range recovery edge cases | N/A | blocked | Python uses semantic source range reconstruction; exact Rust `textwrap::Cow` pointer/owned penalty behavior requires deeper textwrap-compatible engine. |
| `live_wrap.rs` | `rows_do_not_exceed_width_ascii` | `tests/test_tui_live_wrap.py::test_rows_do_not_exceed_width_ascii` | complete | Ports RowBuilder ASCII hard-wrap behavior. |
| `live_wrap.rs` | `rows_do_not_exceed_width_emoji_cjk` | `tests/test_tui_live_wrap.py::test_rows_do_not_exceed_width_emoji_cjk` | complete | Ports display-width-aware wrapping for emoji/CJK-width text using Python semantic width. |
| `live_wrap.rs` | `fragmentation_invariance_long_token` | `tests/test_tui_live_wrap.py::test_fragmentation_invariance_long_token` | complete | Ports incremental push_fragment invariance. |
| `live_wrap.rs` | `newline_splits_rows` | `tests/test_tui_live_wrap.py::test_newline_splits_rows` | complete | Ports explicit newline row behavior. |
| `live_wrap.rs` | `rewrap_on_width_change` | `tests/test_tui_live_wrap.py::test_rewrap_on_width_change` | complete | Ports set_width full rewrap behavior. |
| `live_wrap.rs` | `take_prefix_by_width` | `tests/test_tui_live_wrap.py::test_take_prefix_by_width_returns_prefix_suffix_and_width` | complete | Ports prefix/suffix/taken-width helper behavior. |
| `live_wrap.rs` | `drain_commit_ready` display-row commit contract | `tests/test_tui_live_wrap.py::test_drain_commit_ready_counts_current_display_row` | complete | Rust has no local unit test for this helper; Python test records module contract. |
| `motion.rs` | `MotionMode::from_animations_enabled` | `tests/test_tui_motion.py::test_motion_mode_from_animations_enabled` | complete | Ports bool-to-motion-mode helper. |
| `motion.rs` | `reduced_motion_activity_indicator_uses_explicit_fallback` | `tests/test_tui_motion.py::test_reduced_motion_activity_indicator_uses_explicit_fallback` | complete | Ports Hidden -> None and StaticBullet -> dim bullet behavior using semantic Span. |
| `motion.rs` | `reduced_motion_shimmer_text_is_plain_text` | `tests/test_tui_motion.py::test_reduced_motion_shimmer_text_is_plain_text` | complete | Ports reduced shimmer fallback to plain text or empty vector. |
| `motion.rs` | animated activity/shimmer semantic path | `tests/test_tui_motion.py::test_animated_motion_returns_semantic_spans` | complete_slice | Python uses semantic shimmer style rather than terminal-color-dependent ratatui shimmer. |
| `motion.rs` | `animated_activity_indicator` 600ms integer tick boundaries | `tests/test_tui_motion.py::test_animated_activity_indicator_tick_boundaries_use_integer_milliseconds` | complete_slice | Uses rounded integer milliseconds before the Rust `(elapsed_ms / 600).is_multiple_of(2)` blink bucket calculation, avoiding float truncation drift at 600ms boundaries. |
| `motion.rs` | `animation_primitive_allowlisted_path` | `tests/test_tui_motion.py::test_animation_primitive_allowlisted_path` | complete | Ports allowlist helper. |
| `motion.rs` | `animation_primitives_are_only_used_by_motion_module` | `tests/test_tui_motion.py::test_animation_primitives_are_only_used_by_motion_module` | complete_slice | Ports source scan policy with injectable source directory instead of Cargo resource lookup. |
| `shimmer.rs` | `shimmer_spans` empty text | `tests/test_tui_shimmer.py::test_shimmer_spans_empty_text_returns_empty_vec` | complete | Ports empty input -> empty span vector. |
| `shimmer.rs` | `shimmer_spans` one span per character | `tests/test_tui_shimmer.py::test_shimmer_spans_emits_one_span_per_character` | complete_slice | Uses semantic `Span`/`ShimmerStyle` instead of ratatui `Style`. |
| `shimmer.rs` | `color_for_level` fallback thresholds | `tests/test_tui_shimmer.py::test_color_for_level_fallback_thresholds` | complete | Ports dim/default/bold intensity thresholds. |
| `shimmer.rs` | truecolor shimmer blend branch | `tests/test_tui_shimmer.py::test_truecolor_shimmer_uses_bold_rgb_style` | complete_slice | Ports semantic RGB bold style; terminal capability detection remains injectable. |
| `token_usage.rs` | `TokenUsage::is_zero`, `cached_input`, `non_cached_input`, `blended_total`, `tokens_in_context_window` | `tests/test_tui_token_usage.py::test_token_usage_zero_and_input_accounting` | complete | Ports local token accounting behavior. |
| `token_usage.rs` | negative token clamp behavior | `tests/test_tui_token_usage.py::test_token_usage_clamps_negative_values_like_rust` | complete | Ports Rust `.max(0)` semantics for cached/non-cached/blended totals. |
| `token_usage.rs` | `percent_of_context_window_remaining` baseline/clamp/round | `tests/test_tui_token_usage.py::test_percent_of_context_window_remaining_baseline_and_clamp` | complete | Ports 12k baseline and 0..100 percentage behavior. |
| `token_usage.rs` | `Display for TokenUsage` cached/reasoning formatting | `tests/test_tui_token_usage.py::test_display_format_includes_cached_and_reasoning_when_present` | complete | Ports user-visible token usage string with separators. |
| `token_usage.rs` | `Display for TokenUsage` omission of zero cached/reasoning details | `tests/test_tui_token_usage.py::test_display_format_omits_zero_cached_and_reasoning` | complete | Ports conditional display suffix behavior. |
| `token_usage.rs` | `TokenUsageInfo` data model defaults | `tests/test_tui_token_usage.py::test_token_usage_info_defaults` | complete | Ports wrapper data shape with optional model context window. |
| `status_indicator_widget.rs` | `fmt_elapsed_compact_formats_seconds_minutes_hours` | `tests/test_tui_status_indicator_widget.py::test_fmt_elapsed_compact_formats_seconds_minutes_hours` | complete | Ports compact elapsed time formatting. |
| `status_indicator_widget.rs` | `update_details` capitalization/max-lines behavior | `tests/test_tui_status_indicator_widget.py::test_details_update_capitalization_and_limit` | complete | Ports trim-start, optional capitalization, preserve mode, and max(1) line cap. |
| `status_indicator_widget.rs` | `update_inline_message` and `interrupt` | `tests/test_tui_status_indicator_widget.py::test_inline_message_trim_and_interrupt` | complete_slice | Uses semantic AppEventSender. |
| `status_indicator_widget.rs` | `timer_pauses_when_requested` | `tests/test_tui_status_indicator_widget.py::test_timer_pauses_when_requested` | complete | Ports pause/resume elapsed accounting and resume frame request. |
| `status_indicator_widget.rs` | `renders_without_spinner_when_animations_disabled` | `tests/test_tui_status_indicator_widget.py::test_render_without_spinner_when_animations_disabled` | complete_slice | Ports visible text contract via semantic `render_lines` instead of ratatui snapshot. |
| `status_indicator_widget.rs` | remapped interrupt hint and inline suffix | `tests/test_tui_status_indicator_widget.py::test_render_remapped_interrupt_hint_and_inline_message` | complete_slice | Ports interrupt binding replacement and inline message suffix. |
| `status_indicator_widget.rs` | `details_overflow_adds_ellipsis` | `tests/test_tui_status_indicator_widget.py::test_details_overflow_adds_ellipsis` | complete_slice | Ports max details line truncation and semantic ellipsis. |
| `status_indicator_widget.rs` | desired height and details render height cap | `tests/test_tui_status_indicator_widget.py::test_desired_height_and_render_details_height_limit` | complete_slice | Ports details height accounting and render area limiting. |
| `status_indicator_widget.rs` | ratatui `TestBackend` visual snapshots | N/A | blocked | Python uses semantic `Line` output contract; full cell-buffer snapshot parity depends on shared Python TUI buffer renderer. |
| `goal_display.rs` | `format_goal_elapsed_seconds_is_compact` | `tests/test_tui_goal_display.py::test_format_goal_elapsed_seconds_is_compact` | complete | Ports seconds/minutes/hours/days compact elapsed formatting and negative clamp. |
| `goal_display.rs` | `goal_status_label` | `tests/test_tui_goal_display.py::test_goal_status_label_matches_rust_variants` | complete | Ports ThreadGoalStatus label mapping. |
| `goal_display.rs` | `goal_usage_summary_formats_time_and_budgeted_tokens` | `tests/test_tui_goal_display.py::test_goal_usage_summary_formats_time_and_budgeted_tokens` | complete | Ports objective/time/token budget summary formatting. |
| `goal_display.rs` | `goal_usage_summary` optional time/budget omission | `tests/test_tui_goal_display.py::test_goal_usage_summary_omits_absent_time_or_budget` | complete | Captures module contract for absent optional fields. |
| `goal_display.rs` | `format_tokens_compact` dependency behavior used by goal summary | `tests/test_tui_goal_display.py::test_format_tokens_compact_representative_values` | complete | Local semantic implementation mirrors visible compact token formatting needed by this module. |

### goal_display.rs - complete

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `goal_display.rs` `format_goal_elapsed_seconds`, `goal_status_label`, `goal_usage_summary`; Rust tests `format_goal_elapsed_seconds_is_compact`, `goal_usage_summary_formats_time_and_budgeted_tokens` | `pycodex.tui.goal_display`; `tests/test_tui_goal_display.py` | `complete` | Module-scoped behavior contract is covered: negative elapsed seconds clamp to zero, compact seconds/minutes/hours/days labels, all `ThreadGoalStatus` labels, objective/time/token summary composition, optional time/budget omission, and compact token formatting needed by this module. |
| `branch_summary.rs` | `branch_diff_stats_prefers_remote_default_ref_over_stale_local_branch` | `tests/test_tui_branch_summary.py::test_branch_diff_stats_prefers_remote_default_ref_over_stale_local_branch` | complete_slice | Ports remote default ref preference, merge-base range, and numstat aggregation through injected runner. |
| `branch_summary.rs` | `open_pull_request_uses_current_branch_view_first` | `tests/test_tui_branch_summary.py::test_open_pull_request_uses_current_branch_view_first` | complete | Ports gh current-branch PR lookup and avoids fallback when open PR is found. |
| `branch_summary.rs` | `open_pull_request_falls_back_to_parent_repo_commit_lookup` | `tests/test_tui_branch_summary.py::test_open_pull_request_falls_back_to_parent_repo_commit_lookup` | complete_slice | Ports HEAD SHA fallback, parent-first repo order, and commit-to-PR API lookup. |
| `branch_summary.rs` | `status_line_pr_view_parser_requires_open_pr` | `tests/test_tui_branch_summary.py::test_status_line_pr_view_parser_requires_open_pr` | complete | Ports gh PR view JSON parser open-only behavior. |
| `branch_summary.rs` | `status_line_pr_fallback_searches_parent_repo_first` | `tests/test_tui_branch_summary.py::test_status_line_pr_fallback_searches_parent_repo_first` | complete | Ports repo search order parser parent-before-fork behavior. |
| `branch_summary.rs` | real `git`/`gh` background probe side effects | N/A | complete_slice | Python preserves Rust runner abstraction and best-effort optional metadata semantics; no direct subprocess probing is introduced. |
| `git_action_directives.rs` | `strips_and_parses_git_action_directives` | `tests/test_tui_git_action_directives.py::test_strips_and_parses_git_action_directives` | complete | Ports directive stripping, visible markdown trimming, and Stage/Push action parsing. |
| `git_action_directives.rs` | `hides_malformed_directives_without_materializing_rows` | `tests/test_tui_git_action_directives.py::test_hides_malformed_directives_without_materializing_rows` | complete | Ports malformed known directive removal without creating a git action. |
| `git_action_directives.rs` | `last_created_branch_cwd_uses_the_last_matching_directive` | `tests/test_tui_git_action_directives.py::test_last_created_branch_cwd_uses_the_last_matching_directive` | complete | Ports reverse search over parsed git actions. |
| `git_action_directives.rs` | `parse_attributes` quoted/bare attributes | `tests/test_tui_git_action_directives.py::test_parse_attributes_supports_quoted_and_bare_values` | complete | Captures local parser behavior for quoted and whitespace-delimited values. |
| `git_action_directives.rs` | `git-create-pr` optional URL and draft flag | `tests/test_tui_git_action_directives.py::test_parse_git_create_pr_optional_url_and_draft_flag` | complete | Ports CreatePr action construction and `isDraft == true` rule. |
| `git_action_directives.rs` | duplicate directive de-duplication | `tests/test_tui_git_action_directives.py::test_duplicate_actions_are_deduplicated_in_first_seen_order` | complete | Ports `HashSet`-based de-duplication while preserving first-seen order. |
| `startup_error.rs` | `LocalStateDbStartupError::new`, accessors, and Display error text | `tests/test_tui_startup_error.py::test_local_state_db_startup_error_accessors_and_display` | complete | Ports state DB path/detail storage and user-visible error string. |
| `cwd_prompt.rs` | `CwdPromptAction::verb` / `past_participle` | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_action_words_match_rust` | complete | Ports resume/fork display words. |
| `cwd_prompt.rs` | `cwd_prompt_selects_session_by_default` | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_selects_session_by_default` | complete | Ports default highlighted Session and Enter selection. |
| `cwd_prompt.rs` | `cwd_prompt_can_select_current` | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_can_select_current` | complete | Ports Down then Enter selecting Current. |
| `cwd_prompt.rs` | `cwd_prompt_ctrl_c_exits_instead_of_selecting` | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_ctrl_c_exits_instead_of_selecting` | complete | Ports Ctrl-C exit behavior. |
| `cwd_prompt.rs` | numeric and Escape selection rules | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_number_and_escape_selection_rules` | complete_slice | Captures key mapping from Rust handle_key. |
| `cwd_prompt.rs` | vim-style `j`/`k` highlight navigation | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_vim_keys_toggle_highlight_like_arrows` | complete_slice | Covers Rust `KeyCode::Char('j')`/`KeyCode::Char('k')` aliases for Down/Up selection cycling. |
| `cwd_prompt.rs` | release-event ignore and frame scheduling on highlight change | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_ignores_key_release_and_schedules_on_highlight_change` | complete_slice | Ports state transition and frame request behavior with semantic KeyEvent. |
| `cwd_prompt.rs` | `cwd_prompt_snapshot` / `cwd_prompt_fork_snapshot` visible modal text | `tests/test_tui_cwd_prompt.py::test_cwd_prompt_render_lines_resume_and_fork_content` | complete_slice | Python uses semantic render_lines text contract instead of VT100 snapshot. |
| `cwd_prompt.rs` | full async TUI event-stream draw loop | N/A | blocked | Requires shared Python TUI event loop/buffer renderer; screen state machine and visible text are ported. |
| `additional_dirs.rs` | `returns_none_for_workspace_write` | `tests/test_tui_additional_dirs.py::test_returns_none_for_workspace_write` | complete | Ports cwd-writable profile early return. |
| `additional_dirs.rs` | `returns_none_for_danger_full_access` | `tests/test_tui_additional_dirs.py::test_returns_none_for_danger_full_access` | complete | Ports Disabled/danger-full-access early return. |
| `additional_dirs.rs` | `file_system_policy.has_full_disk_write_access()` guard | `tests/test_tui_additional_dirs.py::test_returns_none_for_managed_full_disk_write_policy` | complete | Covers the explicit Rust full-disk-write policy branch independently from the Disabled permission-profile early return. |
| `additional_dirs.rs` | `returns_none_for_external_sandbox` | `tests/test_tui_additional_dirs.py::test_returns_none_for_external_sandbox` | complete | Ports External sandbox early return. |
| `additional_dirs.rs` | `warns_for_read_only` | `tests/test_tui_additional_dirs.py::test_warns_for_read_only` | complete | Ports exact warning text and path joining. |
| `additional_dirs.rs` | `warns_when_profile_can_write_elsewhere_but_not_cwd` | `tests/test_tui_additional_dirs.py::test_warns_when_profile_can_write_elsewhere_but_not_cwd` | complete | Ports warning when profile has writes outside cwd but cannot write cwd. |
| `additional_dirs.rs` | `returns_none_when_no_additional_dirs` | `tests/test_tui_additional_dirs.py::test_returns_none_when_no_additional_dirs` | complete | Ports empty additional dirs early return. |
| `mention_codec.rs` | `decode_history_mentions_restores_visible_tokens` | `tests/test_tui_mention_codec.py::test_decode_history_mentions_restores_visible_tokens` | complete | Ports markdown linked `$mention` decoding and linked path capture. |
| `mention_codec.rs` | `decode_history_mentions_restores_plugin_links_with_at_sigil` | `tests/test_tui_mention_codec.py::test_decode_history_mentions_restores_plugin_links_with_at_sigil` | complete | Ports plugin `@mention` compatibility decoding to visible `$mention`. |
| `mention_codec.rs` | `decode_history_mentions_ignores_at_sigil_for_non_plugin_paths` | `tests/test_tui_mention_codec.py::test_decode_history_mentions_ignores_at_sigil_for_non_plugin_paths` | complete | Ports at-sigil plugin path restriction. |
| `mention_codec.rs` | `encode_history_mentions_links_bound_mentions_in_order` | `tests/test_tui_mention_codec.py::test_encode_history_mentions_links_bound_mentions_in_order` | complete | Ports ordered binding of repeated visible mentions to linked paths. |
| `mention_codec.rs` | env var and non-tool path filters | `tests/test_tui_mention_codec.py::test_decode_history_mentions_filters_env_vars_and_non_tool_paths` | complete | Captures helper filter semantics beyond explicit Rust tests. |
| `mention_codec.rs` | `is_tool_path` known schemes and SKILL.md basename | `tests/test_tui_mention_codec.py::test_tool_path_accepts_known_schemes_and_skill_md` | complete | Ports tool path recognition helpers. |

### mention_codec.rs - complete

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `mention_codec.rs` `LinkedMention`, `DecodedHistoryText`, `encode_history_mentions`, `decode_history_mentions`, linked mention parsing/filter helpers; Rust tests `decode_history_mentions_restores_visible_tokens`, `decode_history_mentions_restores_plugin_links_with_at_sigil`, `decode_history_mentions_ignores_at_sigil_for_non_plugin_paths`, `encode_history_mentions_links_bound_mentions_in_order` | `pycodex.tui.mention_codec`; `tests/test_tui_mention_codec.py` | `complete` | Module-scoped behavior contract is covered: ordered repeated mention binding, markdown link decode back to visible `$mention`, plugin `@mention` compatibility decode, non-plugin `@` rejection, common-env-var filtering, tool path scheme/SKILL.md recognition, path trimming, empty-path rejection, and ASCII mention-name character rules. |
| `config_update.rs` | `replace_config_value` / `clear_config_value` edit shape | `tests/test_tui_config_update.py::test_replace_and_clear_config_value_match_rust_edit_shape` | complete | Ports `ConfigEdit` replace/null semantics with Python semantic dataclasses. |
| `config_update.rs` | `app_scoped_key_path_quotes_dotted_app_ids` | `tests/test_tui_config_update.py::test_app_scoped_key_path_quotes_dotted_app_ids` | complete | Ports Rust unit test for JSON-quoted app id path segment. |
| `config_update.rs` | `trusted_project_edit_targets_project_trust_level` | `tests/test_tui_config_update.py::test_trusted_project_edit_targets_project_trust_level` | complete | Ports Rust unit test for project trust-level key/value. |
| `config_update.rs` | project trust key escaping | `tests/test_tui_config_update.py::test_trusted_project_edit_escapes_backslashes_and_quotes` | complete_slice | Captures Rust escaping logic for backslashes and quotes. |
| `config_update.rs` | model and reasoning effort edits | `tests/test_tui_config_update.py::test_build_model_selection_edits_clears_or_replaces_effort` | complete_slice | Ports model write plus effort clear/replace behavior. |
| `config_update.rs` | service tier config value normalization | `tests/test_tui_config_update.py::test_build_service_tier_selection_edits_normalizes_known_tiers` | complete_slice | Ports default/fast/priority/flex/custom handling. |
| `config_update.rs` | Windows sandbox migration edits | `tests/test_tui_config_update.py::test_build_windows_sandbox_mode_edits_writes_new_key_and_clears_legacy_flags` | complete_slice | Ports edit list shape independent of target platform. |
| `config_update.rs` | feature toggle default-false clearing | `tests/test_tui_config_update.py::test_build_feature_enabled_edit_clears_default_false_disabled_features` | complete_slice | Python accepts the feature catalog/default map as an injected interface instead of fabricating `codex_features::FEATURES`. |
| `config_update.rs` | memory and OSS provider edits | `tests/test_tui_config_update.py::test_build_memory_and_oss_provider_edits` | complete_slice | Ports simple config edit builders. |
| `config_update.rs` | app-server config/skill request helpers | `tests/test_tui_config_update.py::test_write_config_batch_sends_config_batch_write_request` | complete_slice | Uses semantic `ClientRequest` model and injected request handle, not a fake app-server transport. |
| `config_update.rs` | trusted project/read config/skill request helpers | `tests/test_tui_config_update.py::{test_write_trusted_project_uses_trusted_project_edit,test_read_effective_config_sends_config_read_request,test_write_skill_enabled_sends_skills_config_write_request}` | complete_slice | Ports request kind, params, and request-id prefix semantics; real app-server response typing remains caller-provided. |
| `config_update.rs` | app-server request-id prefixes | `tests/test_tui_config_update.py::{test_write_config_batch_sends_config_batch_write_request,test_read_effective_config_sends_config_read_request,test_write_skill_enabled_sends_skills_config_write_request}` | complete_slice | Aligns Python request ids with Rust prefixes: `tui-config-write-`, `tui-config-read-`, and `tui-skill-config-write-`. |
| `resize_reflow_cap.rs` | `auto_resize_reflow_max_rows_uses_terminal_defaults` | `tests/test_tui_resize_reflow_cap.py::test_auto_resize_reflow_max_rows_uses_terminal_defaults` | complete | Ports terminal-specific cap table and fallback default. |
| `resize_reflow_cap.rs` | `auto_resize_reflow_max_rows_prefers_vscode_probe` | `tests/test_tui_resize_reflow_cap.py::test_auto_resize_reflow_max_rows_prefers_vscode_probe` | complete | Ports VS Code environment probe precedence over terminal metadata. |
| `resize_reflow_cap.rs` | `configured_resize_reflow_max_rows_overrides_auto_detection` | `tests/test_tui_resize_reflow_cap.py::test_configured_resize_reflow_max_rows_overrides_auto_detection` | complete | Ports explicit limit override behavior. |
| `resize_reflow_cap.rs` | `disabled_resize_reflow_max_rows_keeps_all_rows` | `tests/test_tui_resize_reflow_cap.py::test_disabled_resize_reflow_max_rows_keeps_all_rows` | complete | Ports disabled row-cap behavior as `None`. |
| `resize_reflow_cap.rs` | `unknown_terminal_uses_fallback_even_under_multiplexer` | `tests/test_tui_resize_reflow_cap.py::test_unknown_terminal_uses_fallback_even_under_multiplexer` | complete | Ports fallback behavior when terminal name remains unknown under tmux. |
| `resize_reflow_cap.rs` | public resolver scalar compatibility | `tests/test_tui_resize_reflow_cap.py::test_public_resolver_accepts_scalar_config_shapes` | complete_slice | Python exposes deterministic injected terminal/config inputs instead of global terminal probing. |
| `service_tier_resolution.rs` | `configured_service_tier` explicit config and fast-default opt-out | `tests/test_tui_service_tier_resolution.py::test_configured_service_tier_prefers_explicit_config_then_opt_out_default` | complete | Ports explicit service tier precedence and opt-out default sentinel behavior. |
| `service_tier_resolution.rs` | FastMode guard for effective tier and core update | `tests/test_tui_service_tier_resolution.py::test_effective_service_tier_is_none_when_fast_mode_disabled` | complete | Ports early return when `Feature::FastMode` is disabled. |
| `service_tier_resolution.rs` | unknown model keeps configured tier | `tests/test_tui_service_tier_resolution.py::test_effective_service_tier_returns_configured_when_model_unknown` | complete | Ports configured-tier passthrough when no model preset is found. |
| `service_tier_resolution.rs` | default sentinel bypasses model tier support check | `tests/test_tui_service_tier_resolution.py::test_effective_service_tier_keeps_default_sentinel_even_if_not_in_model_tiers` | complete | Ports explicit `default` sentinel preservation. |
| `service_tier_resolution.rs` | unsupported configured tier clears effective tier and sends default update | `tests/test_tui_service_tier_resolution.py::test_effective_service_tier_drops_unsupported_configured_tier` | complete | Ports unsupported configured tier handling and core update fallback. |
| `service_tier_resolution.rs` | supported model default service tier | `tests/test_tui_service_tier_resolution.py::test_effective_service_tier_uses_supported_model_default_when_unconfigured` | complete | Ports unconfigured model default selection. |
| `service_tier_resolution.rs` | unsupported model default and unknown-model update suppression | `tests/test_tui_service_tier_resolution.py::{test_effective_service_tier_ignores_unsupported_model_default,test_service_tier_update_for_core_sends_no_update_for_unknown_model_without_effective_tier}` | complete | Ports fallback to default only for known models and no-update for unknown unconfigured models. |
| `service_tier_resolution.rs` | `model_supports_service_tier` | `tests/test_tui_service_tier_resolution.py::test_model_supports_service_tier_accepts_semantic_model_shapes` | complete_slice | Uses Python semantic `ModelPreset`/dict shapes instead of Rust protocol structs. |
| `collaboration_modes.rs` | `filtered_presets` TUI-visible filtering | `tests/test_tui_collaboration_modes.py::test_filtered_presets_keeps_only_tui_visible_modes` | complete_slice | Ports `ModeKind::is_tui_visible` filtering and keeps `ModelCatalog` ignored as in Rust. |
| `collaboration_modes.rs` | `default_mask` default preference and fallback | `tests/test_tui_collaboration_modes.py::test_default_mask_prefers_default_mode_then_first_visible` | complete | Ports default-mode preference, first-visible fallback, and empty-list None behavior. |
| `collaboration_modes.rs` | `mask_for_kind` visible-kind guard and lookup | `tests/test_tui_collaboration_modes.py::test_mask_for_kind_rejects_non_tui_visible_modes` | complete | Ports rejection of PairProgramming/Execute and visible preset lookup. |
| `collaboration_modes.rs` | `next_mask` list-order cycling | `tests/test_tui_collaboration_modes.py::test_next_mask_cycles_by_visible_preset_order` | complete | Ports current-kind matching, wraparound, missing-current fallback to first visible preset, and empty-list None. |
| `collaboration_modes.rs` | `default_mode_mask` / `plan_mask` helpers | `tests/test_tui_collaboration_modes.py::test_default_and_plan_helpers_delegate_to_mask_for_kind` | complete | Ports helper delegation to `mask_for_kind`. |
| `debug_config.rs` | `session_all_proxy_url_uses_socks_when_enabled` / `session_all_proxy_url_uses_http_when_socks_disabled` | `tests/test_tui_debug_config.py::test_session_all_proxy_url_uses_socks_or_http` | complete | Ports HTTP vs SOCKS proxy URL selection. |
| `debug_config.rs` | `debug_config_output_lists_all_layers_including_disabled` | `tests/test_tui_debug_config.py::test_debug_config_output_lists_all_layers_including_disabled` | complete_slice | Ports visible layer stack text, enabled/disabled status, disabled reason, and empty requirements display using string lines instead of ratatui `Line`. |
| `debug_config.rs` | `debug_config_output_lists_session_flag_key_value_pairs` | `tests/test_tui_debug_config.py::test_render_session_flag_details_flattens_sorted_key_value_pairs` | complete_slice | Ports sorted nested config flattening and TOML-like scalar formatting for session flags. |
| `debug_config.rs` | `debug_config_output_shows_legacy_mdm_layer_value` | `tests/test_tui_debug_config.py::test_render_mdm_layer_details_preserves_raw_multiline_value` | complete_slice | Ports raw multiline MDM value display. |
| `debug_config.rs` | `join_or_empty` and `requirement_line` helpers | `tests/test_tui_debug_config.py::test_requirement_and_join_helpers_match_visible_text_contract` | complete | Ports visible helper formatting. |
| `debug_config.rs` | `debug_config_output_normalizes_empty_web_search_mode_list` | `tests/test_tui_debug_config.py::test_normalize_allowed_web_search_modes_adds_disabled_and_handles_empty` | complete | Ports empty-list normalization to disabled and implicit disabled append. |
| `debug_config.rs` | `debug_config_output_formats_unix_socket_permissions` / network constraints | `tests/test_tui_debug_config.py::test_format_network_constraints_domains_and_unix_sockets_are_sorted` | complete_slice | Ports sorted domain/unix socket permission formatting and selected network fields. |
| `debug_config.rs` | `format_network_constraints` scalar field ordering | `tests/test_tui_debug_config.py::test_format_network_constraints_preserves_rust_scalar_field_order` | complete_slice | Pins Rust source-order formatting for enabled, proxy ports, upstream/non-loopback/socket flags, managed-domain-only, and local-binding fields. |
| `debug_config.rs` | `format_config_layer_source` variants | `tests/test_tui_debug_config.py::test_format_config_layer_source_variants` | complete_slice | Ports representative source labels for session flags, MDM, and legacy MDM. |
| `debug_config.rs` | `new_debug_config_output` session runtime proxy block | `tests/test_tui_debug_config.py::test_new_debug_config_output_appends_session_runtime_proxy_lines` | complete_slice | Ports visible proxy diagnostics block with injected config/proxy objects. |
| `debug_config.rs` | scalar TOML flattening and managed hooks requirements | `tests/test_tui_debug_config.py::{test_flatten_toml_key_values_uses_value_for_scalar_root,test_format_managed_hooks_requirements_includes_dirs_and_handlers}` | complete_slice | Ports helper-level behavior used by requirements display; full Rust config requirement object graph remains semantic/adapted. |
| `permission_compat.rs` | bridgeable profile returns unchanged | `tests/test_tui_permission_compat.py::test_legacy_compatible_permission_profile_preserves_bridgeable_profile` | complete_slice | Ports early return when `to_legacy_sandbox_policy(cwd)` succeeds. |
| `permission_compat.rs` | `compatibility_profile_preserves_unbridgeable_write_roots` | `tests/test_tui_permission_compat.py::test_compatibility_profile_preserves_unbridgeable_write_roots` | complete | Ports Rust unit test preserving extra writable root plus cwd in rebuilt workspace-write profile. |
| `permission_compat.rs` | rebuilt compatibility profile preserves network policy | `tests/test_tui_permission_compat.py::test_legacy_compatible_permission_profile_preserves_network_policy_when_rebuilt` | complete_slice | Captures Rust use of original `network_sandbox_policy` during fallback rebuild. |
| `permission_compat.rs` | fallback `/tmp` exclusion flag | `tests/test_tui_permission_compat.py::test_legacy_compatible_permission_profile_sets_slash_tmp_exclusion_from_write_access` | complete_slice | Covers Rust `slash_tmp_writable` branch: rebuilt workspace-write profile excludes `/tmp` unless `/tmp` exists and is writable under the source file-system policy. |
| `version.rs` | `CODEX_CLI_VERSION` compile-time package version | `tests/test_tui_version.py::test_codex_cli_version_matches_workspace_package_version` | complete | Ports `env!("CARGO_PKG_VERSION")`; upstream `codex-tui` currently inherits workspace version `0.0.0`. |
| `audio_device.rs` | `list_realtime_audio_device_names` de-duplication and name-error skip | `tests/test_tui_audio_device.py::test_list_realtime_audio_device_names_deduplicates_and_skips_name_errors` | complete_slice | Ports visible list behavior with injected host instead of real `cpal` backend. |
| `audio_device.rs` | `preferred_input_sample_rate` | `tests/test_tui_audio_device.py::test_preferred_input_sample_rate_clamps_to_supported_range` | complete | Ports preferred 24kHz clamp/selection behavior. |
| `audio_device.rs` | `preferred_input_config` ranking and fallback | `tests/test_tui_audio_device.py::{test_preferred_input_config_ranks_rate_then_channels_then_format,test_preferred_input_config_falls_back_to_default_when_no_supported_formats}` | complete_slice | Ports `(sample_rate_penalty, channel_penalty, sample_format_rank)` scoring and default-input fallback. |
| `audio_device.rs` | configured/default device selection | `tests/test_tui_audio_device.py::{test_select_configured_device_prefers_matching_name_then_default,test_select_configured_device_falls_back_to_default_when_named_device_missing}` | complete_slice | Ports configured-name preference and system-default fallback with injected host. |
| `audio_device.rs` | missing configured/default device errors from selection | `tests/test_tui_audio_device.py::{test_select_configured_device_reports_missing_default_with_configured_name,test_select_configured_device_reports_missing_default_without_configured_name}` | complete_slice | Covers Rust selection error boundary when configured devices are unavailable and no default input/output device exists. |
| `audio_device.rs` | `configured_name` and `missing_device_error` | `tests/test_tui_audio_device.py::{test_configured_name_reads_realtime_audio_fields,test_missing_device_error_messages_match_rust_text}` | complete | Ports microphone/speaker config lookup and exact error text. |
| `audio_device.rs` | real `cpal` host enumeration boundary | `tests/test_tui_audio_device.py::test_real_audio_enumeration_requires_injected_host` | blocked | Python does not silently fake OS audio devices; callers must inject a host or later wire a real audio backend. |
| `update_action.rs` | `maps_install_context_to_update_action` | `tests/test_tui_update_action.py::test_maps_install_context_to_update_action` | complete | Ports install method/platform mapping to update actions. |
| `update_action.rs` | `UpdateAction::command_args` command table | `tests/test_tui_update_action.py::test_update_action_command_args_match_rust_table` | complete | Ports npm, bun, and brew command argument mappings. |
| `update_action.rs` | `standalone_update_commands_rerun_latest_installer` | `tests/test_tui_update_action.py::test_standalone_update_commands_rerun_latest_installer` | complete | Ports Unix and Windows standalone installer command args. |
| `update_action.rs` | `UpdateAction::command_str` shell-joined command | `tests/test_tui_update_action.py::test_command_str_uses_shell_join_semantics` | complete_slice | Uses Python `shlex.join`, matching Rust `shlex::try_join` semantics for covered commands. |
| `update_action.rs` | `get_update_action` install-context boundary | `tests/test_tui_update_action.py::test_get_update_action_requires_injected_context_or_detector` | blocked | Python requires injected install context/detector until `InstallContext::current` is wired; no silent install-source fabrication. |
| `update_versions.rs` | `extracts_version_from_latest_tag` | `tests/test_tui_update_versions.py::test_extracts_version_from_latest_tag` | complete | Ports `rust-v` prefix stripping and version extraction. |
| `update_versions.rs` | `latest_tag_without_prefix_is_invalid` | `tests/test_tui_update_versions.py::test_latest_tag_without_prefix_is_invalid` | complete | Invalid latest tag prefix raises an explicit parse error. |
| `update_versions.rs` | `prerelease_version_is_not_considered_newer` | `tests/test_tui_update_versions.py::test_prerelease_version_is_not_considered_newer` | complete | Prerelease suffix in the third component is rejected, matching Rust `u64` parse failure semantics. |
| `update_versions.rs` | `plain_semver_comparisons_work` | `tests/test_tui_update_versions.py::test_plain_semver_comparisons_work` | complete | Compares parsed major/minor/patch tuples like Rust tuple ordering. |
| `update_versions.rs` | `source_build_version_is_not_checked` | `tests/test_tui_update_versions.py::test_source_build_version_is_not_checked` | complete | Mirrors Rust source-build sentinel version `0.0.0`. |
| `update_versions.rs` | `whitespace_is_ignored` | `tests/test_tui_update_versions.py::test_whitespace_is_ignored` | complete | Preserves Rust trim-before-parse behavior. |
| `update_versions.rs` | `parse_version` edge cases | `tests/test_tui_update_versions.py::test_parse_version_matches_rust_u64_components` | complete | Covers malformed, signed, empty, u64 overflow, and extra-component parsing behavior inferred from Rust source. |
| `update_prompt.rs` | `update_prompt_snapshot` visible modal contract | `tests/test_tui_update_prompt.py::test_update_prompt_snapshot_visible_contract` | complete_slice | Ports visible title, version transition, release notes URL, choices, command text, and Enter hint as semantic text lines instead of VT100 snapshot. |
| `update_prompt.rs` | `update_prompt_confirm_selects_update` | `tests/test_tui_update_prompt.py::test_update_prompt_confirm_selects_update` | complete | Ports Enter selecting the default highlighted update action. |
| `update_prompt.rs` | `update_prompt_dismiss_option_leaves_prompt_in_normal_state` | `tests/test_tui_update_prompt.py::test_update_prompt_dismiss_option_leaves_prompt_in_normal_state` | complete | Ports Down then Enter selecting Skip/NotNow. |
| `update_prompt.rs` | `update_prompt_dont_remind_selects_dismissal` | `tests/test_tui_update_prompt.py::test_update_prompt_dont_remind_selects_dismissal` | complete | Ports two-step Down navigation and dismissal selection. |
| `update_prompt.rs` | `update_prompt_ctrl_c_skips_update` | `tests/test_tui_update_prompt.py::test_update_prompt_ctrl_c_skips_update` | complete | Ports Ctrl-C/Ctrl-D skip behavior. |
| `update_prompt.rs` | `update_prompt_navigation_wraps_between_entries` | `tests/test_tui_update_prompt.py::test_update_prompt_navigation_wraps_between_entries` | complete | Ports Up/Down cyclic selection navigation. |
| `update_prompt.rs` | numeric shortcuts, Escape, release-key filtering, frame scheduling | `tests/test_tui_update_prompt.py::{test_update_prompt_numeric_and_escape_shortcuts,test_update_prompt_ignores_release_key_and_schedules_on_highlight_change}` | complete_slice | Captures important internal state transitions inferred from Rust source. |
| `update_prompt.rs` | `run_update_prompt_if_needed` dependency and outcome flow | `tests/test_tui_update_prompt.py::{test_run_update_prompt_returns_run_update_and_clears_terminal,test_run_update_prompt_dismisses_version_on_dont_remind,test_run_update_prompt_continues_when_dependencies_absent}` | complete_slice | Uses injected latest-version/update-action/update modules and semantic TUI event stream; real ratatui draw loop and terminal buffer remain adapted. |
| `update_prompt.rs` | `WidgetRef`-style prompt rendering through `Rect`/`Buffer`/`Clear`/`Line`/`Span` | `tests/test_tui_update_prompt.py::{test_update_prompt_renders_to_bridge_buffer_and_clears_area,test_update_prompt_bridge_render_tracks_highlight,test_update_prompt_module_render_ref_keeps_snapshot_compatibility}` | complete_slice | Adds real ratatui-bridge buffer mutation for the prompt while preserving the existing semantic snapshot helper; terminal OSC8 hyperlink marking remains a terminal/runtime boundary. |
| `updates.rs` | `version_filepath` / `read_version_info` | `tests/test_tui_updates.py::test_version_filepath_and_read_version_info` | complete | Ports `codex_home/version.json` path and JSON cache parse including dismissed version. |
| `updates.rs` | `get_upgrade_version` disabled/source-build/cache-newer behavior | `tests/test_tui_updates.py::test_get_upgrade_version_respects_disabled_source_build_and_cached_newer` | complete_slice | Ports local decision logic with injected current version and clock. |
| `updates.rs` | stale or missing cache schedules background refresh | `tests/test_tui_updates.py::test_get_upgrade_version_schedules_refresh_for_missing_or_stale_cache` | complete_slice | Python uses injected background scheduler instead of spawning a Tokio task. |
| `updates.rs` | `get_upgrade_version_for_popup` dismissal filter | `tests/test_tui_updates.py::test_get_upgrade_version_for_popup_honors_dismissed_version` | complete | Ports exact-version dismissal suppression and newer-version re-show behavior. |
| `updates.rs` | `dismiss_version` | `tests/test_tui_updates.py::test_dismiss_version_updates_existing_cache_and_missing_cache_is_noop` | complete | Ports no-op on missing cache and cache rewrite preserving latest/checked fields. |
| `updates.rs` | `fetch_latest_github_release_version` | `tests/test_tui_updates.py::test_fetch_latest_github_release_version_extracts_rust_tag` | complete_slice | Uses injected JSON getter; ports GitHub tag extraction through `update_versions`. |
| `updates.rs` | `check_for_update` remote source selection by update action | `tests/test_tui_updates.py::test_fetch_latest_version_for_action_uses_expected_remote_source` | complete_slice | Ports Homebrew vs GitHub+npm vs GitHub-only source selection; real HTTP and npm readiness are explicit injected boundaries. |
| `updates.rs` | `check_for_update` cache write and dismissed preservation | `tests/test_tui_updates.py::test_check_for_update_writes_cache_and_preserves_dismissal` | complete_slice | Ports cache write shape and preservation of previously dismissed version with injected clock. |
| `npm_registry.rs` | `ready_version_requires_latest_dist_tag_and_root_dist` | `tests/test_tui_npm_registry.py::test_ready_version_requires_latest_dist_tag_and_root_dist` | complete | Ports successful readiness check for matching `latest` dist-tag and complete dist metadata. |
| `npm_registry.rs` | `ready_version_rejects_stale_latest_dist_tag` | `tests/test_tui_npm_registry.py::test_ready_version_rejects_stale_latest_dist_tag` | complete | Ports stale npm latest dist-tag rejection and error text anchor. |
| `npm_registry.rs` | `ready_version_rejects_missing_root_dist` | `tests/test_tui_npm_registry.py::test_ready_version_rejects_missing_root_dist` | complete | Ports missing dist metadata rejection. |
| `npm_registry.rs` | `ensure_version_ready` missing dist-tag/version/tarball/integrity branches | `tests/test_tui_npm_registry.py::{test_ready_version_rejects_missing_latest_dist_tag,test_ready_version_rejects_missing_version_tarball_and_integrity}` | complete_slice | Captures important error branches inferred from Rust source. |
| `npm_registry.rs` | version trim before readiness comparison | `tests/test_tui_npm_registry.py::test_version_is_trimmed_before_latest_dist_tag_comparison` | complete | Ports Rust `version.trim()` behavior. |
| `npm_registry.rs` | `version_info_with_dist` return contract | `tests/test_tui_npm_registry.py::test_version_info_with_dist_returns_parsed_version_info` | complete_slice | Exposes helper as Python semantic return object equivalent to Rust borrowed version info. |
| `npm_registry.rs` | `PACKAGE_URL` release registry endpoint | `tests/test_tui_npm_registry.py::test_package_url_matches_rust_release_registry_url` | complete | Ports encoded npm package registry URL. |
| `notifications/bel.rs` | `PostNotification::write_ansi` BEL command output | `tests/test_tui_notifications_bel.py::test_post_notification_write_ansi_emits_bel` | complete | Ports crossterm command ANSI output as semantic stream write of `\\x07`. |
| `notifications/bel.rs` | module-level `write_ansi` helper | `tests/test_tui_notifications_bel.py::test_module_write_ansi_helper_emits_bel` | complete | Python exposes helper equivalent for direct tests/callers. |
| `notifications/bel.rs` | `BelBackend::notify` ignores message and emits BEL | `tests/test_tui_notifications_bel.py::test_bel_backend_notify_ignores_message_and_flushes_stream` | complete | Uses injectable stream instead of real stdout while preserving BEL output and flush side effect. |
| `notifications/bel.rs` | Windows WinAPI rejection and ANSI support | `tests/test_tui_notifications_bel.py::test_windows_winapi_path_is_explicitly_rejected_and_ansi_supported` | complete | Ports Rust Windows branch semantics: WinAPI path errors, ANSI is supported. |
| `notifications/osc9.rs` | `post_notification_writes_plain_osc9_sequence` | `tests/test_tui_notifications_osc9.py::test_post_notification_writes_plain_osc9_sequence` | complete | Ports plain OSC 9 ANSI sequence `ESC ] 9 ; message BEL`. |
| `notifications/osc9.rs` | `post_notification_writes_tmux_dcs_wrapped_osc9_sequence` | `tests/test_tui_notifications_osc9.py::test_post_notification_writes_tmux_dcs_wrapped_osc9_sequence` | complete | Ports tmux DCS passthrough wrapper and doubled initial ESC before OSC. |
| `notifications/osc9.rs` | `post_notification_escapes_escape_bytes_inside_tmux_payload` | `tests/test_tui_notifications_osc9.py::test_post_notification_escapes_escape_bytes_inside_tmux_payload` | complete | Ports payload ESC-byte doubling inside tmux passthrough. |
| `notifications/osc9.rs` | `escape_tmux_dcs_passthrough_payload` helper | `tests/test_tui_notifications_osc9.py::test_escape_tmux_dcs_passthrough_payload_doubles_only_escape_bytes` | complete_slice | Captures helper behavior inferred from Rust source. |
| `notifications/osc9.rs` | `Osc9Backend::notify` passthrough flag and stream side effect | `tests/test_tui_notifications_osc9.py::test_osc9_backend_notify_uses_passthrough_flag_and_flushes` | complete_slice | Uses injectable stream and explicit passthrough flag; parent terminal/multiplexer detection belongs to `notifications/mod.rs`. |
| `notifications/osc9.rs` | default backend construction | `tests/test_tui_notifications_osc9.py::test_default_backend_is_plain_osc9_until_parent_detection_sets_tmux_flag` | complete_slice | Python default is plain unless caller injects tmux flag; real `terminal_info()` detection remains parent-module scope. |
| `notifications/osc9.rs` | Windows WinAPI rejection and ANSI support | `tests/test_tui_notifications_osc9.py::test_windows_winapi_path_is_explicitly_rejected_and_ansi_supported` | complete | Ports Rust Windows branch semantics: WinAPI path errors, ANSI is supported. |
| `notifications/mod.rs` | `selects_osc9_method` | `tests/test_tui_notifications.py::test_selects_osc9_method` | complete | Ports explicit `NotificationMethod::Osc9` backend selection. |
| `notifications/mod.rs` | `selects_bel_method` | `tests/test_tui_notifications.py::test_selects_bel_method` | complete | Ports explicit `NotificationMethod::Bel` backend selection. |
| `notifications/mod.rs` | `supports_osc9_for_supported_terminals` | `tests/test_tui_notifications.py::test_supports_osc9_for_supported_terminals` | complete | Ports Ghostty, iTerm2, Kitty, WarpTerminal, and WezTerm OSC9 allow-list. |
| `notifications/mod.rs` | `supports_osc9_for_unsupported_terminals` | `tests/test_tui_notifications.py::test_supports_osc9_for_unsupported_terminals` | complete | Ports unsupported terminal deny-list from Rust tests. |
| `notifications/mod.rs` | Auto backend detection | `tests/test_tui_notifications.py::test_auto_detects_osc9_only_for_supported_terminal` | complete_slice | Uses injected semantic `TerminalInfo` instead of global `terminal_info()` side effect. |
| `notifications/mod.rs` | `DesktopNotificationBackend::notify` dispatch | `tests/test_tui_notifications.py::test_notify_delegates_to_selected_backend` | complete_slice | Delegates to implemented OSC9/BEL Python backends with injectable streams. |
| `notifications/mod.rs` | tmux passthrough propagation for OSC9 backend | `tests/test_tui_notifications.py::test_auto_tmux_supported_terminal_sets_osc9_passthrough` | complete_slice | Parent module sets OSC9 passthrough from semantic multiplexer info; real terminal detection remains external. |
| `public_widgets/mod.rs` | package boundary declares only `composer_input` | `tests/test_tui_public_widgets.py::test_public_widgets_declares_composer_input_submodule` | complete | Rust module is a facade with a single `pub(crate) mod composer_input;`; Python mirrors the package boundary and does not mark `public_widgets::composer_input` behavior complete here. |
| `key_hint.rs` | `is_press_accepts_press_and_repeat_but_rejects_release` | `tests/test_tui_key_hint.py::test_is_press_accepts_press_and_repeat_but_rejects_release` | complete | Ports press/repeat acceptance, release rejection, and wrong-modifier rejection. |
| `key_hint.rs` | `keybinding_list_ext_matches_any_binding` | `tests/test_tui_key_hint.py::test_keybinding_list_ext_matches_any_binding` | complete | Ports list-of-alternatives matching semantics as Python `is_pressed`. |
| `key_hint.rs` | shifted letter uppercase compatibility tests | `tests/test_tui_key_hint.py::{test_shifted_letter_binding_matches_uppercase_char_events,test_shift_letter_binding_preserves_other_modifiers_with_uppercase_compat,test_shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase}` | complete | Ports uppercase events being normalized to lower-case plus SHIFT while preserving other modifiers. |
| `key_hint.rs` | C0 control-char compatibility tests | `tests/test_tui_key_hint.py::{test_ctrl_letter_binding_matches_c0_control_char_events,test_ctrl_bindings_match_all_supported_c0_control_char_events,test_ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete,test_history_search_ctrl_bindings_match_c0_control_char_events}` | complete | Ports raw C0 mapping for ctrl-space, ctrl-a..z, ctrl-4..7 and rejection of ESC/delete ambiguity. |
| `key_hint.rs` | `ctrl_alt_sets_both_modifiers` | `tests/test_tui_key_hint.py::test_ctrl_alt_sets_both_modifiers` | complete | Ports combined CONTROL+ALT binding constructor. |
| `key_hint.rs` | `has_ctrl_or_alt_checks_supported_modifier_combinations` | `tests/test_tui_key_hint.py::test_has_ctrl_or_alt_checks_supported_modifier_combinations` | complete | Ports ctrl/alt detection with platform-aware AltGr boundary. |
| `key_hint.rs` | `normalize_key_parts` helper | `tests/test_tui_key_hint.py::test_normalize_key_parts_uppercase_and_raw_c0` | complete | Captures helper-level uppercase and raw C0 normalization behavior. |
| `key_hint.rs` | `is_plain_text_key_event` | `tests/test_tui_key_hint.py::test_is_plain_text_key_event_allows_printable_non_ctrl_alt` | complete | Ports printable text-input boundary independent of navigation matching. |
| `key_hint.rs` | display label / Span conversion / dim style | `tests/test_tui_key_hint.py::test_display_label_and_span_style` | complete | Uses Python semantic `Span`/style instead of ratatui `Span`, preserving visible labels and dim style contract. |
| `key_hint.rs` | `ALT_PREFIX` display label | `tests/test_tui_key_hint.py::test_display_label_and_span_style` | complete | Restores the Rust test-path Option/Alt symbol prefix (`⌥ + `) for semantic key-hint labels instead of preserving local encoding damage. |
| `key_hint.rs` | `KeyBinding::from_event` normalization | `tests/test_tui_key_hint.py::test_keybinding_from_event_uses_normalization` | complete | Ports event-to-binding normalization shape. |
| `tooltips.rs` | `random_tooltip_returns_some_tip_when_available` | `tests/test_tui_tooltips.py::test_random_tooltip_returns_some_tip_when_available` | complete_slice | Ports non-empty tooltip pool selection using Python seeded RNG and embedded upstream `tooltips.txt` content. |
| `tooltips.rs` | `random_tooltip_is_reproducible_with_seed` | `tests/test_tui_tooltips.py::test_random_tooltip_is_reproducible_with_seed` | complete_slice | Preserves deterministic selection under seeded RNG. |
| `tooltips.rs` | `paid_tooltip_pool_rotates_between_promos` | `tests/test_tui_tooltips.py::test_paid_tooltip_pool_rotates_between_promos` | complete_slice | Ports paid promo split between app tooltip and Fast tooltip with platform-aware app availability. |
| `tooltips.rs` | `paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled` | `tests/test_tui_tooltips.py::test_paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled` | complete_slice | Ports suppression of Fast promo when Fast mode is already enabled. |
| `tooltips.rs` | `announcement_tip_toml_picks_last_matching` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_picks_last_matching` | complete | Ports last matching announcement wins and default `target_app = cli`. |
| `tooltips.rs` | `announcement_tip_toml_picks_no_match` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_picks_no_match` | complete | Ports no-match behavior for expired, version-mismatched, and non-cli announcements. |
| `tooltips.rs` | `announcement_tip_toml_bad_deserialization` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_bad_deserialization` | complete | Ports invalid TOML/schema returning None. |
| `tooltips.rs` | `announcement_tip_toml_parse_comments` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_parse_comments` | complete | Ports TOML comment handling and latest matching fallback. |
| `tooltips.rs` | `announcement_tip_toml_matches_target_plan_type` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_matches_target_plan_type` | complete | Ports plan-specific announcements and all-plan fallback. |
| `tooltips.rs` | `announcement_tip_toml_rejects_unknown_target_plan_type` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_rejects_unknown_target_plan_type` | complete_slice | Python maps unknown plan tokens to skipped announcement, matching Rust serde `Unknown` rejection intent. |
| `tooltips.rs` | `announcement_tip_toml_matches_target_os` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_matches_target_os` | complete | Ports current OS filtering. |
| `tooltips.rs` | `announcement_tip_toml_rejects_unknown_target_os` | `tests/test_tui_tooltips.py::test_announcement_tip_toml_rejects_unknown_target_os` | complete | Ports unknown OS target rejection. |
| `tooltips.rs` | `get_tooltip` announcement/free/other decision flow | `tests/test_tui_tooltips.py::test_get_tooltip_prefers_announcement_then_plan_specific_paths` | complete_slice | Uses injected announcement and RNG; real remote announcement prewarm remains an explicit boundary. |
| `tooltips.rs` | `blocking_init_announcement_tip` remote fetch | N/A | blocked | Rust performs a blocking reqwest fetch with timeout/no-proxy; Python requires injected fetcher and does not silently perform network I/O. |
| `custom_terminal.rs` | `display_width` ignores OSC escape sequences | `tests/test_tui_custom_terminal.py::test_display_width_ignores_osc_sequences` | complete_slice | Ports the display-width helper that strips OSC `ESC ] ... BEL` sequences before width calculation. |
| `custom_terminal.rs` | `diff_buffers_does_not_emit_clear_to_end_for_full_width_row` | `tests/test_tui_custom_terminal.py::test_diff_buffers_does_not_emit_clear_to_end_for_full_width_row` | complete_slice | Ports tested ClearToEnd suppression and final-cell Put behavior with Python semantic `Buffer`/`Cell`. |
| `custom_terminal.rs` | `diff_buffers_clear_to_end_starts_after_wide_char` | `tests/test_tui_custom_terminal.py::test_diff_buffers_clear_to_end_starts_after_wide_char` | complete_slice | Ports wide-character rightmost-column handling using semantic display width. |
| `custom_terminal.rs` | `terminal_draw_applies_requested_cursor_style` | `tests/test_tui_custom_terminal.py::test_terminal_draw_applies_requested_cursor_style` | complete_slice | Uses Python capture backend and semantic cursor-style sequences instead of crossterm queue internals. |
| `custom_terminal.rs` | `reset_cursor_style_emits_default_user_shape` | `tests/test_tui_custom_terminal.py::test_reset_cursor_style_emits_default_user_shape` | complete_slice | Ports default cursor-shape reset visible output contract. |
| `custom_terminal.rs` | visible history row cap / scrollback ANSI state reset | `tests/test_tui_custom_terminal.py::{test_terminal_visible_history_rows_are_capped_by_viewport_top,test_clear_scrollback_and_visible_screen_ansi_resets_state}` | complete_slice | Captures important state transitions from Rust source beyond explicit tests. |
| `custom_terminal.rs` | full ratatui terminal/backend integration | N/A | blocked | Python currently provides a semantic buffer/backend model; full ratatui-compatible terminal rendering and crossterm command queue are intentionally not fabricated. |
| `streaming/chunking.rs` | `smooth_mode_is_default` | `tests/test_tui_streaming_chunking.py::test_smooth_mode_is_default` | complete | Ports default smooth-mode state. |
| `streaming/chunking.rs` | `enters_catch_up_on_depth_threshold` | `tests/test_tui_streaming_chunking.py::test_enters_catch_up_on_depth_threshold` | complete | Ports depth-triggered catch-up entry and batch drain. |
| `streaming/chunking.rs` | `enters_catch_up_on_age_threshold` | `tests/test_tui_streaming_chunking.py::test_enters_catch_up_on_age_threshold` | complete | Ports oldest-age-triggered catch-up entry. |
| `streaming/chunking.rs` | `severe_backlog_uses_faster_paced_batches` | `tests/test_tui_streaming_chunking.py::test_severe_backlog_uses_faster_paced_batches` | complete | Ports severe backlog batch plan behavior. |
| `streaming/chunking.rs` | `catch_up_batch_drains_current_backlog` | `tests/test_tui_streaming_chunking.py::test_catch_up_batch_drains_current_backlog` | complete | Ports current-backlog batch sizing while already in catch-up. |
| `streaming/chunking.rs` | `exits_catch_up_after_hysteresis_hold` | `tests/test_tui_streaming_chunking.py::test_exits_catch_up_after_hysteresis_hold` | complete | Ports exit hysteresis hold and smooth drain return. |
| `streaming/chunking.rs` | `drops_back_to_smooth_when_idle` | `tests/test_tui_streaming_chunking.py::test_drops_back_to_smooth_when_idle` | complete | Ports idle queue immediate smooth-mode reset and exit timestamp note. |
| `streaming/chunking.rs` | `holds_reentry_after_catch_up_exit` | `tests/test_tui_streaming_chunking.py::test_holds_reentry_after_catch_up_exit` | complete | Ports re-entry suppression after catch-up exit. |
| `streaming/chunking.rs` | `severe_backlog_can_reenter_during_hold` | `tests/test_tui_streaming_chunking.py::test_severe_backlog_can_reenter_during_hold` | complete | Ports severe backlog bypassing re-entry hold. |
| `streaming/chunking.rs` | `should_exit_catch_up` oldest-age `Option::is_some_and` boundary | `tests/test_tui_streaming_chunking.py::test_exit_requires_oldest_age_to_be_known` | complete_slice | Captures source-inferred None-age exit rejection. |
| `streaming/commit_tick.rs` | `CommitTickOutput::default` | `tests/test_tui_streaming_commit_tick.py::test_default_commit_tick_output_matches_rust_default` | complete | Ports default no-commit output shape. |
| `streaming/commit_tick.rs` | `stream_queue_snapshot` | `tests/test_tui_streaming_commit_tick.py::{test_stream_queue_snapshot_sums_depth_and_keeps_max_oldest_age,test_stream_queue_snapshot_preserves_present_age_when_other_missing}` | complete_slice | Rust has no local tests; Python tests anchor queue-depth sum and max optional duration behavior from source. |
| `streaming/commit_tick.rs` | `max_duration` | `tests/test_tui_streaming_commit_tick.py::test_max_duration_matches_optional_duration_rules` | complete_slice | Ports helper optional-duration merge semantics. |
| `streaming/commit_tick.rs` | `apply_commit_tick_plan` / `drain_*_controller` | `tests/test_tui_streaming_commit_tick.py::{test_apply_single_plan_drains_stream_then_plan_and_tracks_idle,test_apply_batch_plan_uses_batch_api_on_both_controllers}` | complete_slice | Uses Python fake controllers to preserve Rust orchestration order and idle aggregation without implementing downstream controller internals. |
| `streaming/commit_tick.rs` | `run_commit_tick` scope and policy flow | `tests/test_tui_streaming_commit_tick.py::{test_run_commit_tick_catch_up_only_suppresses_smooth_drain,test_run_commit_tick_any_mode_applies_smooth_single_drain,test_run_commit_tick_enters_catch_up_and_batches_current_backlog}` | complete_slice | Ports scope suppression, chunking-policy resolution, and drain-plan application. |
| `streaming/table_holdback.rs` | `table_holdback_state_detects_header_plus_delimiter` | `tests/test_tui_streaming_table_holdback.py::test_table_holdback_state_detects_header_plus_delimiter` | complete | Ports confirmed table detection for header + delimiter pair. |
| `streaming/table_holdback.rs` | `table_holdback_state_detects_single_column_header_plus_delimiter` | `tests/test_tui_streaming_table_holdback.py::test_table_holdback_state_detects_single_column_header_plus_delimiter` | complete | Ports single-column pipe-table detection. |
| `streaming/table_holdback.rs` | `table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence` | `tests/test_tui_streaming_table_holdback.py::test_table_holdback_state_ignores_table_like_lines_inside_unclosed_long_fence` | complete | Ports non-markdown fence suppression. |
| `streaming/table_holdback.rs` | `table_holdback_state_treats_indented_fence_text_as_plain_content` | `tests/test_tui_streaming_table_holdback.py::test_table_holdback_state_treats_indented_fence_text_as_plain_content` | complete | Ports indented fence-like text as plain content. |
| `streaming/table_holdback.rs` | `table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence` | `tests/test_tui_streaming_table_holdback.py::test_table_holdback_state_ignores_table_like_lines_inside_blockquoted_other_fence` | complete | Ports blockquoted non-markdown fence suppression. |
| `streaming/table_holdback.rs` | `incremental_holdback_matches_stateless_scan_per_chunk` | `tests/test_tui_streaming_table_holdback.py::test_incremental_holdback_matches_stateless_scan_per_chunk` | complete | Ports incremental scanner parity against stateless helper. |
| `streaming/table_holdback.rs` | `incremental_holdback_detects_header_delimiter_across_chunk_boundary` | `tests/test_tui_streaming_table_holdback.py::test_incremental_holdback_detects_header_delimiter_across_chunk_boundary` | complete | Ports pending header then confirmed table transition across chunks. |
| `streaming/table_holdback.rs` | `table_candidate_text` and source byte offsets | `tests/test_tui_streaming_table_holdback.py::{test_table_candidate_text_strips_blockquotes_and_requires_pipe_segments,test_parse_lines_with_fence_state_reports_source_byte_offsets,test_scanner_reset_clears_confirmed_state}` | complete_slice | Captures source-inferred helper behavior and byte-offset scanner reset semantics. |
| `streaming/mod.rs` | `drain_n_clamps_to_available_lines` | `tests/test_tui_streaming_state.py::test_drain_n_clamps_to_available_lines` | complete | Ports Rust unit test for clamped FIFO drain behavior. |
| `streaming/mod.rs` | `StreamState::step` | `tests/test_tui_streaming_state.py::test_step_drains_one_queued_line_from_front` | complete_slice | Captures source-inferred FIFO one-line drain semantics. |
| `streaming/mod.rs` | `StreamState::clear` | `tests/test_tui_streaming_state.py::test_clear_resets_collector_queue_and_delta_flag` | complete_slice | Calls injected collector.clear and resets queue/lifecycle state. |
| `streaming/mod.rs` | `StreamState::clear_queue` | `tests/test_tui_streaming_state.py::test_clear_queue_keeps_collector_and_delta_flag` | complete_slice | Ports queue-only clear behavior. |
| `streaming/mod.rs` | `queued_len` / `oldest_queued_age` | `tests/test_tui_streaming_state.py::test_queued_len_and_oldest_queued_age_track_fifo_head` | complete_slice | Ports queue-depth and oldest queued age semantics with saturating non-negative age. |
| `streaming/mod.rs` | `drain_n` zero/negative Python boundary | `tests/test_tui_streaming_state.py::test_drain_n_zero_and_negative_do_not_drain` | complete_slice | Rust `usize` prevents negative input; Python clamps it to the same no-drain safety boundary as zero. |
| `diff_model.rs` | `FileChange::Add` serde tag/content shape | `tests/test_tui_diff_model.py::test_file_change_add_serializes_with_snake_case_tag` | complete | Ports Rust `#[serde(tag = "type", rename_all = "snake_case")]` add variant shape. |
| `diff_model.rs` | `FileChange::Delete` serde tag/content shape | `tests/test_tui_diff_model.py::test_file_change_delete_serializes_with_snake_case_tag` | complete | Ports delete variant shape. |
| `diff_model.rs` | `FileChange::Update` unified diff and optional move path | `tests/test_tui_diff_model.py::test_file_change_update_serializes_unified_diff_and_optional_move_path` | complete | Ports update variant shape and `Option<PathBuf>` as string/None semantic path. |
| `diff_model.rs` | unknown/malformed serde variant rejection | `tests/test_tui_diff_model.py::test_file_change_rejects_unknown_or_malformed_variants` | complete_slice | Captures Rust serde rejection behavior for unknown tags and missing/wrong-typed fields. |
| `app_server_approval_conversions.rs` | `converts_file_update_changes_to_display` | `tests/test_tui_app_server_approval_conversions.py::test_converts_file_update_changes_to_display_add` | complete | Ports Rust test for Add patch display conversion. |
| `app_server_approval_conversions.rs` | `FileUpdateChange` Delete/Update conversion | `tests/test_tui_app_server_approval_conversions.py::test_converts_file_update_changes_to_display_delete_and_update` | complete | Captures source-inferred Delete and Update/move_path mapping to `FileChange`. |
| `app_server_approval_conversions.rs` | `converts_request_permissions_into_granted_permissions` | `tests/test_tui_app_server_approval_conversions.py::test_converts_request_permissions_into_granted_permissions` | complete | Ports network enabled and filesystem permission passthrough conversion. |
| `app_server_approval_conversions.rs` | `converts_request_permissions_into_canonical_granted_permissions` | `tests/test_tui_app_server_approval_conversions.py::test_converts_request_permissions_into_canonical_granted_permissions` | complete | Ports canonical filesystem entries passthrough with no network permissions. |
| `app_server_approval_conversions.rs` | narrow field conversion and rejection boundaries | `tests/test_tui_app_server_approval_conversions.py::{test_conversions_accept_mapping_payloads,test_rejects_unknown_patch_kind_and_relative_absolute_path_helper}` | complete | Python accepts mapping/object payloads while preserving Rust field semantics and explicit errors for unknown patch kinds/non-absolute helper paths. |
| `approval_events.rs` | `ExecApprovalRequestEvent::effective_approval_id` | `tests/test_tui_approval_events.py::test_effective_approval_id_falls_back_to_call_id` | complete | Ports approval_id fallback to call_id. |
| `approval_events.rs` | `ExecApprovalRequestEvent::effective_available_decisions` explicit list | `tests/test_tui_approval_events.py::test_effective_available_decisions_preserves_explicit_list` | complete | Ports explicit available decisions clone semantics. |
| `approval_events.rs` | network-context default decisions | `tests/test_tui_approval_events.py::{test_default_decisions_for_network_context_include_allow_amendment,test_default_decisions_for_network_context_without_allow_amendment}` | complete | Ports Accept, AcceptForSession, first Allow network amendment, Cancel ordering. |
| `approval_events.rs` | additional-permissions default decisions | `tests/test_tui_approval_events.py::test_default_decisions_for_additional_permissions` | complete | Ports Accept/Cancel branch for additional permissions. |
| `approval_events.rs` | execpolicy/default exec decisions | `tests/test_tui_approval_events.py::{test_default_decisions_for_execpolicy_amendment,test_default_decisions_plain_exec}` | complete | Ports Accept, optional execpolicy amendment, Cancel branch. |
| `approval_events.rs` | `ApplyPatchApprovalRequestEvent` fields and change validation | `tests/test_tui_approval_events.py::{test_apply_patch_approval_request_normalizes_paths_and_keeps_optional_fields,test_apply_patch_approval_request_rejects_invalid_change_values}` | complete | Ports TUI-owned patch approval request shape using Python semantic `FileChange`. |
| `app_command.rs` | simple unit constructors | `tests/test_tui_app_command.py::test_simple_constructors_create_expected_variants` | complete_slice | Rust has no local tests; Python anchors constructor behavior for no-payload variants. |
| `app_command.rs` | payload constructors | `tests/test_tui_app_command.py::test_payload_constructors_match_rust_variant_fields` | complete_slice | Ports command, exec approval, patch approval, thread name, and rollback payload shapes. |
| `app_command.rs` | `AppCommand::user_turn` | `tests/test_tui_app_command.py::test_user_turn_sets_approvals_reviewer_to_none` | complete_slice | Ports user turn constructor payload and `approvals_reviewer: None` default. |
| `app_command.rs` | `AppCommand::override_turn_context` | `tests/test_tui_app_command.py::test_override_turn_context_preserves_nested_options` | complete_slice | Ports override context payload fields without flattening nested option-like values. |
| `app_command.rs` | realtime, elicitation, user input, permission response constructors | `tests/test_tui_app_command.py::test_realtime_elicitation_user_input_and_permissions_commands` | complete_slice | Ports non-turn payload variant constructors. |
| `app_command.rs` | list skills, review, guardian, `is_review` | `tests/test_tui_app_command.py::test_list_skills_review_guardian_and_is_review` | complete_slice | Ports list skills path normalization and Review-only predicate. |
| `app_command.rs` | `From<&AppCommand> for AppCommand` clone behavior | `tests/test_tui_app_command.py::{test_from_clones_app_command_payload,test_from_rejects_non_app_command}` | complete_slice | Python `from_` mirrors clone behavior with deep payload copy for mutable semantic payloads. |
| `app_event_sender.rs` | `AppEventSender::send` logging and send behavior | `tests/test_tui_app_event_sender.py::test_send_logs_only_non_codex_op_events_and_sends_to_target` | complete | Ports non-CodexOp inbound logging boundary and event forwarding with Python semantic events. |
| `app_event_sender.rs` | failed send is swallowed after logging | `tests/test_tui_app_event_sender.py::test_send_swallows_send_errors_after_error_logging` | complete | Mirrors Rust channel-send error handling without raising to caller. |
| `app_event_sender.rs` | CodexOp helper methods | `tests/test_tui_app_event_sender.py::test_codex_op_helpers_send_expected_commands` | complete | Ports interrupt, compact, set_thread_name, review, list_skills, realtime audio, and user_input_answer helper wrappers. |
| `app_event_sender.rs` | SubmitThreadOp helper methods | `tests/test_tui_app_event_sender.py::test_thread_op_helpers_submit_expected_commands` | complete | Ports exec approval, permissions response, patch approval, and elicitation helper wrappers. |
| `app_event_sender.rs` | channel-like target boundary | `tests/test_tui_app_event_sender.py::test_sender_accepts_send_method_targets` | complete | Uses semantic send-like target in place of Tokio `UnboundedSender`. |

### app_event_sender.rs - complete

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `app_event_sender.rs` `AppEventSender::{new,send,interrupt,compact,set_thread_name,review,list_skills,realtime_conversation_audio,user_input_answer,exec_approval,request_permissions_response,patch_approval,resolve_elicitation}` | `pycodex.tui.app_event_sender`; `tests/test_tui_app_event_sender.py` | `complete` | Module-scoped behavior contract is covered: sender construction, non-`CodexOp` inbound logging, swallowed send failures with error logging, CodexOp helper wrapping, SubmitThreadOp helper wrapping, and semantic channel-like send targets. `app_event.rs` and `app_command.rs` remain separate module contracts. |
| `app_event.rs` | `RealtimeAudioDeviceKind::{title,noun}` | `tests/test_tui_app_event.py::test_realtime_audio_device_labels_match_rust_helpers` | complete | Ports microphone/speaker title and noun helpers exactly. |
| `app_event.rs` | struct-like local enums preserve variant payloads | `tests/test_tui_app_event.py::test_struct_like_modes_preserve_variant_payloads` | complete_slice | Ports `ThreadGoalSetMode`, `RateLimitRefreshOrigin`, and `KeymapEditIntent` as semantic variant DTOs. |
| `app_event.rs` | `AppEvent` variant names and important payload fields | `tests/test_tui_app_event.py::test_app_event_constructors_match_variant_payloads` | complete_slice | Ports the internal app event-bus contract with semantic `kind`/payload events rather than Rust enum layout. |
| `app_event.rs` | local structs field preservation | `tests/test_tui_app_event.py::test_data_structs_preserve_rust_fields` | complete_slice | Ports `HistoryLookupResponse`, `ConnectorsSnapshot`, `PermissionProfileSelection`, and `RealtimeWebrtcOffer` field shape. |
| `app_event.rs` | simple enum variant names | `tests/test_tui_app_event.py::test_simple_enum_values_match_rust_variant_names` | complete | Ports `ConsolidationScrollbackReflow`, `WindowsSandboxEnableMode`, `ExitMode`, and `FeedbackCategory` variant names. |
| `clipboard_copy.rs` | OSC52 sequence encoding, tmux wrapping, payload limit | `tests/test_tui_clipboard_copy.py::test_osc52_sequence_matches_rust_encoding_tests` | complete | Ports Rust OSC52 byte limit, base64 payload, BEL terminator, and tmux passthrough sequence. |
| `clipboard_copy.rs` | `write_osc52_to_writer` | `tests/test_tui_clipboard_copy.py::{test_write_osc52_to_writer_emits_sequence_verbatim,test_write_osc52_to_writer_distinguishes_write_and_flush_errors}` | complete | Ports verbatim sequence write/flush boundary with semantic writer, including distinct Rust error strings for write and flush failures. |
| `clipboard_copy.rs` | SSH environment skips native and uses terminal clipboard | `tests/test_tui_clipboard_copy.py::{test_ssh_uses_terminal_clipboard_and_skips_native,test_ssh_error_messages_match_rust,test_ssh_inside_tmux_prefers_tmux_then_osc52_fallback}` | complete | Ports remote copy order, tmux preference, OSC52 fallback, and Rust error strings. |
| `clipboard_copy.rs` | `tmux_clipboard_copy_ready` | `tests/test_tui_clipboard_copy.py::test_tmux_clipboard_copy_ready_matches_rust_boundaries` | complete | Ports forwarding disabled and missing `Ms` capability rejection. |
| `clipboard_copy.rs` | local/native/WSL/terminal fallback order | `tests/test_tui_clipboard_copy.py::{test_local_uses_native_first_and_preserves_lease,test_local_fallback_order_and_errors_match_rust,test_local_wsl_uses_powershell_then_terminal_fallback}` | complete_slice | Ports injected-backend decision tree and error composition. Real native clipboard uses explicit unavailable backend unless a dependency-backed implementation is added later. |
| `clipboard_paste.rs` | `PasteImageError` display and `EncodedImageFormat::label` | `tests/test_tui_clipboard_paste.py::test_error_display_and_format_labels_match_rust` | complete | Ports user-facing error prefixes and PNG/JPEG/IMG labels. |
| `clipboard_paste.rs` | `PastedImageInfo` field shape | `tests/test_tui_clipboard_paste.py::test_pasted_image_info_preserves_fields` | complete | Ports width/height/encoded_format DTO shape. |
| `clipboard_paste.rs` | pasted path normalization tests | `tests/test_tui_clipboard_paste.py::{test_normalize_file_url_and_shell_escaped_paths,test_normalize_multiple_tokens_returns_none,test_normalize_windows_paths_without_posix_backslash_loss}` | complete | Ports file URL, shell escaped, quoted, Windows, and UNC path normalization semantics. |
| `clipboard_paste.rs` | WSL Windows-path conversion helper | `tests/test_tui_clipboard_paste.py::test_convert_windows_path_to_wsl_contract` | complete_slice | Ports source-defined drive-letter to `/mnt/<drive>` conversion and UNC rejection as a deterministic helper. |
| `clipboard_paste.rs` | `pasted_image_format` | `tests/test_tui_clipboard_paste.py::test_pasted_image_format_png_jpeg_unknown` | complete | Ports extension-based PNG/JPEG/Other inference for Unix and Windows-style paths. |
| `clipboard_paste.rs` | native image clipboard capture | N/A | blocked | Rust depends on `arboard` and `image` for real clipboard image capture/encoding; Python stdlib backend reports explicit clipboard unavailable instead of fabricating image data. |
| `slash_command.rs` | `stop_command_is_canonical_name` / `clean_alias_parses_to_stop_command` | `tests/test_tui_slash_command.py::test_stop_command_is_canonical_name_and_clean_alias_parses` | complete | Ports canonical `stop` command string and `clean` alias parsing. |
| `slash_command.rs` | `pet_alias_parses_to_pets_command` | `tests/test_tui_slash_command.py::test_pet_alias_parses_to_pets_command` | complete | Ports canonical `pets` command and `pet` alias. |
| `slash_command.rs` | `certain_commands_are_available_during_task` | `tests/test_tui_slash_command.py::test_certain_commands_are_available_during_task` | complete | Ports Rust availability and inline-args assertions for Goal/Ide/Title/Statusline/Raw. |
| `slash_command.rs` | `auto_review_command_is_approve` | `tests/test_tui_slash_command.py::test_auto_review_command_is_approve` | complete | Ports AutoReview canonical command and parse alias. |
| `slash_command.rs` | descriptions, parse, presentation order, visibility | `tests/test_tui_slash_command.py::{test_command_descriptions_and_negative_availability_match_source,test_parse_accepts_leading_slash_and_rejects_unknown,test_built_in_slash_commands_preserve_presentation_order}` | complete | Ports source-defined command table semantics and runtime visibility predicates with Python platform/debug equivalents. |
| `external_editor.rs` | `resolve_editor_prefers_visual` | `tests/test_tui_external_editor.py::test_resolve_editor_prefers_visual` | complete | Ports VISUAL-over-EDITOR priority. |
| `external_editor.rs` | `resolve_editor_errors_when_unset` | `tests/test_tui_external_editor.py::test_resolve_editor_errors_when_unset` | complete | Ports missing editor error string. |
| `external_editor.rs` | command splitting and empty command boundary | `tests/test_tui_external_editor.py::test_resolve_editor_command_splits_and_rejects_empty` | complete_slice | Ports shlex-style command splitting and empty command rejection. |
| `external_editor.rs` | `run_editor_returns_updated_content` | `tests/test_tui_external_editor.py::test_run_editor_returns_updated_content` | complete | Ports temp `.md` seed file, editor invocation with path argument, and read-back content flow. |
| `external_editor.rs` | empty/nonzero editor errors and env guard helpers | `tests/test_tui_external_editor.py::{test_run_editor_rejects_empty_and_nonzero_exit,test_env_guard_and_restore_env_roundtrip}` | complete_slice | Ports source-defined error boundaries plus Rust test-support env restore semantics. |
| `workspace_command.rs` | `WorkspaceCommand::new` defaults | `tests/test_tui_workspace_command.py::test_workspace_command_new_uses_rust_defaults` | complete_slice | Rust has no local unit test; Python anchors argv, cwd/env, 5s timeout, 64KiB cap, and cap-enabled defaults from source. |
| `workspace_command.rs` | builder methods `cwd`, `env`, `timeout`, `disable_output_cap` | `tests/test_tui_workspace_command.py::test_workspace_command_builders_are_immutable_and_chainable` | complete_slice | Ports Rust consuming-builder semantics as immutable Python dataclass replacements. |
| `workspace_command.rs` | `WorkspaceCommandOutput::success` and `WorkspaceCommandError` display | `tests/test_tui_workspace_command.py::test_workspace_command_output_success_and_error_display` | complete_slice | Ports zero-exit success predicate and error string display. |
| `workspace_command.rs` | app-server one-off command request conversion | `tests/test_tui_workspace_command.py::test_app_server_runner_builds_one_off_command_request` | complete_slice | Ports non-tty, no stream, timeout ms, cwd/env, output cap, sandbox/profile None request shape using a semantic dict. |
| `workspace_command.rs` | disabled output cap and transport error wrapping | `tests/test_tui_workspace_command.py::test_app_server_runner_disables_output_cap_and_wraps_errors` | complete_slice | Ports output cap None when disabled and request-handle errors into `WorkspaceCommandError`. |
| `session_log.rs` | `maybe_init` env gate and header record | `tests/test_tui_session_log.py::test_maybe_init_respects_env_and_writes_header` | complete_slice | Rust has no local tests; Python anchors `CODEX_TUI_RECORD_SESSION`, explicit path, and session_start metadata fields from source. |
| `session_log.rs` | `SessionLogger::open` / `write_json_line` | `tests/test_tui_session_log.py::test_logger_open_truncates_and_writes_json_lines` | complete_slice | Ports parent creation/truncate/write/flush JSONL semantics; Unix 0600 mode is attempted best-effort. |
| `session_log.rs` | special inbound AppEvent records | `tests/test_tui_session_log.py::test_inbound_app_event_records_special_variants` | complete_slice | Ports NewSession, ClearUi, InsertHistoryCell, StartFileSearch, and FileSearchResult summary records. |
| `session_log.rs` | generic and pet inbound AppEvent records | `tests/test_tui_session_log.py::test_inbound_app_event_records_generic_variant_and_pet_results` | complete_slice | Ports generic variant logging plus PetPreviewLoaded/PetSelectionLoaded request/ok fields. |
| `session_log.rs` | outbound op, session end, generic record | `tests/test_tui_session_log.py::test_outbound_op_session_end_and_write_record` | complete_slice | Ports `from_tui` op payload records, session_end meta record, and generic write_record shape. |
| `file_search.rs` | `FileSearchManager::on_user_query` starts session and ignores duplicate query | `tests/test_tui_file_search.py::test_manager_starts_session_and_updates_query_once` | complete_slice | Rust has no local unit tests; Python anchors source-defined session creation, `compute_indices: true`, cancel flag None, and duplicate-query no-op. |
| `file_search.rs` | empty query drops session and next query restarts | `tests/test_tui_file_search.py::test_empty_query_drops_session_and_next_query_restarts` | complete_slice | Ports empty-query session drop and subsequent session recreation behavior. |
| `file_search.rs` | `update_search_dir` | `tests/test_tui_file_search.py::test_update_search_dir_drops_session_and_clears_query` | complete_slice | Ports directory update, current session drop, and latest query clear. |
| `file_search.rs` | failed session start | `tests/test_tui_file_search.py::test_failed_session_start_is_swallowed_and_query_is_kept` | complete_slice | Ports Rust warning-and-none behavior without raising to caller. |
| `file_search.rs` | `TuiSessionReporter::send_snapshot` filters and sends results | `tests/test_tui_file_search.py::{test_reporter_sends_only_current_non_empty_snapshots,test_stale_reporter_token_is_ignored_and_free_functions_delegate}` | complete_slice | Ports token guard, empty latest/snapshot query guards, match clone, `FileSearchResult` event emission, and no-op completion callback. |
| `model_migration.rs` | `migration_copy_for_models` markdown branch and placeholder fill | `tests/test_tui_model_migration.py::test_migration_copy_prefers_markdown_and_fills_placeholders` | complete | Ports markdown override and `{model_from}`/`{model_to}` replacement. |
| `model_migration.rs` | `migration_copy_for_models` default/custom copy branches | `tests/test_tui_model_migration.py::{test_migration_copy_default_content_and_no_opt_out_continue,test_migration_copy_custom_copy_and_opt_out_line}` | complete | Ports heading, recommendation copy, target description/link handling, opt-out line, and continue hint text as semantic lines. |
| `model_migration.rs` | `escape_key_accepts_prompt` | `tests/test_tui_model_migration.py::test_escape_key_accepts_prompt` | complete | Ports Esc confirming the highlighted option rather than exiting. |
| `model_migration.rs` | `selecting_use_existing_model_rejects_upgrade` | `tests/test_tui_model_migration.py::test_selecting_use_existing_model_rejects_upgrade` | complete | Ports Down then Enter selecting Use Existing Model and rejecting migration. |
| `model_migration.rs` | menu key state machine and Ctrl-C/Ctrl-D exit | `tests/test_tui_model_migration.py::test_menu_keys_and_ctrl_exit_combo` | complete | Ports k/j/up/down, numeric selection, frame scheduling, and control exit combo behavior. |
| `model_migration.rs` | non-opt-out key behavior and release filtering | `tests/test_tui_model_migration.py::test_non_opt_out_accepts_enter_or_escape_only_and_ignores_release` | complete | Ports key release ignore and Enter/Esc accept behavior when opt-out is unavailable. |
| `model_migration.rs` | markdown prompt long URL tail visibility | `tests/test_tui_model_migration.py::test_semantic_render_keeps_long_url_tail_visible_when_narrow` | complete | Uses semantic line wrapping rather than ratatui snapshot rendering while preserving Rust test's user-visible tail condition. |
| `startup_hooks_review.rs` | `bypass_hook_trust_suppresses_startup_review` | `tests/test_tui_startup_hooks_review.py::test_bypass_hook_trust_suppresses_startup_review` | complete | Ports bypass flag suppressing startup review. |
| `startup_hooks_review.rs` | `untrusted_hooks_need_review_without_bypass` / review count | `tests/test_tui_startup_hooks_review.py::test_untrusted_hooks_need_review_without_bypass` | complete_slice | Ports review-needed predicate for Untrusted/Modified hook trust states and count helper. |
| `startup_hooks_review.rs` | `selected_choice` index mapping | `tests/test_tui_startup_hooks_review.py::test_selected_choice_maps_completed_indices` | complete_slice | Ports incomplete view None, indices 0/1/2, no selection default, and out-of-range None. |
| `startup_hooks_review.rs` | `selection_view_params` prompt content | `tests/test_tui_startup_hooks_review.py::{test_selection_view_params_prompt_content,test_selection_view_params_singular_trusting_and_error_states}` | complete_slice | Ports header count text, warning line, trust error/trusting text, disabled item state, and three menu items. |
| `startup_hooks_review.rs` | `selection_item` defaults | `tests/test_tui_startup_hooks_review.py::test_selection_item_defaults_match_rust` | complete_slice | Ports name, dismiss_on_select true, and disabled flag. |
| `startup_hooks_review.rs` | prompt render snapshots | `tests/test_tui_startup_hooks_review.py::{test_render_lines_semantic_prompt_contains_snapshot_text,test_render_lines_semantic_prompt_with_trust_error}` | complete_slice | Uses semantic rendered lines rather than ratatui buffer snapshot while preserving user-visible prompt text and error content. |
| `keymap.rs` | function key parsing and out-of-range rejection | `tests/test_tui_keymap.py::test_parses_function_keys_and_rejects_out_of_range_function_keys` | complete_slice | Ports F1-F12 parsing and F13 rejection with Python semantic `KeyBinding`. |
| `keymap.rs` | named non-character key parsing | `tests/test_tui_keymap.py::test_parses_all_named_non_character_keys` | complete_slice | Ports tab/backspace/esc/delete/arrows/home/end/page/space/minus names. |
| `keymap.rs` | invalid modifier/function specs and minus aliases | `tests/test_tui_keymap.py::{test_rejects_modifier_only_and_nonnumeric_function_key_specs,test_parses_minus_alias_and_legacy_literal_minus}` | complete_slice | Ports modifier-only rejection, nonnumeric function rejection, `alt-minus`, `alt--`, and literal `-`. |
| `keymap.rs` | string/array binding specs, dedup, parse path errors | `tests/test_tui_keymap.py::test_parse_bindings_supports_string_array_and_deduplicates` | complete_slice | Ports string/array input, first-seen deduplication, and config-path-aware parse errors. |
| `keymap.rs` | primary binding helper | `tests/test_tui_keymap.py::test_primary_binding_returns_first_or_none` | complete | Ports first binding or None behavior. |
| `keymap.rs` | selected built-in defaults | `tests/test_tui_keymap.py::{test_selected_defaults_match_rust_tests,test_vim_normal_defaults_include_insert_and_arrow_aliases}` | complete_slice | Ports Rust-tested defaults for copy, raw output, editor newline/deletion aliases, composer shortcuts, approval fullscreen, and Vim movement aliases. |
| `keymap.rs` | config remap/unbind and basic conflict validation | `tests/test_tui_keymap.py::{test_from_config_remaps_unbinds_and_validates_conflicts,test_defaults_pass_conflict_validation}` | complete_slice | Ports source-defined config override shape and per-scope duplicate rejection for the implemented keymap subset. |
| `bottom_pane/popup_consts.rs` | `MAX_POPUP_ROWS` | `tests/test_tui_bottom_pane_popup_consts.py::test_max_popup_rows_matches_rust_constant` | complete | Ports shared popup row cap constant. |
| `bottom_pane/popup_consts.rs` | `standard_popup_hint_line` | `tests/test_tui_bottom_pane_popup_consts.py::test_standard_popup_hint_line_uses_enter_and_escape` | complete_slice | Uses semantic string lines instead of ratatui `Line`, preserving visible hint text. |
| `bottom_pane/popup_consts.rs` | `standard_popup_hint_line_for_keymap` | `tests/test_tui_bottom_pane_popup_consts.py::test_standard_popup_hint_line_for_keymap_uses_primary_bindings` | complete_slice | Ports primary accept/cancel binding selection from `ListKeymap`. |
| `bottom_pane/popup_consts.rs` | `accept_cancel_hint_line` option matrix | `tests/test_tui_bottom_pane_popup_consts.py::test_accept_cancel_hint_line_handles_missing_bindings` | complete_slice | Ports both/single/none binding branches as user-visible text. |
| `bottom_pane/popup_consts.rs` | `accept_cancel_hint_line` uses `key_hint::KeyBinding::display_label` for binding spans | `tests/test_tui_bottom_pane_popup_consts.py::test_accept_cancel_hint_line_uses_rust_key_hint_display_labels` | complete | Ports Rust key-hint label semantics for lowercase special keys, modifier order/prefixes, and PageUp/PageDown labels using Python semantic strings instead of ratatui `Line`/`Span`. |
| `bottom_pane/slash_commands.rs` | exact builtin dispatch lookup and aliases | `tests/test_tui_bottom_pane_slash_commands.py::test_builtin_dispatch_lookup_resolves_visible_and_alias_commands` | complete | Ports debug-config, clear, stop, and clean alias exact lookup after feature gating. |
| `bottom_pane/slash_commands.rs` | service tier feature gating and insertion after `/model` | `tests/test_tui_bottom_pane_slash_commands.py::{test_service_tier_commands_are_hidden_when_disabled,test_all_service_tiers_are_exposed_as_commands_after_model}` | complete | Ports disabled service-tier hiding and model-adjacent insertion order. |
| `bottom_pane/slash_commands.rs` | feature-gated builtins | `tests/test_tui_bottom_pane_slash_commands.py::test_feature_gated_builtin_commands_are_hidden` | complete | Ports goal, realtime, and settings/audio-device visibility gates. |
| `bottom_pane/slash_commands.rs` | side-conversation popup filtering vs dispatch lookup | `tests/test_tui_bottom_pane_slash_commands.py::{test_side_conversation_hides_commands_without_side_flag,test_side_conversation_exact_lookup_still_resolves_hidden_commands_for_dispatch_error,test_side_conversation_exact_lookup_still_resolves_service_tier_commands_for_dispatch_error}` | complete | Ports the Rust distinction between hidden popup commands and exact dispatch lookup. |
| `bottom_pane/slash_commands.rs` | `SlashCommandItem` methods and fuzzy prefix matching | `tests/test_tui_bottom_pane_slash_commands.py::{test_slash_command_item_delegates_builtin_methods_and_service_tiers_are_not_inline_or_side_safe,test_has_slash_command_prefix_uses_visible_command_items}` | complete_slice | Uses a Python subsequence matcher for the Rust fuzzy-match dependency boundary. |
| `bottom_pane/action_required_title.rs` | `ACTION_REQUIRED_PREVIEW_PREFIX` | `tests/test_tui_bottom_pane_action_required_title.py::test_action_required_preview_prefix_matches_rust_constant` | complete | Ports Rust action-required title prefix constant. |
| `bottom_pane/action_required_title.rs` | `build_action_required_title_text` filtering and joining | `tests/test_tui_bottom_pane_action_required_title.py::{test_build_action_required_title_text_filters_spinner_and_excluded_items,test_build_action_required_title_text_omits_none_values_but_keeps_prefix}` | complete | Ports prefix-first join, spinner exclusion, explicit excluded item filtering, and `None` value omission. |
| `bottom_pane/prompt_args.rs` | `parse_slash_name` command/rest parsing | `tests/test_tui_bottom_pane_prompt_args.py::{test_parse_slash_name_rejects_non_slash_and_empty_name,test_parse_slash_name_splits_name_and_left_trims_rest}` | complete | Ports first-line slash parsing, empty-name rejection, and left-trimmed rest behavior. |
| `bottom_pane/prompt_args.rs` | `parse_slash_name` UTF-8 byte offset semantics | `tests/test_tui_bottom_pane_prompt_args.py::{test_parse_slash_name_uses_utf8_byte_offset,test_parse_slash_name_treats_unicode_whitespace_as_separator}` | complete | Preserves Rust byte-index offset rather than Python character-index semantics. |
| `bottom_pane/scroll_state.rs` | `wrap_navigation_and_visibility` | `tests/test_tui_bottom_pane_scroll_state.py::test_wrap_navigation_and_visibility` | complete | Ports wrap-around up/down navigation and visibility adjustment. |
| `bottom_pane/scroll_state.rs` | `page_and_jump_navigation_clamps` | `tests/test_tui_bottom_pane_scroll_state.py::test_page_and_jump_navigation_clamps` | complete | Ports non-wrapping page movement, top/bottom jumps, and scroll window updates. |
| `bottom_pane/scroll_state.rs` | empty, zero-visible, clamp, and reset boundaries | `tests/test_tui_bottom_pane_scroll_state.py::{test_empty_and_zero_visible_rows_reset_scroll_boundaries,test_clamp_selection_and_reset_match_source_contract}` | complete_slice | Adds source-contract coverage for empty list clearing, zero visible rows, clamp without scroll adjustment, and reset. |
| `bottom_pane/scroll_state.rs` | None-selection initialization across wrap/page navigation | `tests/test_tui_bottom_pane_scroll_state.py::test_none_selection_initializes_like_rust_for_navigation_methods` | complete | Covers the remaining source branches where non-empty navigation starts from row 0 before wrapping/clamping. Module contract is complete. |
| `bottom_pane/paste_burst.rs` | Rust paste-burst unit tests | `tests/test_tui_bottom_pane_paste_burst.py::{test_ascii_first_char_is_held_then_flushes_as_typed,test_ascii_two_fast_chars_start_buffer_from_pending_and_flush_as_paste,test_flush_before_modified_input_includes_pending_first_char,test_decide_begin_buffer_only_triggers_for_pastey_prefixes,test_newline_suppression_window_outlives_buffer_flush}` | complete | Ports ASCII hold/flush, fast burst buffering, modified-input flush, pastey retro-grab heuristic, and Enter suppression window. |
| `bottom_pane/paste_burst.rs` | `retro_start_index` and state boundary helpers | `tests/test_tui_bottom_pane_paste_burst.py::{test_retro_start_index_uses_utf8_byte_indices,test_active_append_newline_try_append_and_clear_boundaries}` | complete_slice | Adds source-contract coverage for UTF-8 byte offsets, active newline append, try-append, non-char window clearing, and explicit paste clearing. |
| `bottom_pane/paste_burst.rs` | `on_plain_char_no_hold` IME/non-ASCII branch | `tests/test_tui_bottom_pane_paste_burst.py::test_no_hold_path_never_retains_first_char_and_can_begin_buffer` | complete | Ports the no-hold path: it never sets `pending_first_char`, returns `None` before the burst threshold, begins buffering at the third fast char, and returns `BufferAppend` once active. |
| `bottom_pane/selection_tabs.rs` | tab unit active/inactive style and gap constant | `tests/test_tui_bottom_pane_selection_tabs.py::test_tab_gap_width_and_active_unit_semantics` | complete_slice | Uses semantic `StyledSpan` values instead of ratatui spans while preserving accent/dim intent. |
| `bottom_pane/selection_tabs.rs` | tab bar line wrapping and height | `tests/test_tui_bottom_pane_selection_tabs.py::{test_tab_bar_lines_wrap_when_next_unit_would_exceed_width,test_tab_bar_width_is_clamped_to_at_least_one_and_empty_tabs_have_zero_height}` | complete_slice | Ports max-width clamp, two-space gaps, active bracket width, and empty-tab height behavior. |
| `bottom_pane/selection_tabs.rs` | `render_tab_bar` visible-line clipping | `tests/test_tui_bottom_pane_selection_tabs.py::{test_render_tab_bar_appends_only_lines_that_fit_area_height,test_render_tab_bar_accepts_mapping_area}` | complete_slice | Represents ratatui buffer mutation as append-only semantic rendered lines clipped to area height. |
| `bottom_pane/selection_tabs.rs` | out-of-range `active_idx` leaves all tabs inactive | `tests/test_tui_bottom_pane_selection_tabs.py::test_active_index_out_of_range_leaves_all_tabs_inactive` | complete | Ports Rust's direct `idx == active_idx` behavior without clamping the active index. Module contract is complete with semantic `StyledLine`/`StyledSpan` replacing ratatui `Line`/`Span` and buffer rendering. |
| `bottom_pane/selection_popup_common.rs` | `one_cell_width_falls_back_without_panic_for_wrapped_two_column_rows` | `tests/test_tui_bottom_pane_selection_popup_common.py::test_one_cell_width_falls_back_without_panic_for_wrapped_two_column_rows` | complete | Ports one-cell two-column fallback behavior. |
| `bottom_pane/selection_popup_common.rs` | `selected_rows_use_the_shared_accent_style` | `tests/test_tui_bottom_pane_selection_popup_common.py::test_selected_rows_use_the_shared_accent_style_semantics` | complete_slice | Uses semantic accent style instead of ratatui modifier/color cells. |
| `bottom_pane/selection_popup_common.rs` | row layout helpers and menu surface semantics | `tests/test_tui_bottom_pane_selection_popup_common.py::{test_menu_surface_inset_and_padding_match_rust_constants,test_build_full_line_combines_prefix_match_description_disabled_and_category,test_compute_desc_col_modes_and_wrap_indent_contracts,test_should_wrap_name_in_column_and_render_single_line_empty_placeholder}` | complete_slice | Ports semantic rect inset, column-width modes, wrap indent, full-line composition, placeholder rendering, and two-column eligibility without copying ratatui internals. |
| `bottom_pane/selection_popup_common.rs` | empty menu surface render and empty-row measurement placeholder | `tests/test_tui_bottom_pane_selection_popup_common.py::test_menu_surface_render_empty_area_is_noop_and_measure_empty_rows_placeholder` | complete_slice | Ports `render_menu_surface` empty-area no-op and `measure_rows_height` empty-row placeholder height. Exact ratatui buffer/cell styling remains a renderer boundary. |
| `bottom_pane/pending_input_preview.rs` | desired height and queued message rendering | `tests/test_tui_bottom_pane_pending_input_preview.py::{test_desired_height_empty_and_width_too_narrow,test_desired_height_one_message,test_render_one_message_with_remapped_edit_binding_and_height_clip}` | complete_slice | Ports empty/narrow no-op, one queued message height, edit binding hint, and area-height clipping as semantic lines. |
| `bottom_pane/pending_input_preview.rs` | preview truncation and URL-like no-ellipsis behavior | `tests/test_tui_bottom_pane_pending_input_preview.py::{test_render_more_than_three_wrapped_message_lines_adds_overflow_marker,test_long_url_like_message_does_not_expand_into_wrapped_ellipsis_rows}` | complete_slice | Ports three-line preview cap with overflow marker and URL-like token preservation. |
| `bottom_pane/pending_input_preview.rs` | pending/rejected/queued section ordering and interrupt binding | `tests/test_tui_bottom_pane_pending_input_preview.py::{test_pending_steers_render_above_rejected_and_queued_messages,test_pending_interrupt_binding_can_be_hidden_or_remapped}` | complete_slice | Ports section order, steer header text, remapped interrupt binding text, and hidden interrupt hint branch. |
| `bottom_pane/pending_input_preview.rs` | stable semantic preview rendering | `tests/test_tui_bottom_pane_pending_input_preview.py::{test_desired_height_empty_and_width_too_narrow,test_desired_height_one_message,test_render_one_message_with_remapped_edit_binding_and_height_clip,test_render_more_than_three_wrapped_message_lines_adds_overflow_marker,test_long_url_like_message_does_not_expand_into_wrapped_ellipsis_rows,test_pending_steers_render_above_rejected_and_queued_messages,test_pending_interrupt_binding_can_be_hidden_or_remapped,test_edit_hint_only_appears_for_queued_messages}` | complete_slice | Replaces encoding-damaged glyph literals with stable ASCII semantic markers while preserving Rust preview structure, width guards, height clipping, binding text, section ordering, queued-message-only edit hint, three-line cap, and URL-like no-overflow behavior. Exact ratatui cell styling and original glyph rendering remain renderer/encoding boundaries. |
| `bottom_pane/pending_input_preview.rs` | optional edit binding and empty-area render guards | `tests/test_tui_bottom_pane_pending_input_preview.py::{test_edit_binding_none_hides_queued_message_hint,test_render_empty_area_is_noop}` | complete_slice | Ports the remaining local branches: queued messages do not render the edit hint when `edit_binding` is absent, and empty render areas produce no buffer output. Exact ratatui cell styling/glyph rendering remains a renderer boundary. |
| `bottom_pane/pending_thread_approvals.rs` | `desired_height_empty` and state updates | `tests/test_tui_bottom_pane_pending_thread_approvals.py::{test_set_threads_reports_changes_and_is_empty_tracks_state,test_desired_height_empty_and_width_too_narrow}` | complete | Ports `set_threads` change detection, empty predicate, test-only `threads`, empty height, and narrow-width no-op. |
| `bottom_pane/pending_thread_approvals.rs` | snapshot-visible approval rows | `tests/test_tui_bottom_pane_pending_thread_approvals.py::{test_render_single_thread_snapshot_visible_text,test_render_multiple_threads_limits_to_three_and_adds_switch_hint,test_render_clips_to_area_height}` | complete_slice | Ports visible warning rows, three-thread cap, overflow marker, `/agent` hint, snapshot row padding, and area-height clipping using semantic rows. |
| `bottom_pane/pending_thread_approvals.rs` | module-scoped semantic contract | `tests/test_tui_bottom_pane_pending_thread_approvals.py::{test_set_threads_reports_changes_and_is_empty_tracks_state,test_set_threads_takes_an_owned_snapshot_of_thread_names,test_desired_height_empty_and_width_too_narrow,test_render_single_thread_snapshot_visible_text,test_render_multiple_threads_limits_to_three_and_adds_switch_hint,test_render_clips_to_area_height}` | complete | Covers the full module-owned behavior contract: owned thread-list updates, unchanged detection, empty predicate, test-visible thread snapshot, empty/narrow render no-op, three-thread cap, overflow marker, wrapped warning rows, `/agent` switch hint, desired height, and render height clipping. Python uses semantic rows for ratatui `Line`/`Paragraph` rendering; exact terminal cell styling is an intentional framework adaptation. |
| `bottom_pane/chat_composer/draft_state.rs` | `DraftState::new` default fields | `tests/test_tui_bottom_pane_chat_composer_draft_state.py::test_draft_state_new_matches_rust_defaults` | complete_slice | Ports composer draft container defaults while keeping `textarea` behavior as a separate dependency boundary. |
| `bottom_pane/chat_composer/draft_state.rs` | independent owned containers and `ComposerMentionBinding` fields | `tests/test_tui_bottom_pane_chat_composer_draft_state.py::{test_draft_state_default_factories_are_not_shared,test_composer_mention_binding_preserves_fields_and_clone_like_equality}` | complete_slice | Ports Rust owned Vec/HashMap semantics with Python default factories and field-preserving mention binding DTO. |
| `bottom_pane/mod.rs` | module-level DTOs, cancellation enum, and timing/feature constants | `tests/test_tui_bottom_pane_mod.py::{test_bottom_pane_module_constants_match_rust_defaults,test_local_image_attachment_preserves_placeholder_and_path,test_mention_binding_preserves_mention_and_path,test_cancellation_event_variants_match_rust_enum}` | complete_slice | Ports `LocalImageAttachment`, `MentionBinding`, `CancellationEvent::{Handled,NotHandled}`, `QUIT_SHORTCUT_TIMEOUT`, `APPROVAL_PROMPT_TYPING_IDLE_DELAY`, and `DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED`; full `BottomPane` routing/render/composer stack remains explicit interface scaffold. |
| `render/highlight.rs` | theme-name parsing/listing, custom theme path/warnings, `.tmTheme` plist scope parsing, ANSI alpha color conversion, syntax aliases, highlight guardrails, Pygments-backed known-language highlighting, content-preserving fallback lines | `tests/test_tui_render_highlight.py::{test_theme_constants_and_builtin_names_match_rust_contract,test_parse_and_resolve_builtin_theme_names,test_custom_theme_path_validation_and_listing,test_custom_tmtheme_parser_extracts_scope_styles_and_diff_backgrounds,test_ansi_color_conversion_matches_rust_alpha_semantics,test_find_syntax_aliases_and_unknown_language_fallback,test_pygments_highlighting_styles_rust_keywords,test_highlight_limits_and_content_preserving_fallback}` | complete_slice | Ports the portable Python behavior boundary of Rust `render::highlight`: bundled theme IDs, custom `.tmTheme` discovery and plist parsing, scope foreground/background/fontStyle extraction, user-facing warning text, alpha-channel ANSI/default/RGB conversion, syntax alias resolution, 512KiB/10000-line fallbacks, exact text reconstruction, and real vendored-Pygments token highlighting for known languages. Exact syntect/two_face grammar/theme fidelity remains a dependency boundary. |
| `bottom_pane/chat_composer/attachment_state.rs` | local/remote image numbering, relabeling, and submission take/prune | `tests/test_tui_bottom_pane_chat_composer_attachment_state.py::{test_remote_urls_offset_local_image_numbering_and_take_relabels,test_attach_image_inserts_placeholder_and_local_image_views_are_copies,test_prune_and_take_recent_submission_images,test_remove_deleted_local_placeholders_relabels_remaining_images}` | complete_slice | Ports placeholder numbering offset by remote images, textarea payload replacement, attach insertion, prune by text elements, and take semantics. |
| `bottom_pane/chat_composer/attachment_state.rs` | remote image line selection and keyboard deletion/navigation | `tests/test_tui_bottom_pane_chat_composer_attachment_state.py::{test_remote_image_lines_selection_and_keyboard_navigation,test_remote_image_delete_relabels_local_images_and_rejects_modified_events}` | complete_slice | Ports selected remote line styling, Up/Down selection behavior, Delete removal, event kind/modifier guards, and local relabeling after remote removal. |
| `bottom_pane/chat_composer/footer_state.rs` | footer flash visibility and test helper | `tests/test_tui_bottom_pane_chat_composer_footer_state.py::{test_flash_visible_matches_rust_expiry_predicate,test_show_flash_accepts_plain_text_and_stores_line}` | complete_slice | Ports flash expiry predicate (`now < expires_at`) and show-flash state update with Python monotonic-compatible timestamps. |
| `bottom_pane/chat_composer/footer_state.rs` | status line text and state container fields | `tests/test_tui_bottom_pane_chat_composer_footer_state.py::{test_status_line_text_concatenates_span_content,test_status_line_text_handles_none_string_and_duck_typed_lines,test_footer_state_preserves_field_defaults_and_mutability}` | complete_slice | Ports span-content concatenation and field-preserving footer state DTO semantics; full footer rendering remains separate. |
| `bottom_pane/chat_composer/popup_state.rs` | `PopupState::default` and `active` predicate | `tests/test_tui_bottom_pane_chat_composer_popup_state.py::{test_popup_state_default_matches_rust_default,test_popup_state_active_reports_non_none_variants}` | complete | Ports default `ActivePopup::None`, inactive predicate, and non-None popup variants being active. |
| `bottom_pane/chat_composer/popup_state.rs` | `ActivePopup` variants and dismissal/query fields | `tests/test_tui_bottom_pane_chat_composer_popup_state.py::{test_active_popup_preserves_variant_names_and_payloads,test_popup_state_preserves_dismissal_and_query_tokens}` | complete_slice | Uses duck-typed popup payloads while preserving Rust variant names and lifecycle token fields. |
| `bottom_pane/chat_composer/history_search.rs` | `HistorySearchSession`, `HistorySearchStatus`, case-insensitive byte match ranges, footer line status rendering, highlight gating, result-status mapping | `tests/test_tui_bottom_pane_chat_composer_history_search.py::{test_history_search_session_defaults_and_active_predicate,test_case_insensitive_match_ranges_match_rust_examples,test_history_search_footer_line_status_variants,test_history_search_highlight_ranges_only_for_match_with_query,test_status_for_history_result_and_session_update}` | complete_slice | Ports the module-local, independently measurable history-search behavior. Full `ChatComposer` search lifecycle/key handling remains owned by composer/textarea/history module boundaries and existing Rust test-name scaffolds stay explicit `not_ported` markers. |
| `bottom_pane/chat_composer/slash_input.rs` | `SlashInput` local parsing/validation helpers, queued action selection, command under cursor, completion text, prepared args, argument text-element range translation | `tests/test_tui_bottom_pane_chat_composer_slash_input.py::{test_validate_submission_and_command_modes,test_bare_and_inline_command_detection,test_dequeue_action_matches_rust_ordering,test_command_element_range_and_command_under_cursor_use_byte_offsets,test_editing_command_name_and_popup_filter_text,test_completion_dispatch_and_prepared_args,test_args_elements_translate_full_text_ranges_to_argument_ranges}` | complete_slice | Ports independently measurable slash-input behavior. Full `ChatComposer` popup key handling and draft-tail mutation tests remain explicit not-ported composer lifecycle boundaries. |
| `bottom_pane/chat_composer_history.rs` | local submission dedupe, async persistent navigation, boundary-gated navigation, local/persistent incremental search, duplicate-match skipping, case-insensitive/empty-query search | `tests/test_tui_bottom_pane_chat_composer_history.py::{test_duplicate_submissions_are_not_recorded,test_navigation_with_async_fetch_and_response,test_local_search_matches_boundaries_and_newer_direction,test_search_skips_duplicate_local_matches_but_can_revisit_cached_unique_matches,test_persistent_search_fetches_until_match_and_repeated_boundary_does_not_refetch,test_search_case_insensitive_empty_query_and_navigation_reset,test_should_handle_navigation_when_cursor_is_at_line_boundaries}` | complete_slice | Ports the core history state machine using semantic lookup event dictionaries. Mention decoding and real `AppEventSender` transport remain dependency boundaries. |
| `bottom_pane/chat_composer_history.rs` | `HistoryEntry::new` persisted mention decoding | `tests/test_tui_bottom_pane_chat_composer_history.py::test_history_entry_new_decodes_persisted_mentions_like_rust` | complete_slice | Ports the Rust constructor's `decode_history_mentions` dependency boundary: linked tool/plugin mentions become visible `$`/`@` tokens and populate `MentionBinding` values while attachment/text-element fields remain empty. |
| `bottom_pane/command_popup.rs` | command popup filtering, exact/prefix ordering, alias empty-filter hiding, service-tier display, feature gates, selection movement, row conversion | `tests/test_tui_bottom_pane_command_popup.py::{test_filter_prefix_exact_and_presentation_order,test_alias_commands_hidden_only_for_empty_filter,test_service_tier_uses_catalog_name_description_and_feature_gate,test_feature_gated_commands_and_popup_hidden_commands,test_filter_extraction_selection_movement_and_rows,test_flags_convert_to_builtin_command_flags}` | complete_slice | Ports semantic popup behavior and row DTO generation. Ratatui `WidgetRef` rendering is represented by semantic row rendering through existing selection-popup helpers. |
| `bottom_pane/command_popup.rs` | composer text filter extraction uses first line and trims whitespace after slash | `tests/test_tui_bottom_pane_command_popup.py::test_filter_extraction_uses_first_line_and_trims_after_slash` | complete_slice | Ports the first-line-only `/name <rest>` filter extraction branch and leading-whitespace trim before token selection. |
| `bottom_pane/list_selection_view.rs` | popup content/side layout widths, selection params/items/toggles, filtering and selected-index mapping, tabs, disabled-row navigation, accept/cancel/toggle, semantic row building | `tests/test_tui_bottom_pane_list_selection_view.py::{test_popup_content_and_side_by_side_width_contracts,test_initial_selection_prefers_current_then_initial_then_first_enabled,test_search_filter_maps_visible_to_actual_indices_and_notifies_callback,test_navigation_skips_disabled_rows_and_page_jump_clamp,test_toggle_accept_cancel_and_completion_flags,test_tabs_switch_visible_items_and_clear_search,test_build_rows_marks_selection_current_default_and_disabled}` | complete_slice | Ports core list-selection state behavior and visible row DTOs. Full ratatui snapshots, side-content buffer clearing, and exhaustive keymap dispatch remain renderer/runtime follow-up slices. |

| `bottom_pane/multi_select_picker.rs` | multi-select item defaults, fuzzy filter ordering, row building with section breaks, toggle/confirm/cancel callbacks, ordering constraints, page/jump navigation, semantic key input | `tests/test_tui_bottom_pane_multi_select_picker.py::{test_non_orderable_items_cannot_move_or_be_crossed,test_orderable_items_can_move_and_callbacks_fire,test_section_break_after_item_builds_separator_row,test_searchable_plain_character_updates_query_instead_of_navigating,test_toggle_confirm_cancel_and_preview_callbacks,test_navigation_page_jump_and_rows_width_height,test_match_item_display_then_canonical_fallback}` | complete_slice | Ports the picker state machine using semantic rows and string-based key events. Full ratatui rendering and exhaustive `ListKeymap` event dispatch remain runtime/renderer follow-up slices. |
| `bottom_pane/multi_select_picker.rs` | reordering disabled while search query is active | `tests/test_tui_bottom_pane_multi_select_picker.py::test_reordering_is_disabled_while_search_query_is_active` | complete_slice | Ports the `move_selected_item` early return for non-empty search queries, preserving the backing item order during filtered views. |

| `bottom_pane/status_line_style.rs` | status-line segment ordering, separator dimming, theme/fallback accent styles, RGB color softening, disabled-theme dimming, pull-request underline, empty input | `tests/test_tui_bottom_pane_status_line_style.py::{test_status_line_segments_preserve_order_and_plain_text,test_status_line_segments_dim_separators_and_use_theme_styles_first,test_status_line_segments_soften_rgb_theme_styles_without_dimming_text,test_status_line_segments_can_disable_theme_colors,test_pull_request_number_uses_link_style,test_status_line_segments_return_none_when_empty,test_color_softening_helpers_match_rust_contract}` | complete_slice | Ports ratatui `Line`/`Span`/`Style` behavior as semantic `StyledLine`/`StyledSpan` values while preserving visible text, foreground colors, dim and underline modifiers. |
| `bottom_pane/status_line_style.rs` | `STATUS_LINE_SEPARATOR` visible copy | `tests/test_tui_bottom_pane_status_line_style.py::test_status_line_separator_matches_rust_copy` | complete | Pins Rust's exact `" 路 "` separator constant separately from composite line rendering. |

| `bottom_pane/status_surface_preview.rs` | preview item order/placeholders, live vs placeholder precedence, placeholder suppression, rate-limit preview copy naming/descriptions, status-line item to preview value mapping | `tests/test_tui_bottom_pane_status_surface_preview.py::{test_default_populates_all_rust_placeholders_in_iter_order,test_live_values_override_placeholders_and_placeholders_do_not_override_live_values,test_suppress_placeholder_only_removes_placeholder_values,test_rate_limit_preview_copy_prefixes_and_fallbacks,test_rate_limit_item_name_and_description_only_use_live_values,test_status_line_for_items_maps_status_items_to_preview_values}` | complete_slice | Ports preview data behavior and semantic status-line bridge. Rust `StatusLineItem` is accepted by name/preview-item protocol so full setup-view behavior remains owned by `status_line_setup.rs`. |

| `bottom_pane/unified_exec_footer.rs` | process-list change detection, empty predicate, summary grammar, count-based copy, width boundary, prefix truncation, dim footer-line semantics, render height clipping | `tests/test_tui_bottom_pane_unified_exec_footer.py::{test_new_empty_footer_has_no_summary_or_height,test_set_processes_reports_only_real_changes_and_uses_copies,test_summary_text_uses_singular_and_plural_grammar,test_render_lines_width_boundaries_and_dim_semantics,test_many_sessions_summary_is_count_based_not_command_based,test_render_clips_to_area_and_accepts_area_shapes}` | complete_slice | Ports footer state and visible summary rendering as semantic `FooterLine` rows instead of ratatui `Paragraph`/`Buffer` cells. |

| `bottom_pane/app_link_view.rs` | external URL validation, ChatGPT auth host allowlist, URL elicitation params, action labels, toggle/open/confirm/decline state transitions, terminal-title action predicate, matching request dismissal, semantic content lines | `tests/test_tui_bottom_pane_app_link_view.py::{test_validate_external_url_and_chatgpt_auth_hosts,test_codex_apps_auth_url_elicitation_builds_auth_app_link_params,test_generic_url_elicitation_builds_generic_params_and_rejects_bad_url,test_installed_app_actions_toggle_and_emit_event,test_tool_suggestion_open_confirm_accept_and_refresh_for_codex_apps,test_decline_enable_suggestion_and_terminal_title_action,test_content_lines_include_browser_url_and_keep_url_like_token_unsplit,test_selection_navigation_back_and_dismiss_matching_request}` | complete_slice | Ports the core app-link state machine and visible text as semantic data/events. Full ratatui snapshot rendering, exact keymap remapping, and app-server protocol concrete variant types remain renderer/runtime dependency boundaries. |

| `bottom_pane/custom_prompt_view.rs` | initial text/cursor setup, Enter submit trim/non-empty gate, modified Enter textarea input, Esc/Ctrl-C cancellation, paste boundaries, desired/input height, cursor offset, semantic render lines | `tests/test_tui_bottom_pane_custom_prompt_view.py::{test_new_sets_initial_text_and_cursor_to_end,test_enter_submits_trimmed_non_empty_text_and_marks_accepted,test_enter_with_empty_trimmed_text_does_not_submit_or_complete,test_modified_enter_inserts_newline_instead_of_submit,test_escape_ctrl_c_and_paste_boundaries,test_height_and_cursor_position_follow_rust_offsets,test_render_uses_title_context_gutter_placeholder_and_hint}` | complete_slice | Ports the custom prompt view state/input contract with a lightweight semantic textarea and display lines. Exact ratatui buffer rendering and full textarea widget internals remain dependency/module boundaries. |

| `bottom_pane/experimental_features_view.rs` | feature item rows, initial selection, wrap/page/jump navigation, toggle selected, rows width, save-on-close event, complete state, hint and empty render text | `tests/test_tui_bottom_pane_experimental_features_view.py::{test_new_initializes_selection_only_when_features_exist,test_build_rows_marks_selected_and_enabled_state,test_navigation_wraps_pages_and_jumps_with_scroll_visibility,test_toggle_selected_and_key_events,test_on_ctrl_c_saves_updates_and_completes_only_when_features_exist,test_rows_width_hint_desired_height_and_render_empty_state}` | complete_slice | Ports the experimental feature toggle state machine and visible row/hint semantics as semantic data. Full ratatui block/layout rendering and exhaustive keymap remapping remain renderer/runtime follow-up slices. |

| `bottom_pane/skills_toggle_view.rs` | empty-filter initialization, search query filtering/sorting, selected item preservation, row marker/truncation, wrap/page/jump navigation, plain character search, toggle event, close/reload events, rows width/height, hint and empty render text | `tests/test_tui_bottom_pane_skills_toggle_view.py::{test_new_applies_empty_filter_and_initial_selection,test_build_rows_uses_selection_enabled_marker_and_truncation,test_filter_matches_display_name_then_skill_name_and_preserves_selection,test_navigation_page_jump_and_plain_character_search_behavior,test_toggle_selected_sends_set_skill_enabled_event,test_close_is_idempotent_and_triggers_manage_closed_and_reload,test_rows_width_height_hint_and_render_empty_state}` | complete_slice | Ports skills toggle state/search behavior as semantic rows/events. Uses module-local minimal skill match/truncation adapter because `skills_helpers` remains a separate dependency boundary. Full ratatui rendering and exhaustive keymap binding formatting remain follow-up slices. |

| `bottom_pane/skill_popup.rs` | mention item DTO, empty-query ordering beyond popup height, required height, wrap navigation/scroll window, selected mention lookup, display-name vs search-term fuzzy ranking, plugin rank bias after score, description/category composition, truncation, empty render text and hint | `tests/test_tui_bottom_pane_skill_popup.py::{test_filtered_mentions_preserve_results_beyond_popup_height,test_scrolling_mentions_shifts_rendered_window_and_selection,test_display_name_match_sorting_beats_worse_secondary_search_term_matches,test_query_match_score_sorts_before_plugin_rank_bias,test_rows_description_composition_and_truncation,test_set_mentions_query_clamp_empty_and_hint_line}` | complete_slice | Ports skill popup filtering and semantic row behavior. Python uses a focused fuzzy-score adapter to match Rust test ordering; exact ratatui cell snapshots remain renderer follow-up work. |

| `bottom_pane/feedback_view.rs` | feedback note input/submit/cancel/paste, title/placeholder/classification, connectivity diagnostics visibility, issue URL routing, success copy, feedback selection/disabled params, upload consent attachment/diagnostic lines and actions | `tests/test_tui_bottom_pane_feedback_view.py::{test_feedback_title_placeholder_and_classification_matrix,test_submit_feedback_emits_submit_event_with_trimmed_note_and_empty_note,test_key_paste_height_cursor_and_render_contracts,test_connectivity_details_only_for_non_good_result_with_diagnostics,test_issue_url_and_feedback_success_copy_matrix,test_feedback_selection_disabled_and_upload_consent_params,test_feedback_upload_consent_lists_attachments_and_diagnostics}` | complete_slice | Ports feedback view behavior as semantic lines, selection params, and event dictionaries. Exact ratatui buffers, WebHyperlinkHistoryCell styling, and app-server feedback upload transport remain renderer/runtime boundaries. |

| \`bottom_pane/mcp_server_elicitation.rs\` | boolean form parsing, unsupported numeric rejection, empty-object approval actions, tool approval persist actions, tool suggestion metadata, approval display params/message formatting, form submit, persist submit, Ctrl-C cancel, FIFO queue, resolved-request dismissal | \`tests/test_tui_bottom_pane_mcp_server_elicitation.py::{test_parses_boolean_form_request,test_unsupported_numeric_form_falls_back_to_none,test_empty_object_schema_uses_approval_actions,test_empty_tool_approval_schema_uses_persist_actions_and_cancel,test_tool_suggestion_meta_is_parsed_into_request_payload,test_plugin_tool_suggestion_meta_without_install_url_is_parsed,test_tool_approval_display_params_prefer_explicit_display_order,test_tool_approval_display_params_fallback_sort_and_format,test_submit_sends_accept_with_typed_content,test_session_and_always_choices_set_persist_meta,test_ctrl_c_cancels_elicitation,test_queues_requests_fifo,test_resolved_request_dismisses_overlay_without_emitting_events}\` | complete_slice | Ports schema/request parsing, approval action semantics, tool suggestion DTOs, display-param formatting, answer submission, cancellation, and overlay FIFO/dismiss lifecycle as semantic events. Exact ratatui overlay rendering, textarea widget internals, and exhaustive keymap dispatch remain renderer/runtime follow-up slices. |

| \`bottom_pane/status_line_setup.rs\` | status-line item canonical IDs, legacy aliases, preview item mapping, runtime/placeholder preview values, thread-title preview, setup view item ordering/deduplication, theme-color toggle, rate-limit item copy, confirm/cancel events, semantic render lines | \`tests/test_tui_bottom_pane_status_line_setup.py::{test_status_line_item_canonical_and_legacy_ids,test_git_and_title_only_items_are_parseable,test_preview_uses_runtime_values_and_placeholders,test_preview_includes_thread_title,test_setup_view_orders_configured_items_first_dedupes_and_adds_theme_toggle,test_rate_limit_select_item_uses_runtime_copy,test_confirm_sends_status_line_setup_and_cancel_sends_cancelled,test_render_lines_uses_runtime_preview_values}\` | complete_slice | Ports StatusLineItem parsing/display/description/preview mapping and StatusLineSetupView picker construction, preview, confirmation, cancellation, and visible semantic lines. Full ratatui snapshot cell rendering and exhaustive keymap handling remain renderer/runtime follow-up slices. |

| \`bottom_pane/mentions_v2/search_mode.rs\` | SearchMode previous/next cycling, MentionType acceptance filters, visible labels | \`tests/test_tui_bottom_pane_mentions_v2_search_mode.py::{test_previous_cycles_results_filesystem_tools_like_rust,test_next_cycles_results_filesystem_tools_like_rust,test_accepts_all_results_mode,test_filesystem_only_accepts_files_and_directories_only,test_tools_accepts_plugins_and_skills_only,test_labels_match_rust_visible_copy}\` | complete | Ports the full module-local enum behavior. Python accepts duck-typed/string mention types so candidate.rs can remain a separate module boundary. |

| \`bottom_pane/mentions_v2/candidate.rs\` | TAG_WIDTH, Selection variants, MentionType filesystem predicate, padded tag labels/spans, Candidate::to_result clone-like DTO conversion | \`tests/test_tui_bottom_pane_mentions_v2_candidate.py::{test_tag_width_matches_plugin_label_width,test_mention_type_is_filesystem_matches_rust,test_mention_type_labels_and_padded_spans_match_rust_visible_tags,test_mention_type_span_applies_semantic_styles,test_selection_file_and_tool_variants_preserve_fields,test_candidate_to_result_clones_candidate_fields_and_match_indices}\` | complete_slice | Ports module-local candidate/result DTO behavior and semantic mention tag spans. Ratatui Style/Span concrete types are represented by SemanticSpan; exact terminal styling remains renderer-level. |

| \`bottom_pane/mentions_v2/filter.rs\` | filtered_candidates query trimming, search-mode filtering, tool fuzzy matching, search-term fallback, optional file-match rows, file-match conversion, row sorting by type/directness/score/name | \`tests/test_tui_bottom_pane_mentions_v2_filter.py::{test_empty_query_returns_accepted_candidates_with_zero_scores_and_type_sorting,test_best_tool_match_prefers_display_name_indices_then_search_terms_score_only,test_filtered_candidates_applies_search_mode_before_matching,test_file_matches_are_appended_when_enabled_and_filtered_by_mode,test_file_match_to_row_preserves_indices_and_score,test_sort_rows_orders_tools_by_direct_match_before_search_term_match,test_filesystem_rows_sort_by_descending_score_within_rank}\` | complete_slice | Ports the module-local filtering and sorting contract with a deterministic Python fuzzy-match adapter. Real codex-file-search FileMatch backend remains a dependency boundary represented by compatible DTO/dict inputs. |

| \`bottom_pane/mentions_v2/footer.rs\` | footer hint visible copy, search-mode indicator labels/styles, right-aligned indicator layout, narrow-width hiding, left hint truncation | \`tests/test_tui_bottom_pane_mentions_v2_footer.py::{test_footer_hint_line_matches_visible_key_copy,test_search_mode_indicator_labels_and_active_styles,test_tools_search_mode_uses_magenta_active_style,test_render_footer_splits_left_and_right_with_gap,test_render_footer_hides_right_line_when_width_too_narrow,test_left_footer_truncates_when_width_is_small}\` | complete_slice | Ports visible footer contract as semantic FooterLine/FooterSpan/RenderedFooter values. Ratatui Buffer/Rect cell mutation and exact key_hint glyph formatting remain renderer-level follow-up slices. |

| \`bottom_pane/mentions_v2/render.rs\` | file-name/path splitting, primary/secondary span construction, match highlighting, selected-row style, content alignment, tag placement, empty row rendering, scroll-window selection adjustment, popup footer inclusion | \`tests/test_tui_bottom_pane_mentions_v2_render.py::{test_file_name_start_and_primary_text_width_for_filesystem_rows,test_primary_spans_highlight_match_indices_for_tools_and_cyan_file_names,test_path_spans_show_dot_slash_or_path_prefix_with_highlights,test_secondary_line_for_file_combines_path_and_description,test_content_line_aligns_secondary_column_by_primary_width,test_build_line_places_tag_at_right_and_bolds_selected_rows,test_render_rows_empty_scroll_window_and_selection_adjustment,test_render_popup_adds_footer_when_area_is_tall_enough}\` | complete_slice | Ports the visible row-rendering contract with semantic RenderLine/RenderSpan/RenderedPopup values. Ratatui Buffer/Rect cell mutation and exact unicode-width truncation remain renderer-level follow-up slices. |

| \`bottom_pane/mentions_v2/search_catalog.rs\` | build_search_catalog skill/plugin ordering, skill candidate display/description/search terms/selection, plugin config-name marketplace split, plugin search terms/selection, explicit/fallback plugin descriptions, capability labels pluralization | \`tests/test_tui_bottom_pane_mentions_v2_search_catalog.py::{test_build_search_catalog_preserves_skill_then_plugin_order_and_handles_none,test_skill_candidate_uses_display_name_description_terms_and_tool_selection,test_skill_candidate_omits_duplicate_display_name_and_blank_description,test_plugin_candidate_splits_marketplace_name_and_builds_terms_selection,test_plugin_candidate_without_marketplace_or_display_alias_terms,test_plugin_description_prefers_explicit_description,test_plugin_capability_labels_and_fallback_descriptions}\` | complete_slice | Ports the module-local catalog DTO conversion. External SkillMetadata, PluginCapabilitySummary, and skills_helpers are represented by duck-typed objects/dicts instead of pulling in dependency crate implementations. |

| \`bottom_pane/request_user_input/layout.rs\` | no-options tight/normal layout, options layout question truncation, hidden/visible notes allocation, section area stacking, layout_sections area/question/footer output | \`tests/test_tui_bottom_pane_request_user_input_layout.py::{test_layout_without_options_tight_truncates_question_and_hides_everything_else,test_layout_without_options_normal_allocates_notes_footer_progress_and_extra_to_notes,test_layout_with_options_truncates_question_to_leave_minimum_option_row,test_layout_with_options_hidden_notes_reserves_progress_footer_and_spacers_by_shrinking_options,test_layout_with_options_visible_notes_prefers_footer_spacer_then_notes,test_build_layout_areas_stacks_sections_with_spacers,test_layout_sections_without_options_returns_truncated_lines_and_areas,test_layout_sections_with_options_uses_options_area_and_footer_lines}\` | complete_slice | Ports the pure layout planning contract with semantic Rect/LayoutPlan/LayoutSections values and duck-typed overlay height hooks. Exact ratatui Rect type integration remains a renderer/runtime boundary. |

| \`bottom_pane/request_user_input/render.rs\` | desired_height component/minimum behavior, unanswered confirmation data/height, line width, word-boundary ellipsis truncation, bottom-aligned rows, cursor-position gating, semantic render_ui normal and unanswered branches | \`tests/test_tui_bottom_pane_request_user_input_render.py::{test_desired_height_uses_minimum_and_component_heights,test_unanswered_confirmation_data_pluralizes_and_carries_rows_state,test_unanswered_confirmation_height_respects_minimum,test_line_width_and_word_boundary_truncation,test_render_rows_bottom_aligned_offsets_short_rows_to_bottom,test_cursor_pos_only_when_notes_focused_visible_and_area_nonzero,test_render_ui_outputs_progress_question_notes_and_footer_semantics,test_render_ui_unanswered_confirmation_branch}\` | complete_slice | Ports visible/render planning behavior with semantic StyledLine/StyledSpan render events. Ratatui Buffer/Paragraph/Widget mutation, exact menu surface drawing, and full selection renderer integration remain renderer/runtime follow-up slices. |
| `bottom_pane/request_user_input/render.rs` | desired-height component/minimum behavior, unanswered confirmation data/height, line width, word-boundary ellipsis truncation, bottom-aligned rows, cursor-position gating, semantic render_ui normal and unanswered branches | `tests/test_tui_bottom_pane_request_user_input_render.py::{test_desired_height_uses_minimum_and_component_heights,test_unanswered_confirmation_data_pluralizes_and_carries_rows_state,test_unanswered_confirmation_height_respects_minimum,test_line_width_and_word_boundary_truncation,test_render_rows_bottom_aligned_offsets_short_rows_to_bottom,test_cursor_pos_only_when_notes_focused_visible_and_area_nonzero,test_render_ui_outputs_progress_question_notes_and_footer_semantics,test_render_ui_unanswered_confirmation_branch}` | complete_slice | Ports the module's layout/render planning into semantic Python events instead of ratatui buffer cells; full pixel/cell painting remains framework-adapted debt. |
| `auto_review_denials.rs` | `RecentAutoReviewDenials::push/is_empty/entries/take`, `action_summary`, `keeps_only_ten_most_recent_denials` | `tests/test_tui_auto_review_denials.py::{test_keeps_only_ten_most_recent_denials_matches_rust_order,test_push_ignores_non_denied_and_deduplicates_by_id,test_take_removes_matching_denial,test_action_summary_variants_follow_rust_text,test_dict_inputs_are_supported_for_protocol_facades}` | complete | Ports the full module-local behavior: denied-only insertion, id deduplication, newest-first bounded deque, removal by id, and user-facing action summary strings. |
| `app_backtrack.rs` | `BacktrackState`, `BacktrackSelection`, `PendingBacktrackRollback`, transcript user/session/agent position iterators, trim-to-nth-user, drop-last-n-user-turns, global Esc decision, overlay event decision, prime state, overlay close/sync state, state reset, main confirm selection/reset, selection stepping/payload extraction, rollback planning/completion, Rust helper tests | `tests/test_tui_app_backtrack.py::{test_backtrack_state_defaults_match_rust,test_selection_and_pending_rollback_carry_payloads,test_user_positions_restart_after_latest_session_cell,test_trim_transcript_for_first_user_drops_user_and_newer_cells,test_trim_transcript_preserves_cells_before_selected_user,test_trim_transcript_for_later_user_keeps_prior_history,test_trim_drop_last_n_user_turns_applies_rollback_semantics,test_trim_drop_last_n_user_turns_allows_overflow_and_ignores_zero,test_agent_group_count_ignores_context_compacted_marker_and_stream_continuations,test_backtrack_target_requires_user_message,test_backtrack_unavailable_info_message_snapshot_text,test_reset_backtrack_state_resets_rust_state_fields,test_backtrack_selection_matches_thread_and_copies_user_payloads,test_backtrack_selection_returns_empty_selection_when_user_index_is_stale,test_apply_backtrack_rollback_state_plans_pending_rollback_and_composer_payload,test_apply_backtrack_rollback_state_ignores_empty_or_zero_turn_cases,test_apply_backtrack_rollback_state_reports_pending_guard_without_mutating,test_handle_backtrack_rollback_succeeded_finishes_pending_matching_thread,test_handle_backtrack_rollback_succeeded_ignores_stale_thread_pending,test_handle_backtrack_rollback_succeeded_without_pending_applies_thread_rollback,test_handle_backtrack_rollback_failed_clears_pending_guard,test_backtrack_selection_index_steps_older_like_rust,test_forward_backtrack_selection_index_steps_newer_like_rust,test_apply_backtrack_selection_index_sets_state_and_returns_highlight_cell,test_confirm_backtrack_from_main_returns_selection_and_resets_state,test_confirm_backtrack_from_main_resets_state_even_without_matching_thread,test_prime_backtrack_state_sets_base_and_reports_hint_target,test_prime_backtrack_state_does_not_request_hint_without_user_target,test_close_transcript_overlay_state_resets_backtrack_preview_state,test_close_transcript_overlay_state_preserves_non_preview_backtrack_fields,test_sync_overlay_after_transcript_trim_clamps_preview_selection,test_sync_overlay_after_transcript_trim_clears_selection_when_no_users_remain,test_sync_overlay_after_transcript_trim_without_preview_only_reports_side_effects,test_handle_backtrack_esc_key_ignores_non_empty_composer,test_handle_backtrack_esc_key_primes_when_unprimed,test_handle_backtrack_esc_key_requests_open_or_step_when_primed,test_handle_backtrack_overlay_event_routes_preview_navigation,test_handle_backtrack_overlay_event_forwards_when_preview_unarmed,test_handle_backtrack_overlay_event_begins_preview_only_on_esc_outside_preview}` | complete_slice | Ports the module-local transcript trimming, position-counting, pure global Esc decision, pure overlay event decision, prime/reset/overlay-close/overlay-sync backtrack state, preview selection clamping after trims, main-view confirm selection/reset, selection stepping/clamping, highlight-cell index selection, base-thread guard, selected user payload extraction, pending rollback guard, rollback turn-count planning, pending rollback recording, remote-image/composer payload extraction, pending rollback success/failure clearing, stale-thread ignore, and non-pending rollback trim planning. App/Tui event routing, alt-screen switching, actual deferred scrollback flushing, ChatWidget hint clearing/history truncation, actual event dispatch, scrollback refresh scheduling, overlay cell replacement, and live transcript overlay drawing remain higher-level runtime slices. |
| `app_backtrack.rs` | preview open/begin state planning | `tests/test_tui_app_backtrack.py::test_open_backtrack_preview_state_handles_missing_target_with_info_plan`, `tests/test_tui_app_backtrack.py::test_open_backtrack_preview_state_opens_preview_and_selects_latest_user`, `tests/test_tui_app_backtrack.py::test_begin_overlay_backtrack_preview_state_selects_latest_user_or_closes_empty_overlay` | complete_slice | Ports no-target info/reset planning, main backtrack preview opening, and overlay BeginBacktrack preview priming/selection as semantic state plans. Runtime overlay construction, frame scheduling, and terminal rendering remain boundary. |
| `app/pending_interactive_replay.rs` | `PendingInteractiveReplayState` request/op/notification state machine, FIFO request_user_input answer handling, approval/elicitation/permissions replay filtering, turn/thread clear, eviction, pending flags, Rust helper tests | `tests/test_tui_app_pending_interactive_replay.py::{test_pending_request_user_input_replays_until_answered_or_resolved,test_request_user_input_fifo_for_same_turn,test_exec_patch_elicitation_resolution_paths_match_rust_tests,test_turn_completion_and_thread_close_clear_pending_requests,test_pending_thread_approval_flags_exclude_request_user_input,test_op_can_change_state_matches_rust_match_set,test_item_started_and_eviction_clear_matching_pending_request,test_permissions_request_counts_as_pending_approval_and_clears_by_turn,test_snapshot_filters_only_interactive_request_kinds}` | complete_slice | Ports the module-local pending interactive replay contract with semantic app-server request/notification/op DTOs. Full Rust `ThreadEventStore` integration remains owned by the surrounding app module. |
| `app/replay_filter.rs` | `snapshot_has_pending_interactive_request`, `event_is_notice` | `tests/test_tui_app_replay_filter.py::{test_snapshot_has_pending_interactive_request_for_all_rust_request_variants,test_snapshot_has_pending_interactive_request_ignores_non_request_and_other_request,test_event_is_notice_for_warning_guardian_and_config_warnings,test_event_is_notice_ignores_requests_and_other_notifications,test_dict_and_object_shaped_inputs_are_supported}` | complete | Ports the full module-local replay filtering behavior with semantic buffered event/request/notification shapes. |
| `app/thread_events.rs` | `ThreadEventStore` active-turn lifecycle, snapshot active-turn restore, clear active turn, session-refresh rebase, hook preservation, capacity eviction, snapshot request filtering, side parent pending status, rollback reset, file-change lookup helpers | `tests/test_tui_app_thread_events.py::{test_thread_event_store_tracks_active_turn_lifecycle,test_thread_event_store_restores_and_clears_active_turn,test_rebase_preserves_resolved_request_state_and_hooks,test_event_survives_session_refresh_matches_rust_variants,test_snapshot_filters_resolved_requests_but_keeps_other_events,test_capacity_eviction_updates_pending_request_state,test_side_parent_pending_status_prefers_user_input_then_approval,test_turn_id_and_file_change_lookup_helpers,test_file_change_changes_searches_buffer_then_turns,test_apply_thread_rollback_resets_buffer_pending_and_active_turn}` | complete_slice | Ports the module-local event buffer/snapshot state with semantic request/notification/turn DTOs. Real mpsc channel behavior remains a runtime integration boundary. |
| `app/loaded_threads.rs` | `thread_spawn_parent_thread_id`, `find_loaded_subagent_threads_for_primary`, Rust `finds_loaded_subagent_tree_for_primary_thread` | `tests/test_tui_app_loaded_threads.py::{test_finds_loaded_subagent_tree_for_primary_thread_matches_rust,test_invalid_thread_ids_and_non_spawn_sources_are_ignored,test_output_is_sorted_by_thread_id_not_input_order,test_thread_spawn_parent_thread_id_accepts_json_shape_and_rejects_invalid,test_dict_and_object_threads_are_supported}` | complete | Ports the pure loaded-thread subagent spawn-tree walk, including invalid-id skipping, transitive child discovery, JSON-shaped spawn-source parsing, and sorted output. |
| `tui/frame_rate_limiter.rs` | `MIN_FRAME_INTERVAL`, `FrameRateLimiter::clamp_deadline`, `FrameRateLimiter::mark_emitted`, Rust `default_does_not_clamp`, Rust `clamps_to_min_interval_since_last_emit` | `tests/test_tui_frame_rate_limiter.py::{test_default_does_not_clamp_matches_rust,test_clamps_to_min_interval_since_last_emit_matches_rust,test_requested_after_min_interval_is_not_moved_back,test_mark_emitted_replaces_previous_instant,test_datetime_deadlines_use_same_min_interval_semantics}` | complete | Ports the pure 120 FPS deadline clamp helper with exact nanosecond interval semantics for integer monotonic deadlines and a semantic datetime adapter. |
| `app/agent_navigation.rs` | `AgentNavigationState`, `AgentNavigationDirection`, picker name/shortcut labels, Rust `upsert_preserves_first_seen_order`, `adjacent_thread_id_wraps_in_spawn_order`, `picker_subtitle_mentions_shortcuts`, `active_agent_label_tracks_current_thread` | `tests/test_tui_app_agent_navigation.py::{test_upsert_preserves_first_seen_order_matches_rust,test_adjacent_thread_id_wraps_in_spawn_order_matches_rust,test_picker_subtitle_mentions_shortcuts_matches_rust,test_active_agent_label_tracks_current_thread_matches_rust,test_mark_closed_remove_clear_and_non_primary_semantics,test_adjacent_thread_id_requires_current_and_two_entries,test_active_agent_label_fallbacks_and_single_thread_suppression,test_format_agent_picker_item_name_matches_rust_cases}` | complete | Ports the pure multi-agent navigation cache, stable first-seen ordering, wraparound traversal, close/remove/clear behavior, active footer labels, and picker subtitle shortcut text as semantic Python state. |
| `app/app_server_event_targets.rs` | `server_request_thread_id`, `ServerNotificationThreadTarget`, `server_notification_thread_target`, Rust warning/guardian/thread-settings routing tests | `tests/test_tui_app_server_event_targets.py::{test_warning_notifications_without_threads_are_global_matches_rust,test_warning_notifications_route_to_threads_when_thread_id_is_present_matches_rust,test_guardian_warning_notifications_route_to_threads_matches_rust,test_thread_settings_updated_notifications_route_to_threads_matches_rust,test_server_request_thread_id_extracts_only_supported_request_variants,test_thread_started_reads_nested_thread_id,test_invalid_notification_thread_id_is_preserved,test_global_notification_variants_are_global,test_object_shaped_requests_and_notifications_are_supported,test_thread_settings_fixture_shape_matches_rust_fields}` | complete_slice | Ports thread-id extraction and notification target classification with dict/object semantic app-server variants. Concrete app-server protocol enum types remain a dependency boundary. |
| `app/agent_message_consolidation.rs` | `App::handle_consolidate_agent_message`, deferred history cell insertion, trailing `AgentMessageCell` run replacement with `AgentMarkdownCell`, overlay consolidation/frame scheduling, stream reflow completion mode | `tests/test_tui_app_agent_message_consolidation.py::{test_consolidates_trailing_agent_message_cells,test_deferred_history_cell_is_inserted_before_consolidation,test_no_trailing_agent_cells_finishes_stream_reflow_only,test_trailing_run_start_ignores_non_tail_agent_cells,test_consolidation_without_overlay_replaces_transcript_without_frame_request,test_dict_and_object_agent_message_cells_are_supported_semantically}` | complete_slice | Ports the module-local consolidation state transition with semantic cells/overlay/TUI frame requester. Concrete `App`, `HistoryCell`, pager overlay, and resize-reflow integration remain neighboring module/runtime boundaries. |
| `transcript_reflow.rs` | `TRANSCRIPT_REFLOW_DEBOUNCE`, `TranscriptReflowState`, `TranscriptWidthChange`, all local Rust state-machine tests | `tests/test_tui_transcript_reflow.py::{test_schedule_debounced_postpones_existing_reflow_matches_rust,test_schedule_debounced_postpones_due_existing_reflow_matches_rust,test_first_observed_width_marks_reflow_baseline_matches_rust,test_mark_reflowed_width_records_actual_rebuild_width_matches_rust,test_reflow_needed_compares_against_actual_rebuild_width_matches_rust,test_pending_reflow_target_prevents_repeated_reschedule_matches_rust,test_clear_pending_reflow_allows_same_width_to_be_rescheduled_matches_rust,test_mark_reflowed_width_reports_unchanged_width_matches_rust,test_take_stream_finish_reflow_needed_drains_resize_request_matches_rust,test_take_stream_finish_reflow_needed_drains_ran_during_stream_matches_rust,test_clear_resets_stream_reflow_flags_matches_rust,test_schedule_immediate_sets_due_and_clears_target_width,test_clear_stream_flags_preserves_width_and_pending_state,test_debounce_constant_matches_rust_duration}` | complete | Ports the pure transcript resize-reflow scheduling state machine, including observed/reflowed width separation, pending target suppression, debounce/immediate deadlines, and stream repair flags. |
| `tui/frame_requester.rs` | `FrameRequester`, `FrameScheduler`, all local scheduler/coalescing/rate-limit Rust tests | `tests/test_tui_frame_requester.py::{test_schedule_frame_immediate_triggers_once_matches_rust,test_schedule_frame_in_triggers_at_delay_matches_rust,test_coalesces_multiple_requests_into_single_draw_matches_rust,test_coalesces_mixed_immediate_and_delayed_requests_matches_rust,test_limits_draw_notifications_to_120fps_matches_rust,test_rate_limit_clamps_early_delayed_requests_matches_rust,test_rate_limit_does_not_delay_future_draws_matches_rust,test_multiple_delayed_requests_coalesce_to_earliest_matches_rust,test_shared_draw_channel_receives_scheduler_notifications,test_test_dummy_is_noop_like_rust_helper}` | complete_slice | Ports scheduler semantics with deterministic time advancement: immediate/delayed requests, earliest-deadline coalescing, 120 FPS rate limiting, and test-dummy no-op behavior. Real tokio mpsc/broadcast task lifecycle remains a runtime boundary. |
| `app/app_server_requests.rs` | `PendingAppServerRequests`, `AppServerRequestResolution`, `UnsupportedAppServerRequest`, `ResolvedAppServerRequest`, Rust request correlation/FIFO/unsupported tests | `tests/test_tui_app_server_requests.py::{test_resolves_exec_approval_through_app_server_request_id_matches_rust,test_resolves_permissions_and_user_input_through_app_server_request_id_matches_rust,test_correlates_mcp_elicitation_server_request_with_resolution_matches_rust,test_rejects_dynamic_tool_calls_as_unsupported_matches_rust,test_does_not_mark_chatgpt_auth_refresh_as_unsupported_matches_rust,test_resolves_patch_approval_through_app_server_request_id_matches_rust,test_resolve_notification_returns_resolved_exec_request_matches_rust,test_resolve_notification_returns_resolved_mcp_request_matches_rust,test_resolve_notification_returns_resolved_user_input_item_id_matches_rust,test_same_turn_user_input_answers_resolve_app_server_requests_fifo_matches_rust,test_contains_server_request_and_clear_semantics,test_approval_id_falls_back_to_item_id,test_remove_user_input_request_deletes_empty_turn_queue,test_unsupported_legacy_requests_use_rust_messages,test_resolve_notification_removes_permission_request}` | complete_slice | Ports the local pending app-server request correlation state, resolution/removal rules, user-input FIFO behavior, MCP key matching, contains/clear semantics, and unsupported-request messages. Full protocol crate permission-profile conversion and async reject transport remain dependency/runtime boundaries. |
| `app/history_ui.rs` | `open_url_in_browser`, `clear_ui_header_lines_with_version`, `queue_clear_ui_header`, `clear_terminal_ui`, `reset_app_ui_state_after_clear`, `reset_transcript_state_after_clear` | `tests/test_tui_app_history_ui.py::{test_open_url_success_and_failure_messages,test_clear_terminal_ui_alt_and_inline_branches,test_reset_transcript_state_after_clear_resets_owned_state,test_header_lines_include_model_cwd_version_effort_fast_and_yolo_semantics,test_queue_clear_ui_header_sets_history_emitted_only_when_lines_exist,test_clear_terminal_ui_without_redraw_does_not_queue_header}` | complete_slice | Ports module-local URL message, clear-screen branching, header queueing, viewport anchoring, and transcript/backtrack/reflow reset semantics with semantic App/Tui/Terminal models. Exact `SessionHeaderHistoryCell` ratatui rendering and real browser launching remain dependency/runtime boundaries. |
| `tui/keyboard_modes.rs` | env flag parsing, WSL/VSCode disable rules, tmux detection, modifyOtherKeys csi-u gate, reset/enable/disable ANSI command writers, restore/reset command order | `tests/test_tui_keyboard_modes.py::{test_keyboard_enhancement_env_flag_parses_common_values_matches_rust,test_keyboard_enhancement_auto_disables_for_vscode_in_wsl_matches_rust,test_keyboard_enhancement_auto_disable_requires_wsl_and_vscode_matches_rust,test_keyboard_enhancement_env_flag_overrides_auto_detection_matches_rust,test_vscode_terminal_detection_uses_linux_and_windows_term_program_matches_rust,test_tmux_session_detection_accepts_tmux_or_tmux_pane_matches_rust,test_tmux_modify_other_keys_only_requests_confirmed_csi_u_format_matches_rust,test_reset_keyboard_enhancement_flags_clears_all_pushed_levels_matches_rust,test_enable_modify_other_keys_requests_xterm_keyboard_reporting_matches_rust,test_disable_modify_other_keys_resets_xterm_keyboard_reporting_matches_rust,test_enable_keyboard_enhancement_returns_semantic_command_sequence,test_restore_and_reset_sequences_preserve_rust_order,test_read_helpers_parse_command_output_semantics}` | complete_slice | Ports pure detection and ANSI command behavior with semantic command sequences. Real crossterm stdout execution, WinAPI command execution, WSL cmd.exe probing, and tmux subprocess probing remain platform/runtime boundaries. |
| `tui/terminal_stderr.rs` | `TerminalStderrGuard`, `pause`, `resume`, `finish`, locked suppress/restore lifecycle, macOS tests `suppresses_stderr_only_while_terminal_is_owned`, `preserves_stderr_when_already_redirected` | `tests/test_tui_terminal_stderr.py::{test_suppresses_stderr_only_while_terminal_is_owned_matches_rust,test_preserves_stderr_when_already_redirected_matches_rust,test_install_non_macos_or_redirected_is_inactive_noop,test_install_suppression_rejects_existing_owner,test_pause_resume_finish_state_transitions_are_idempotent,test_suppress_and_restore_locked_are_idempotent,test_stderr_target_detection_requires_two_terminals_same_device,test_guard_drop_finishes_active_suppression_once}` | complete_slice | Ports terminal-stderr ownership/suppression lifecycle with semantic state and captured/hidden output. Real macOS fd dup/dup2, `/dev/null`, terminal stat comparison, and poisoned mutex behavior remain platform boundaries. |
| `tui/job_control.rs` | `SUSPEND_KEY`, `SuspendContext`, `ResumeAction`, `PreparedResumeAction`, `suspend_process` terminal-mode sequence | `tests/test_tui_job_control.py::{test_suspend_sets_restore_alt_for_alt_screen,test_suspend_sets_realign_inline_for_inline_screen,test_prepare_resume_action_consumes_realign_inline,test_prepare_resume_action_restores_alt_and_updates_saved_viewport,test_realign_inline_falls_back_to_last_known_cursor_position,test_prepared_resume_action_apply_realign_viewport,test_prepared_resume_action_apply_restore_alt_screen,test_suspend_process_trace_order_and_suspend_key}` | complete_slice | Ports suspend/resume intent capture, cached cursor row, pending action consumption, viewport realignment, alt-screen restore semantics, and process-suspend mode sequence as semantic state. Real SIGTSTP delivery and crossterm terminal commands remain platform/runtime boundaries. |
| `voice.rs` | `MODEL_AUDIO_*`, `VoiceCapture` stop/accessors, `RecordingMeterState`, f32/i16/u16 peak/conversion helpers, `send_realtime_audio_chunk`, `RealtimeAudioPlayer` queue decode/clear, output fill helpers, `convert_pcm16`, Rust `convert_pcm16_downmixes_and_resamples_for_model_input` | `tests/test_tui_voice.py::{test_convert_pcm16_downmixes_and_resamples_for_model_input_matches_rust,test_f32_conversion_and_peak_helpers_match_rust_boundaries,test_convert_u16_to_i16_and_peak_matches_rust_centering,test_send_realtime_audio_chunk_encodes_little_endian_model_audio,test_send_realtime_audio_chunk_converts_non_model_audio_before_encoding,test_send_realtime_audio_chunk_ignores_empty_or_invalid_format,test_realtime_audio_player_enqueue_frame_decodes_converts_and_clear,test_realtime_audio_player_rejects_invalid_frame_and_odd_bytes,test_fill_output_helpers_pop_queue_and_default_silence,test_convert_pcm16_channel_mapping_cases,test_recording_meter_state_returns_four_character_history,test_voice_capture_stop_sets_flag_and_clears_stream}` | complete_slice | Ports pure PCM/audio conversion, realtime chunk encoding, semantic meter state, playback queue/fill behavior, and capture/player stop/accessor boundaries. Real cpal input/output device stream setup remains explicit NotImplementedError/platform boundary; exact Rust meter glyphs are represented by an ASCII semantic ramp because the local Rust source renders those glyphs with encoding damage. |
| `get_git_diff.rs` | `get_git_diff_returns_not_git_for_non_git_cwd`, `get_git_diff_concatenates_tracked_and_untracked_diffs`, `get_git_diff_accepts_diff_exit_code_one`, `get_git_diff_rejects_unexpected_git_diff_status`, command construction timeout/output-cap semantics | `tests/test_tui_get_git_diff.py::{test_get_git_diff_returns_not_git_for_non_git_cwd_matches_rust,test_get_git_diff_concatenates_tracked_and_untracked_diffs_matches_rust,test_get_git_diff_accepts_diff_exit_code_one_matches_rust,test_get_git_diff_rejects_unexpected_git_diff_status_matches_rust,test_get_git_diff_trims_and_skips_empty_untracked_lines}` | complete | Ports the module-local git diff orchestration with injected WorkspaceCommandExecutor: non-git early return, tracked diff plus untracked no-index diffs, diff exit-code 1 success, unexpected status errors, command argv/cwd/30s timeout/disabled output cap, and platform null-device selection. |
| `external_agent_config_migration.rs` | `ExternalAgentConfigMigrationOutcome`, `FocusArea`, `ActionMenuOption`, `ExternalAgentConfigMigrationScreen` selection/action state, description reformatting, plugin detail rows, key handling, Rust prompt/navigation tests | `tests/test_tui_external_agent_config_migration.py::{test_display_description_reformats_project_paths_and_plugin_counts,test_plugin_detail_lines_cap_plugins_and_marketplaces_matches_rust,test_proceed_returns_selected_items_matches_rust,test_toggle_item_then_proceed_keeps_remaining_selection_matches_rust,test_escape_skips_prompt_matches_rust,test_skip_forever_returns_skip_forever_outcome_matches_rust,test_proceed_requires_at_least_one_selected_item_matches_rust,test_proceed_action_is_skipped_when_no_items_are_selected_matches_rust,test_numeric_shortcuts_choose_actions_matches_rust,test_action_navigation_wraps_between_items_and_actions,test_set_all_enabled_clears_error_normalizes_action_and_schedules_frame,test_build_render_lines_groups_home_and_project_sections,test_ctrl_exit_combo_and_release_key_handling,test_interactive_prompt_runtime_boundary_is_explicit}` | complete_slice | Ports the module-local migration prompt state machine, selected-item outcomes, action availability, validation error, all/none toggles, shortcut handling, project-path display descriptions, plugin detail truncation, and semantic render rows. Real TUI event loop, frame drawing, ratatui cell rendering, and exact snapshot styling remain renderer/runtime boundaries. |
| `external_agent_config_migration_startup.rs` | prompt feature/trust gate, hidden scope filtering, cooldown filtering/expiry, success message copy, prompt-shown/dismissal persistence semantics, startup proceed/skip runtime slice | `tests/test_tui_external_agent_config_migration_startup.py::{test_visible_external_agent_config_migration_items_omits_hidden_scopes_matches_rust,test_visible_external_agent_config_migration_items_omits_recently_prompted_scopes_matches_rust,test_external_config_migration_scope_cooldown_expires_after_five_days_matches_rust,test_external_agent_config_migration_success_message_mentions_plugins_when_present_matches_rust,test_external_agent_config_migration_success_message_omits_plugins_copy_when_absent_matches_rust,test_external_agent_config_migration_prompt_requires_trust_nux_entry_matches_rust,test_project_key_and_last_prompt_lookup_match_scope_rules,test_persist_prompt_shown_updates_home_and_project_timestamps_semantically,test_persist_prompt_dismissal_hides_home_and_unique_projects_semantically,test_handle_prompt_skip_and_proceed_paths_are_semantic_runtime_slice,test_handle_prompt_requires_runner_when_visible_items_need_tui}` | complete_slice | Ports startup gating, scope visibility/cooldown, success-copy, timestamp/dismissal mutation, and a semantic app-server/prompt-runner orchestration slice. Real config file edit persistence, full ConfigBuilder reload, app-server protocol DTOs, and TUI prompt loop remain dependency/runtime boundaries. |
| `oss_selection.rs` | `ProviderStatus`, `OssSelectionWidget` provider option state, Ctrl-H/Ctrl-L Rust test, arrow/letter/enter/esc/Ctrl-C key handling, desired height/render semantics, provider autoselect, status helpers | `tests/test_tui_oss_selection.py::{test_ctrl_h_l_move_provider_selection_matches_rust,test_arrow_navigation_wraps_and_release_events_are_ignored,test_enter_escape_cancel_and_letter_shortcuts_select_expected_provider,test_options_and_desired_height_match_source_shape,test_status_symbol_and_color_semantics,test_select_oss_provider_autoselects_when_only_one_provider_runs,test_select_oss_provider_requires_runner_for_manual_ui_and_marks_manual_selection,test_status_helpers_map_port_probe_results}` | complete_slice | Ports OSS provider selection state, keyboard shortcuts, manual-selection completion, one-running-provider autoselect, semantic prompt/render lines, and stdlib localhost port status mapping. Real raw-mode alternate screen, crossterm event loop, ratatui cell rendering, and exact Unicode status glyph styling remain terminal/runtime boundaries. |

| codex-rs/tui/src/local_chatgpt_auth.rs | pycodex.tui.local_chatgpt_auth | tests/test_tui_local_chatgpt_auth.py | complete | Ports the test-only local ChatGPT auth loader, managed auth fixture writer, JWT-shaped helper, auth-mode/openai-api-key rejection, missing-token/account errors, forced workspace filtering, managed-auth precedence over ignored ephemeral files, id-token account fallback, and plan wire-name lowercasing. The concrete codex_login credential-store backend is treated as an external dependency boundary; Python reads the semantic managed auth.json fixture directly. |

| codex-rs/tui/src/selection_list.rs | pycodex.tui.selection_list | tests/test_tui_selection_list.py | complete | Ports selection_option_row and selection_option_row_with_dim as a semantic two-segment row model: one-based prefix text/width, selected cyan style precedence, optional dim style for unselected rows, and wrapped non-trimming label segment. Exact ratatui RowRenderable/Paragraph cell rendering is represented by Python segment/style dataclasses. |

### selection_list.rs - complete

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `selection_list.rs` `selection_option_row`, `selection_option_row_with_dim` | `pycodex.tui.selection_list`; `tests/test_tui_selection_list.py` | `complete` | Module-scoped behavior contract is covered: one-based selected/unselected prefixes, prefix display width, selected cyan style precedence over dim, dim styling for unselected rows, label segment with max-width/wrap/no-trim semantics, and a semantic two-segment model for Rust `RowRenderable`/`Paragraph`. |

| codex-rs/tui/src/skills_helpers.rs | pycodex.tui.skills_helpers | tests/test_tui_skills_helpers.py | complete | Ports the full module-owned helper contract: interface display-name precedence including Some("") preservation, plugin-qualified display formatting, unqualified/empty-split fallback, description precedence with Some("") preservation, skill-name truncation through text_formatting.truncate_text, display-name-first matching, canonical-name fallback with hidden highlight indices, equal-name fallback suppression, and mapping/duck-typed metadata adapters. Exact codex_utils_fuzzy_match score values remain a dependency-crate boundary rather than codex-tui module behavior. |

| codex-rs/tui/src/test_backend.rs | pycodex.tui.test_backend | tests/test_tui_test_backend.py | complete_slice | Ports VT100Backend as a semantic in-memory terminal backend: constructor size, display contents, write/flush, draw cell updates, cursor visibility/position, clear regions, append_lines, size/window_size with 640x480 pixels, and region scrolling. Exact crossterm/vt100 ANSI parser behavior remains a framework dependency boundary. |
| codex-rs/tui/src/test_backend.rs | clear-region semantic branches | tests/test_tui_test_backend.py::test_clear_region_all_after_and_before_cursor | complete_slice | Extends VT100Backend parity coverage for ClearType::All, AfterCursor, and BeforeCursor state changes, including cursor reset on full clear. Exact crossterm/vt100 escape parsing remains a dependency boundary. |

| codex-rs/tui/src/pager_overlay.rs | pycodex.tui.pager_overlay | tests/test_tui_pager_overlay.py | complete_slice | Ports a semantic pager overlay slice: first_or_empty, key-hint text assembly, PagerView content height/content area/page height/render-time scroll clamping, chunk visibility, bottom detection, StaticOverlay wrapping, and TranscriptOverlay live-tail cache, bottom-pinned insertion, manual-scroll preservation, and consolidation highlight remapping. Exact ratatui Buffer rendering, hyperlink marking, keymap event dispatch, snapshots, and alternate-screen behavior remain follow-up/framework boundaries. |

| codex-rs/tui/src/theme_picker.rs | pycodex.tui.theme_picker | tests/test_tui_theme_picker.py | complete_slice | Ports theme picker slice: preview row constants, diff-kind mapping, centered wide preview/inset semantics, narrow preview add/remove invariants, removed-line dim flag, ratatui-bridge Buffer rendering for wide/narrow preview renderables, subtitle width/fallback behavior, bundled/custom theme item construction with search values, half-width side preview metadata, selection-preview/cancel semantic events, and fallback selected theme behavior. Exact syntax highlighting, upstream diff style context, AppEventSender side effects, and config persistence remain framework/dependency boundaries. |

| codex-rs/tui/src/insert_history.rs | pycodex.tui.insert_history | tests/test_tui_insert_history.py | complete_slice | Ports insert-history semantic slice: wrap policy enums, standard/ZellijRaw modes, leading_whitespace_prefix, SetScrollRegion/ResetScrollRegion ANSI, ModifierDiff/style span ANSI transitions, hyperlink decoration, wide-line continuation clearing markers, URL-only terminal-wrap preservation, mixed/non-URL pre-wrap with leading prefix preservation, terminal-wrap no-prewrap behavior, and history-row accounting on a Python TerminalModel. Exact crossterm queueing, ratatui Span/Line styling, vt100 terminal scrollback, custom_terminal viewport mutation, and adaptive_wrap_line parity remain framework/dependency boundaries. |

| codex-rs/tui/src/model_catalog.rs | pycodex.tui.model_catalog | tests/test_tui_model_catalog.py | complete | Ports ModelCatalog as an immutable snapshot of ModelPreset-like values; new stores the provided models and try_list_models returns a fresh cloned list, matching Rust's Infallible Ok(Vec clone) behavior. |

| codex-rs/tui/src/session_state.rs | pycodex.tui.session_state | tests/test_tui_session_state.py | complete | Ports canonical TUI session DTOs plus ThreadSessionState.set_cwd_retargeting_implicit_runtime_workspace_root: cwd replacement, previous-cwd root detection, new cwd root insertion, preservation of other roots, and duplicate suppression. Protocol enum/model fields remain value-carried dependency objects without reinterpretation, matching the Rust module's state-holder role. |

| codex-rs/tui/src/session_resume.rs | pycodex.tui.session_resume | tests/test_tui_session_resume.py | complete | Ports the module-owned rollout resume-state parsing and resolution semantics: explicit UUID thread id handling, JSONL malformed-line skipping, empty-rollout error, session_meta fallback, latest turn_context cwd/model precedence, state-db model/cwd precedence, missing-history Continue(None), cwd normalization comparison, allow_prompt gating, and resolve_cwd_for_resume_or_fork current/session/exit prompt outcomes. Real Tui cwd prompt rendering, codex_state StateRuntime, ThreadId type, and tracing/error-stack integration remain dependency boundaries represented by async duck-typed interfaces. |

| codex-rs/tui/src/hooks_rpc.rs | pycodex.tui.hooks_rpc | tests/test_tui_hooks_rpc.py | complete | Ports the full module-owned hooks RPC helper contract: HookTrustUpdate, HooksList request construction with hooks-list UUID prefix, response coercion, cwd entry selection preserving hooks/warnings/errors with empty fallback, hook review detection for Untrusted/Modified, ConfigBatchWrite request construction for hooks.state Upsert trust hashes, single-update wrapper, and error context wrapping. Real AppServerRequestHandle, protocol enum structs, RequestId type, and ConfigWriteResponse decoding remain dependency boundaries represented by duck-typed request dictionaries. |

| codex-rs/tui/src/exec_command.rs | pycodex.tui.exec_command | tests/test_tui_exec_command.py | complete | Ports shell command helpers: shlex escape fallback, bash/zsh -lc script extraction including absolute shell paths, guarded split_command_string round-trip behavior including Windows C:\ preservation and invalid syntax fallback, and relativize_to_home behavior for absolute paths inside HOME including the empty relative path for HOME itself. |

| codex-rs/tui/src/cli.rs | pycodex.tui.cli | tests/test_tui_cli.py | complete | Ports the full module-owned TUI CLI data-shape contract: public prompt/strict/web-search/no-alt-screen fields, skipped resume/fork controls, config-overrides default, Cli/TuiSharedCliOptions deref/deref_mut/into_inner behavior, shared-option update semantics for mapping and object facades, and mark_tui_args/augment_args/augment_args_for_update adding the dangerously_bypass_approvals_and_sandbox conflict with approval_policy. Real clap Parser/Args/FromArgMatches generation and codex_utils_cli SharedCliOptions parsing remain dependency boundaries represented by lightweight mappings. |

| codex-rs/tui/src/multi_agents.rs | pycodex.tui.multi_agents | tests/test_tui_multi_agents.py | complete | Ports the module-owned multi-agent presentation contract: picker item labels/status dots, previous/next shortcut matching with platform-shaped fallbacks, spawn request summary/details, prompt/status/error truncation previews, agent labels, collab PlainHistoryCell text construction for spawn/send/wait/resume/close tool calls, in-progress no-render branches, wait completion ordering, and first-agent-state fallback. Exact ratatui Span styling, crossterm platform key event structs, ThreadItem protocol enums, HistoryCell rendering, and App-level active-thread coordination remain dependency/framework boundaries. |

| codex-rs/tui/src/app_server_session.rs | pycodex.tui.app_server_session | tests/test_tui_app_server_session.py | complete_slice | Ports the independently testable app-server session slice: JSON-RPC compatibility constants, thread/settings/update unsupported detection, bootstrap error context wrapping, ThreadParamsMode provider/cwd rules, request-id sequencing for read-account and external-agent config requests, account display plan-label remapping, API model preset projection, config request overrides, service-tier forwarding, sandbox projection, permissions selection, and thread start/resume/fork lifecycle params. Full bootstrap orchestration, concrete protocol response decoding, rate-limit snapshots, config rebuild, and app-server transport integration remain dependency/runtime boundaries. |

| `bottom_pane/mentions_v2/popup.rs` | `Popup::new/set_candidates/set_query/set_file_matches/selected/move_up/move_down/previous_search_mode/next_search_mode/calculate_required_height`, `FileSearch` pending/display/waiting/matches behavior, render_ref delegation | `tests/test_tui_bottom_pane_mentions_v2_popup.py::{test_file_search_query_state_matches_rust_pending_display_and_clear_rules,test_popup_initial_state_required_height_and_selection_navigation,test_popup_set_query_updates_file_search_and_clamps_selection,test_popup_set_candidates_replaces_rows_and_clamps_selection,test_popup_file_matches_show_only_for_matching_pending_query_and_cap_to_popup_rows,test_popup_search_mode_cycles_and_filters_rows,test_popup_render_ref_delegates_to_semantic_renderer_with_empty_messages}` | complete | Ports the popup's full local state machine: query/file-search synchronization, empty-query clearing, stale file-match rejection, MAX_POPUP_ROWS capping, candidate replacement with selection clamp/reset, selection wrap/visibility, selected row lookup, search-mode cycling, required-height constant, row filtering delegation, and semantic render_popup delegation. Exact ratatui Buffer/WidgetRef drawing is represented by the separate render module's semantic renderer. |

| `bottom_pane/title_setup.rs` | `TerminalTitleItem` canonical/legacy ids, descriptions, preview item mapping, separators, `preview_line_for_title_items`, all-or-nothing parser, configured-item ordering/dedup/unknown-id skip, title select item construction, semantic confirm/cancel/render lines | `tests/test_tui_bottom_pane_title_setup.py::{test_parse_terminal_title_items_preserves_order_matches_rust,test_parse_terminal_title_items_rejects_invalid_ids_matches_rust,test_canonical_ids_and_legacy_aliases_match_rust_tests,test_parse_accepts_all_kebab_case_variants_from_rust_test,test_preview_line_joins_non_spinner_items_with_pipe_and_omits_missing_values,test_preview_item_and_separator_rules_match_rust,test_preview_line_with_activity_uses_space_separator_around_spinner,test_title_setup_view_orders_configured_unique_items_before_disabled_remainder,test_title_select_item_uses_rate_limit_preview_names_and_descriptions,test_confirm_and_cancel_emit_semantic_events}` | complete | Ports the terminal-title setup semantic contract: persisted kebab-case IDs and legacy aliases, item descriptions/preview mapping, spinner preview omission, separator behavior, preview string construction, all-or-nothing parsing for preview/confirm, picker construction that preserves configured valid unique items first while skipping unknown ids, rate-limit preview item naming, and semantic confirm/cancel/render events. Exact MultiSelectPicker internals and ratatui Buffer rendering remain widget/renderer boundaries represented by semantic view events. |
| `bottom_pane/title_setup.rs` | `preview_line_for_title_items` action-required spinner branch delegates to `build_action_required_title_text` with `ACTION_REQUIRED_PREVIEW_PREFIX` | `tests/test_tui_bottom_pane_title_setup.py::test_preview_line_with_activity_uses_action_required_title_builder` | complete | Corrects the spinner-selected preview to omit Spinner, use `[ ! ] Action Required`, and join remaining preview values with ` | ` like Rust. |

| `bottom_pane/footer.rs` | `FooterMode`, `FooterProps`, `FooterKeyHints::default_bindings`, `toggle_shortcut_mode`, `esc_hint_mode`, `reset_mode_after_activity`, `footer_height`, quit/Esc hint lines, passive status-line precedence, mode indicator labels, context line, paste-image WSL shortcut binding, semantic single-line layout helpers | `tests/test_tui_bottom_pane_footer.py::{test_toggle_shortcut_mode_matches_rust_base_mode_rules,test_esc_and_activity_reset_modes_match_rust_state_machine,test_footer_height_uses_rendered_line_count_for_modes,test_quit_and_esc_hint_copy_follows_running_and_backtrack_flags,test_footer_from_props_prefers_status_line_but_queue_hint_yields,test_mode_indicator_and_single_line_layout_semantics,test_context_line_and_shortcut_binding_wsl_variant,test_default_key_hints_match_rust_test_bindings_shape}` | complete_slice | Ports the module's independent footer state/formatting slice with semantic strings and key bindings: mode transitions, footer-height line counting, instructional copy, passive status/agent line precedence, queue hint precedence, collaboration mode labels, context usage text, shortcut overlay entries, and WSL paste-image shortcut selection. Exact ratatui Span styling, snapshot Buffer rendering, full width fallback/collapse algorithm, IDE/right-context painting, and complete shortcut descriptor table remain renderer/widget follow-up boundaries. |

| `bottom_pane/file_search_popup.rs` | `FileSearchPopup::new/set_query/set_empty_prompt/set_matches/move_up/move_down/selected_match/calculate_required_height`, first-page result capping Rust test, semantic render row conversion | `tests/test_tui_bottom_pane_file_search_popup.py::{test_new_starts_waiting_with_empty_queries_and_visible_height_one,test_set_query_only_updates_when_pending_query_changes,test_set_empty_prompt_clears_matches_and_resets_selection,test_set_matches_keeps_only_the_first_page_of_results_matches_rust_test,test_set_matches_ignores_stale_query_results,test_move_up_down_wrap_selection_and_selected_match,test_render_ref_converts_matches_to_generic_rows_and_empty_message}` | complete_slice | Ports the file-search popup local state machine: display/pending query separation, waiting and empty prompt states, stale-result rejection, MAX_POPUP_ROWS match capping, selection clamp/wrap with selected path lookup, required-height clamping, and semantic GenericDisplayRow render conversion. Exact ratatui WidgetRef/Buffer rendering and selection_popup_common cell styling remain renderer boundaries. |
| `bottom_pane/file_search_popup.rs` | stable old matches while newer query is in-flight | `tests/test_tui_bottom_pane_file_search_popup.py::test_set_query_waiting_for_new_results_keeps_existing_matches_stable` | complete_slice | Ports the source-commented behavior that existing matches/list height remain stable after `set_query` marks a newer pending query as waiting, until matching results arrive. Concrete ratatui WidgetRef/Buffer rendering remains a renderer boundary. |
| `bottom_pane/file_search_popup.rs` | matching empty results leave visible no-matches placeholder | `tests/test_tui_bottom_pane_file_search_popup.py::test_set_matches_with_empty_results_stops_waiting_and_keeps_placeholder_height` | complete_slice | Ports the `set_matches` branch where an in-flight query returns no matches: display/pending query update, waiting becomes false, selection is cleared, required height remains one placeholder row, and render copy switches to `no matches`. |

| `bottom_pane/approval_overlay.rs` | `ApprovalRequest` matching, `ApprovalOverlay` queue/current/done state, selection/cancel/resolve routing, MCP Esc cancel override, approval option construction, footer hints, network target helpers, permission-rule formatting | `tests/test_tui_bottom_pane_approval_overlay.py::{test_request_matches_resolved_request_variants,test_overlay_selection_emits_decision_and_advances_queue_lifo_like_rust_pop,test_cancel_current_request_emits_request_specific_cancel_and_clears_queue,test_dismiss_resolved_request_removes_current_without_abort_event,test_esc_cancels_mcp_elicitation_even_with_custom_decline_overlap,test_shortcuts_trigger_selection_and_fullscreen_open,test_exec_and_permission_options_use_expected_semantic_labels,test_network_targets_and_review_decision_mapping,test_permission_rule_formatting_covers_special_and_path_entries}` | complete_slice | Ports the approval overlay's semantic routing slice: request/resolved-request correlation including MCP server_name/request_id mismatch rejection, queue advancement, explicit decision events for exec/permissions/patch/MCP, current cancellation, resolved-request dismissal without abort events, fullscreen/open-thread shortcuts, MCP Esc-to-Cancel precedence, exec/permissions/patch/elicitation option labels and shortcuts, network target extraction, review decision mapping, and permission-rule formatting. Concrete AppEventSender protocol DTOs, history-cell rendering, ListSelectionView keymap internals, ratatui snapshots, and full additional-permissions protocol coverage remain dependency/widget boundaries. |
| `bottom_pane/memories_settings_view.rs` | `pycodex.tui.bottom_pane.memories_settings_view` | `tests/test_tui_bottom_pane_memories_settings_view.py` | `complete_slice` | Ports the menu items, setting toggles, save/reset confirmation state machine, semantic rows, docs link, footer hint, key handling, and event emission boundary; ratatui layout details remain semantic. |
| `bottom_pane/hooks_browser_view.rs` | `pycodex.tui.bottom_pane.hooks_browser_view` | `tests/test_tui_bottom_pane_hooks_browser_view.py` | `complete_slice` | Ports event aggregation, review-needed selection, event/handler page transitions, unmanaged toggle events, managed/review guardrails, trust selected/all events, issue lines, footer semantics, and semantic render lines; ratatui style/snapshot fidelity remains adapted. |
| `test_support.rs` | `pycodex.tui.test_support` | `tests/test_tui_test_support.py` | `complete_slice` | Ports TUI test helper behavior for deterministic test paths, app-server wire round-tripping, `SessionSource::Cli`, and `SkillScope::{User,Repo}` helpers; upstream absolute-path dependency remains represented as a local semantic test model, not marked as dependency-crate completion. |
| `status/account.rs` | `pycodex.tui.status.account` | `tests/test_tui_status_account.py` | `complete` | Ports the full `StatusAccountDisplay` enum contract: `ChatGpt { email, plan }` optional payloads and payload-free `ApiKey`, with semantic wire conversion and error boundary for unknown variants. |
| `chatwidget/session_header.rs` | `pycodex.tui.chatwidget.session_header` | `tests/test_tui_chatwidget_session_header.py` | `complete` | Ports the full `SessionHeader` behavior: constructor stores model text and `set_model` updates only when the model value changes. |
| `chatwidget/review.rs` | `pycodex.tui.chatwidget.review` | `tests/test_tui_chatwidget_review.py` | `complete` | Ports the full `ReviewState` data contract: default recent auto-review denial store, review-mode flag, and the `Option<Option<TokenUsageInfo>>` snapshot as an explicit Python tri-state. |
| `chatwidget/warnings.rs` | `pycodex.tui.chatwidget.warnings` | `tests/test_tui_chatwidget_warnings.py` | `complete` | Ports the full warning display contract: exact fallback metadata prefix/suffix slug extraction, per-slug deduplication, and always-display behavior for unrelated warnings. |
| `chatwidget/side.rs` | `pycodex.tui.chatwidget.side` | `tests/test_tui_chatwidget_side.py` | `complete` | Ports the full side-conversation chat-surface contract: plain user-turn submission with shell escapes disallowed, active flag and placeholder switching, active-state getter, context-label forwarding, and mixin method shape for widget-like callers. |
| `chatwidget/hooks.rs` | `pycodex.tui.chatwidget.hooks` | `tests/test_tui_chatwidget_hooks.py` | `complete` | Ports the full chat-surface hooks contract: fetch request event with current cwd, stale cwd guard, success conversion through `hooks_list_entry_for_cwd`, error message formatting, hooks browser opening, redraw request, and mixin method shape. |
| `chatwidget/goal_validation.rs` | `pycodex.tui.chatwidget.goal_validation` | `tests/test_tui_chatwidget_goal_validation.py` | `complete_slice` | Ports goal objective length validation, exact limit acceptance, goal-specific oversized error formatting with separators and file hint, live composer cleanup/drain behavior, queued no-cleanup behavior, pending paste expansion boundary, and mixin method shape; full ChatComposer expansion remains an injected dependency boundary. |
| `chatwidget/exec_state.rs` | `pycodex.tui.chatwidget.exec_state` | `tests/test_tui_chatwidget_exec_state.py` | `complete` | Ports unified exec bookkeeping structs, duplicate wait-state detection, wait-streak empty display filtering/update rules, unified source detection, standard tool-call classification, and command string/action conversion through existing Python `ParsedCommand` and split helpers. |
| `onboarding/mod.rs` | `pycodex.tui.onboarding` | `tests/test_tui_onboarding_mod.py` | `complete_slice` | Ports the package-level module boundary and Rust re-exports of `auth::mark_url_hyperlink` and `auth::mark_underlined_hyperlink`; full `onboarding::auth` behavior remains separately scaffolded. |
| `public_widgets/mod.rs` | `pycodex.tui.public_widgets` | `tests/test_tui_public_widgets_mod.py` | `complete_slice` | Ports the package-level module boundary and `composer_input` submodule declaration; does not mark `public_widgets::composer_input` behavior complete. |
| `exec_cell/mod.rs` | `pycodex.tui.exec_cell` | `tests/test_tui_exec_cell_mod.py` | `complete_slice` | Ports the package-level module boundary and Rust re-exports from `model` and `render`; does not mark `exec_cell::model` or `exec_cell::render` behavior complete. |
| `status/mod.rs` | `pycodex.tui.status` | `tests/test_tui_status_mod.py` | `complete_slice` | Ports the package-level module boundary and Rust re-exports from `account`, `card`, `helpers`, and `rate_limits`; does not mark those submodule behavior contracts complete. |
| `app/test_support.rs` | `pycodex.tui.app.test_support` | `tests/test_tui_app_test_support.py` | `complete_slice` | Ports module-local test helper slice: test telemetry defaults/session source, model slug selection, effective-config app enabled lookup, and explicit `NotImplementedError` boundary for heavyweight full App fixture construction. |
| `status/helpers.rs` | `pycodex.tui.status.helpers` | `tests/test_tui_status_helpers.py` | `complete` | Ports model detail composition, agents summary path display, account display passthrough, plan label remapping, compact token formatting, directory display/truncation, reset timestamp formatting, and title-case helper behavior. |
| `status/remote_connection.rs` | `pycodex.tui.status.remote_connection` | `tests/test_tui_status_remote_connection.py` | `complete` | Ports remote connection display formatting: embedded target suppression, websocket credential/query/fragment sanitization, invalid websocket placeholder, unix socket display, version formatting, and Rust-shaped example helper. |
| `onboarding/keys.rs` | fixed onboarding key binding constants: MOVE_UP/DOWN, SELECT_FIRST/SECOND/THIRD, CONFIRM, CANCEL, QUIT, TOGGLE_ANIMATION | `tests/test_tui_onboarding_keys.py::{test_onboarding_navigation_bindings_match_rust_constants,test_onboarding_selection_bindings_match_rust_constants,test_onboarding_confirm_cancel_quit_bindings_match_rust_constants,test_onboarding_toggle_animation_includes_ctrl_shift_period}` | `complete` | Ports the Rust const key-binding arrays into Python semantic `KeyBinding` tuples, including Ctrl+C/Ctrl+D quit and Ctrl+Shift+. animation toggle behavior; crossterm concrete types remain represented by `key_hint`. |
| `status/format.rs` | `FieldFormatter::{from_labels,line,continuation,value_width,full_spans,label_span}`, `push_label`, `line_display_width`, `truncate_line_to_width` | `tests/test_tui_status_format.py::{test_field_formatter_from_labels_aligns_label_spans_like_rust,test_field_formatter_handles_wide_labels_and_continuations,test_push_label_preserves_first_seen_order,test_line_display_width_sums_span_unicode_widths,test_truncate_line_to_width_matches_rust_span_and_width_rules}` | `complete` | Ports status field alignment, dim label/continuation spans, duplicate-label suppression, Unicode display-width accounting, and styled line truncation semantics with Python `Line`/`Span` models instead of ratatui types. |
| `status/rate_limits.rs` | `RateLimitWindowDisplay`, `RateLimitSnapshotDisplay`, `CreditsSnapshotDisplay`, `compose_rate_limit_data{,_many}`, `render_status_limit_progress_bar`, `format_status_limit_summary`, credit balance formatting, Rust non-codex row tests | `tests/test_tui_status_rate_limits.py::{test_non_codex_single_limit_renders_combined_row_matches_rust,test_non_codex_multi_limit_keeps_group_row_matches_rust,test_compose_rate_limit_data_missing_unavailable_and_stale_states,test_credit_rows_and_balance_formatting_match_rust,test_window_label_helpers_and_progress_summary_match_rust_contract,test_rate_limit_snapshot_display_for_limit_converts_duck_typed_protocol_snapshot}` | `complete_slice` | Ports rate-limit snapshot display shaping, stale/missing/unavailable classification, non-codex grouping rules from Rust tests, credits rows/balance rounding, duration labels, progress bar clamping, and protocol snapshot conversion via duck-typed inputs. Exact upstream protocol classes and local-time rendering are represented semantically. |
| `status/card.rs` | `StatusHistoryHandle::finish_rate_limit_refresh`, `StatusHistoryCell` token/context/rate-limit line helpers, permission/provider/url helpers, semantic display/hyperlink lines | `tests/test_tui_status_card.py::{test_status_handle_finish_rate_limit_refresh_updates_shared_state,test_token_usage_and_context_window_spans_match_status_card_shape,test_rate_limit_lines_cover_missing_stale_and_narrow_window_rows,test_permission_label_helpers_match_rust_branches,test_model_provider_and_base_url_sanitizing_match_rust_contract,test_display_lines_include_usage_link_and_hyperlink_metadata}` | `complete_slice` | Ports the status-card local shaping slice: token/context spans, rate-limit state refresh and row messages, permission/approval/provider/base-url labels, usage-link hyperlink metadata, and semantic display lines. Full Config/protocol construction, history-cell borders, ratatui rendering, adaptive wrapping fidelity, and sandbox summary crate behavior remain dependency/framework boundaries. |
| `exec_cell/model.rs` | `CommandOutput`, `ExecCall`, `ExecCell::{new,with_added_call,complete_call,should_flush,mark_failed,is_exploring_cell,is_active,active_start_time,animations_enabled,iter_calls,append_output,is_exploring_call}` | `tests/test_tui_exec_cell_model.py::{test_exec_call_source_helpers_match_rust_variants,test_exploring_cell_accepts_only_related_non_user_read_list_search_calls,test_complete_call_matches_most_recent_call_id_and_reports_miss,test_should_flush_only_for_completed_non_exploring_cells,test_mark_failed_finishes_only_pending_calls,test_active_state_and_active_start_time_match_first_pending_call,test_append_output_rejects_empty_or_missing_and_creates_default_output}` | `complete` | Ports grouped exec-call data model semantics: exploring call grouping, reverse call_id routing, completion/miss signal, flush rules, failure marking, active timing, animation flag, iteration, and chunk append behavior. ParsedCommand and CommandExecutionSource are represented by duck-typed strings/objects at the module boundary. |
| `public_widgets/composer_input.rs` | `ComposerAction`, `ComposerInput::{new,is_empty,clear,input,handle_paste,set_hint_items,clear_hint_items,desired_height,cursor_pos,render_ref,is_in_paste_burst,flush_paste_burst_if_due,recommended_flush_delay,drain_app_events}`, `Default` | `tests/test_tui_public_widgets_composer_input.py::{test_new_default_and_empty_clear_semantics_match_public_wrapper,test_input_enter_submits_and_shift_enter_inserts_newline,test_input_backspace_and_non_text_control_keys_do_not_submit,test_handle_paste_and_flush_burst_semantics,test_hint_item_override_round_trips_stringified_pairs,test_desired_height_cursor_and_render_ref_are_semantic_boundaries,test_recommended_flush_delay_is_positive_duration_slice}` | `complete_slice` | Ports the public wrapper contract around ChatComposer with semantic text input behavior: empty/clear, Enter submit, Shift+Enter newline, paste/paste-burst state, hint override mapping, deterministic desired height/cursor/render result, flush delay, and event draining. Full internal ChatComposer paste heuristics and ratatui Buffer rendering remain dependency boundaries. |
| `exec_cell/render.rs` | `new_active_exec_command`, unified interaction summary, `OutputLines`, output ellipsis, active/exploring/command display semantic lines, transcript/raw helpers, line truncation helpers, Rust render regression tests | `tests/test_tui_exec_cell_render.py::{test_output_lines_ellipsis_includes_transcript_hint_matches_rust,test_command_truncation_ellipsis_does_not_include_transcript_hint_matches_rust,test_truncate_lines_middle_keeps_omitted_count_in_line_units_matches_rust,test_truncate_lines_middle_does_not_truncate_blank_prefixed_output_lines_matches_rust,test_active_command_without_animations_is_stable_matches_rust,test_command_display_does_not_split_long_url_token_matches_rust,test_exploring_display_does_not_split_long_url_like_search_query_matches_rust,test_output_display_does_not_split_long_url_like_token_without_scheme_matches_rust,test_desired_transcript_height_accounts_for_wrapped_url_like_rows_matches_rust,test_unified_exec_interaction_summary_and_preview_semantics,test_user_shell_output_is_limited_by_screen_lines_slice}` | `complete_slice` | Ports the independently testable exec-cell rendering semantics: active command construction, stable no-animation markers, unified interaction summaries, output head/tail truncation with transcript hints, command truncation without transcript hint, long token preservation, transcript height row accounting, and semantic display/transcript/raw line helpers. Exact ratatui styling, ANSI highlighting, bash parsing, adaptive wrapping, and Paragraph row-count fidelity remain renderer/framework boundaries. |
| `onboarding/auth.rs` | `SignInState`, `SignInOption`, `ApiKeyInputState`, `ContinueInBrowserState`, `ContinueWithDeviceCodeState`, `AuthModeWidget` state/input helpers, login notifications, step state, hyperlink helpers, Rust auth widget tests | `tests/test_tui_onboarding_auth.py::{test_device_code_state_pending_ready_and_copyable_auth,test_forced_chatgpt_disables_api_key_flow_matches_rust_tests,test_existing_chatgpt_auth_tokens_counts_as_signed_in_matches_rust,test_cancel_active_attempt_resets_browser_and_device_code_state,test_option_lists_highlight_and_shortcut_selection_respect_forced_methods,test_api_key_entry_key_and_paste_semantics,test_login_completion_and_account_updates_match_current_state_only,test_step_state_and_animation_suppression,test_hyperlink_marking_and_sanitization_semantics,test_cancel_request_and_browser_open_boundaries_are_explicit}` | `complete_slice` | Ports the onboarding auth state-machine slice: sign-in states/options, device-code readiness, forced-login filtering, highlight/shortcut routing, API-key entry/save guardrails, active-attempt cancellation, existing ChatGPT auth handling, account login/update notifications, step completion, animation suppression, and semantic OSC8 hyperlink marking. Full async app-server LoginAccount transport, real browser opening, ratatui rendering, and headless device-code submodule remain dependency/runtime boundaries. |
| `onboarding/auth/headless_chatgpt_login.rs` | `start_headless_chatgpt_login`, `render_device_code_login`, `device_code_attempt_matches`, `set_device_code_state_for_active_attempt`, `set_device_code_error_for_active_attempt`, Rust device-code tests | `tests/test_tui_onboarding_auth_headless_chatgpt_login.py::{test_device_code_attempt_matches_only_for_matching_request_id,test_set_device_code_state_for_active_attempt_updates_only_when_active,test_set_device_code_error_for_active_attempt_updates_only_when_active,test_start_headless_chatgpt_login_sets_pending_and_records_request,test_apply_device_code_response_updates_or_cancels_stale_attempt,test_apply_device_code_error_sets_pick_mode_only_for_active_attempt,test_render_device_code_login_pending_and_ready_semantics,test_render_device_code_login_suppressed_animation_does_not_schedule_frame}` | `complete_slice` | Ports the headless ChatGPT device-code login slice: pending request setup, request-id guarded ready/error state transitions, stale response cancellation signal, pending/ready render text, animation frame scheduling guard, and semantic URL hyperlink marking. Tokio app-server transport and concrete ratatui Buffer rendering remain dependency/runtime boundaries. |
| `chatwidget/rate_limits.rs` | constants, `RateLimitWarningState::take_warnings`, duration/label helpers, prompt/error enums, app-server error classification | `tests/test_tui_chatwidget_rate_limits.py::{test_constants_and_prompt_states_match_rust_values,test_limit_duration_labels_use_five_percent_tolerance,test_limit_label_falls_back_by_primary_or_secondary,test_warning_state_emits_highest_new_threshold_once_per_limit,test_warning_state_handles_secondary_then_primary_order_and_cap_suppression,test_rate_limit_error_kind_mapping_matches_app_server_variants,test_cyber_policy_detection_is_separate_from_rate_limit_errors}` | `complete` | Ports chatwidget rate-limit local behavior: warning thresholds with one-shot index advancement, cap suppression, primary/secondary ordering, duration label tolerance, fallback labels, switch prompt states, and app-server rate-limit/cyber-policy error classification. Full ChatWidget prompt UI and model switching orchestration remain outside this module boundary. |
| `bottom_pane/bottom_pane_view.rs` | `ViewCompletion`, `BottomPaneView` trait defaults for key handling, completion, child-dismiss marker, view identity, cancellation, paste burst, request consumption, resolved request dismissal, terminal action title, next-frame delay | `tests/test_tui_bottom_pane_bottom_pane_view.py::{test_view_completion_enum_matches_rust_variants,test_default_bottom_pane_view_completion_and_identity_methods,test_default_bottom_pane_view_input_and_paste_methods_are_noops,test_default_request_consumers_return_original_request,test_default_external_refresh_and_terminal_title_methods,test_override_methods_can_express_view_specific_behavior}` | `complete` | Ports the bottom-pane view trait boundary as a Python Protocol plus default mixin: no-op key handling, non-complete/no-completion defaults, no child dismissal, no view identity/selection/tab, Ctrl-C not handled, paste/burst hooks false, request consumers return the original request, resolved-request dismissal false, no terminal action requirement, and no delayed frame. Concrete view implementations remain separate modules. |
| `markdown_stream.rs` | `MarkdownStreamCollector::commit_complete_source`, `finalize_and_drain_source`, `clear`, source-boundary stream simulation | `pycodex.tui.markdown_stream.MarkdownStreamCollector`, `tests/test_tui_markdown_stream.py` | `complete_slice` | Source chunk state machine ported; full Rust markdown-to-ratatui rendering tests remain behind the markdown renderer dependency boundary. |
| `markdown_stream.rs` | `MarkdownStreamCollector::commit_complete_source` resumes from prior committed source boundary | `tests/test_tui_markdown_stream.py::test_commit_complete_source_resumes_from_previous_boundary_when_tail_completes` | `complete_slice` | Covers the Rust `committed_source_len` behavior where an incomplete tail remains buffered and is emitted only after a later newline completes it. |
| `chatwidget/goal_status.rs` | `GoalStatusState::{new,is_active,indicator}`, `goal_status_indicator_from_app_goal`, `active_goal_usage`, `stopped_goal_budget_usage`, `completed_goal_usage`, Rust goal status tests | `tests/test_tui_chatwidget_goal_status.py` | `complete` | Ports compact footer goal-status indicator mapping, budget/time usage formatting, duck-typed protocol status normalization, and active-turn elapsed-time accounting. |
| `chatwidget/goal_menu.rs` | `goal_summary_lines`, `goal_status_label`, `edited_goal_status`, bare `/goal` command summary behavior | `tests/test_tui_chatwidget_goal_menu.py` | `complete` | Ports goal summary text rows, status labels, command hint selection, token budget row inclusion, and edit-status transition rules; ChatWidget prompt/selection runtime remains caller boundary. |
| `chatwidget/connectors.rs` | `ConnectorsCacheState`, `ConnectorsState`, refresh gating, mention snapshot lookup, connector labels/descriptions, popup params, loaded/error/update-enabled transitions | `tests/test_tui_chatwidget_connectors.py` | `complete_slice` | Ports connector cache and semantic selection data behavior; concrete ChatWidget AppEvent dispatch, browser open actions, bottom-pane replacement, and redraw wiring remain runtime boundaries. |
| `chatwidget/command_lifecycle.rs` | unified exec process begin/end tracking, footer sync data, recent output chunk retention, terminal wait streak flush/replace semantics | `tests/test_tui_chatwidget_command_lifecycle.py` | `complete_slice` | Ports independent unified-exec lifecycle state; full ChatWidget ExecCell grouping, transcript insertion, AppEvent dispatch, status indicator updates, and redraw behavior remain runtime boundaries. |
| `chatwidget/input_queue.rs` | `PendingInputPreview`, `InputQueueState::{has_queued_follow_up_messages,clear,preview}`, Rust `preview_keeps_queue_categories_separate`, `clear_resets_all_input_queues` | `tests/test_tui_chatwidget_input_queue.py` | `complete` | Ports queue state, preview category separation, history-record fallback/override behavior, follow-up detection, and clear reset semantics; full `user_messages.rs` rendering remains a neighboring module boundary. |
| `chatwidget/interrupts.rs` | `QueuedInterrupt`, `InterruptManager::{new,is_empty,push_*,remove_resolved_prompt,flush_all}`, Rust resolved prompt removal tests | `tests/test_tui_chatwidget_interrupts.py` | `complete` | Ports FIFO interrupt queueing, variant-specific resolved prompt matching, lifecycle-event retention, approval-id fallback, and duck-typed ChatWidget flush dispatch. |
| `chatwidget/hook_lifecycle.rs` | `on_hook_started`, `on_hook_completed`, `flush_completed_hook_output`, `finish_active_hook_cell_if_idle`, `update_due_hook_visibility`, `schedule_hook_timer_if_needed` semantic lifecycle slice | `tests/test_tui_chatwidget_hook_lifecycle.py` | `complete_slice` | Ports hook lifecycle reducer semantics with a Python semantic hook cell; concrete `history_cell::HookCell` rendering, AppEvent insertion transport, and frame requester side effects remain neighboring runtime boundaries. |
| `chatwidget/ide_context.rs` | `IdeContextState`, `/ide` command toggling/args, `maybe_apply_ide_context`, status messages, warning suppression, status indicator sync | `tests/test_tui_chatwidget_ide_context.py` | `complete_slice` | Ports chat-widget IDE context state and command/prompt-injection routing with injected fetch/apply dependencies; lower-level `ide_context.rs` fetch/context serialization remains a separate module boundary. |
| `chatwidget/reasoning_shortcuts.rs` | `ReasoningShortcutDirection`, `reasoning_choices`, `next_reasoning_effort`, `effort_rank`, Rust reasoning shortcut tests | `tests/test_tui_chatwidget_reasoning_shortcuts.py` | `complete` | Ports reasoning effort ordering, supported-choice filtering, nearest-supported movement, clamp/no-op behavior, boundary messages, and semantic shortcut handling guardrails. |
| `chatwidget/keymap_picker.rs` | `open_keymap_picker`, action/capture/debug/replace menus, `return_to_keymap_picker`, `keymap_action_filter`, `apply_keymap_update` semantic integration slice | `tests/test_tui_chatwidget_keymap_picker.py` | `complete_slice` | Ports ChatWidget-owned keymap picker routing, invalid-config error surface, submenu/view opening, return-to-picker replace/fallback behavior, and atomic live keymap cache updates; concrete `RuntimeKeymap`, key capture, and `keymap_setup` editing models remain dependency boundaries. |

### codex-tui `token_usage.rs` - complete
- Python module: `pycodex.tui.token_usage`
- Tests: `tests/test_tui_token_usage.py`
- Notes: Ports the full token-usage data/formatting contract: cached and non-cached input accounting, negative-value clamping where Rust clamps, raw output display where Rust does not clamp, blended total formatting with separators, optional cached/reasoning suffixes, context-window remaining percentage with 12k baseline and Rust-style rounding, and default info containers.

### codex-tui `motion.rs` - complete_slice
- Python module: `pycodex.tui.motion`
- Tests: `tests/test_tui_motion.py`
- Notes: Ports the motion module's independent semantics: animation/reduced mode selection, explicit reduced-motion activity fallback, reduced shimmer as plain text, semantic animated indicator/shimmer spans, recursive Rust source scanning, comment stripping, and animation primitive allowlist checks. Exact `supports_color` truecolor shimmer rendering and ratatui span styling remain framework/runtime boundaries.

### codex-tui `shimmer.rs` - complete_slice
- Python module: `pycodex.tui.shimmer`
- Tests: `tests/test_tui_shimmer.py`
- Notes: Ports shimmer span generation semantics: empty text returns empty, one span per character, process-start elapsed sweep with padding/period, cosine band intensity, fallback dim/plain/bold thresholds, and truecolor RGB blend represented as semantic bold RGB style. Real `supports_color` terminal probing and ratatui `Style`/`Color` objects remain framework boundaries.

### codex-tui `permission_compat.rs` - complete_slice
- Python module: `pycodex.tui.permission_compat`
- Tests: `tests/test_tui_permission_compat.py`
- Notes: Ports the compatibility projection behavior: profiles that already bridge to legacy sandbox policy are preserved, unbridgeable managed profiles are rebuilt as workspace-write while preserving extra writable roots and network policy, and cwd is not duplicated in explicit writable roots. TMPDIR and `/tmp` exclusion flags are delegated to the Python protocol permission model, matching the Rust dependency boundary.

### codex-tui `service_tier_resolution.rs` - complete_slice
- Python module: `pycodex.tui.service_tier_resolution`
- Tests: `tests/test_tui_service_tier_resolution.py`
- Notes: Ports service-tier resolution semantics: configured tier precedence, fast-default opt-out fallback, FastMode disabled no-op, unknown-model configured passthrough, default sentinel preservation, unsupported configured/default tier suppression, supported model default selection, core update fallback to default sentinel for known models, and model tier support lookup. Python represents Rust `Option<Option<String>>` core update as `None` for no update or a string payload for `Some(Some(value))`.

### codex-tui `table_detect.rs` - complete
- Python module: `pycodex.tui.table_detect`
- Tests: `tests/test_tui_table_detect.py`
- Notes: Ports the full table/fence detection contract: pipe segment parsing with escaped pipe preservation, header/delimiter detection, delimiter segment validation, fence marker parsing, markdown info detection, blockquote stripping, indentation ignore rules, backtick/tilde open-close tracking, mismatched/short/trailing-content close rejection, and outside/markdown/other fence states. No ratatui/crossterm framework types are involved.

### codex-tui `resize_reflow_cap.rs` - complete_slice
- Python module: `pycodex.tui.resize_reflow_cap`
- Tests: `tests/test_tui_resize_reflow_cap.py`
- Notes: Ports resize reflow row-cap resolution: terminal default caps for VS Code, Windows Terminal, WezTerm, Alacritty, fallback terminals, VS Code environment probe precedence, explicit limit override, disabled unlimited rows, unknown terminal fallback under multiplexers, and scalar config compatibility. Real terminal detection and VS Code environment probing are injected runtime boundaries.

### `bottom_pane/mentions_v2/candidate.rs` - complete_slice

| Rust behavior/test | Python parity target | Status | Notes |
| --- | --- | --- | --- |
| `TAG_WIDTH` shared tag padding width | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_tag_width_matches_plugin_label_width` | complete | Ports the `"Plugin".len()` width constant used for aligned mention tags. |
| `MentionType::is_filesystem` | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_mention_type_is_filesystem_matches_rust` | complete | Ports File/Directory filesystem classification and Plugin/Skill rejection. |
| `MentionType::label` and padded `span` content | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_mention_type_labels_and_padded_spans_match_rust_visible_tags` | complete_slice | Preserves visible labels and left-padded tag width as semantic text instead of ratatui `Span`. |
| `MentionType::span` style choice | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_mention_type_span_applies_semantic_styles` | complete_slice | Maps Rust magenta/dim/cyan/base style choices to semantic style tokens. |
| `Selection` variants | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_selection_file_and_tool_variants_preserve_fields` | complete | Ports File path and Tool insert-text/path variant field shape. |
| `Candidate::to_result` cloning and score/match propagation | `tests/test_tui_bottom_pane_mentions_v2_candidate.py::test_candidate_to_result_clones_candidate_fields_and_match_indices` | complete | Ports cloned display/description/type/selection plus copied match indices and score. |

### `bottom_pane/textarea/vim.rs` - complete_slice

| Rust behavior/test | Python parity target | Status | Notes |
| --- | --- | --- | --- |
| Vim enum/state variant shapes | `tests/test_tui_bottom_pane_textarea_vim.py::test_vim_enum_variants_match_rust_module_boundary` | complete | Ports VimMode, VimOperator, VimPending, VimMotion, VimTextObjectScope, and VimTextObject semantic variant shapes. |
| `idx_range` quote-inclusive helper | `tests/test_tui_bottom_pane_textarea_vim.py::test_idx_range_extends_to_quote_width` | complete | Ports quote range end calculation. |
| `split_word_pieces` separator splitting dependency used by small-word objects | `tests/test_tui_bottom_pane_textarea_vim.py::test_split_word_pieces_splits_separator_runs` | complete_slice | Mirrors separator-run splitting needed by this module without porting the whole parent textarea module. |
| word and big-word text object ranges | `tests/test_tui_bottom_pane_textarea_vim.py::{test_word_text_object_inner_and_around_small_word,test_big_word_uses_non_whitespace_run_and_cursor_at_end,test_word_around_prefers_preceding_whitespace_when_no_following_whitespace}` | complete_slice | Ports inner/around word range, cursor-at-end behavior, and following/preceding whitespace expansion using byte-range semantics. |
| paired text object ranges and element exclusion | `tests/test_tui_bottom_pane_textarea_vim.py::test_paired_text_object_picks_smallest_pair_and_skips_elements` | complete_slice | Ports smallest enclosing pair selection and skip-inside-element behavior with semantic TextElement ranges. |
| quoted text object ranges | `tests/test_tui_bottom_pane_textarea_vim.py::test_quoted_text_object_respects_current_line_and_escapes` | complete_slice | Ports current-line quote matching, inner/around quote ranges, and escaped-quote rejection. |

### `bottom_pane/mentions_v2/mod.rs` - complete

| Rust behavior/test | Python parity target | Status | Notes |
| --- | --- | --- | --- |
| parent module declarations and public re-exports | `tests/test_tui_bottom_pane_mentions_v2_mod.py::test_mentions_v2_parent_module_reexports_rust_public_items` | complete | Ports `MentionV2Selection`, `MentionV2Popup`, and `build_search_catalog` package-level exports while leaving submodule behavior contracts owned by their matching modules. |

### `bottom_pane/request_user_input/mod.rs` - complete_slice

| Rust behavior/test | Python parity target | Status | Notes |
| --- | --- | --- | --- |
| constants and `Focus` variants | `tests/test_tui_bottom_pane_request_user_input_mod.py::test_constants_and_focus_variants_match_rust_visible_copy` | complete_slice | Ports visible placeholders, footer separator, other-option label, and focus enum names. |
| `ComposerDraft::text_with_pending` semantic expansion | `tests/test_tui_bottom_pane_request_user_input_mod.py::test_composer_draft_text_with_pending_expands_placeholders` | complete_slice | Models pending paste marker expansion without pulling in full `ChatComposer` text-element implementation. |
| option detection, digit mapping, other option label | `tests/test_tui_bottom_pane_request_user_input_mod.py::test_overlay_option_detection_digit_mapping_and_other_option` | complete_slice | Ports local option count/index behavior and synthetic other option label. |
| notes visibility and focus availability | `tests/test_tui_bottom_pane_request_user_input_mod.py::test_notes_visibility_and_focus_for_freeform_and_option_questions` | complete_slice | Ports freeform notes focus and option-question notes visibility guards. |
| wrapped question text | `tests/test_tui_bottom_pane_request_user_input_mod.py::test_wrapped_question_lines_are_width_bounded` | complete_slice | Uses Python textwrap as semantic equivalent for width-bounded question lines. |
| `FooterTip` constructors and wrapping | `tests/test_tui_bottom_pane_request_user_input_mod.py::{test_footer_tip_constructors_and_wrapping_do_not_split_tips,test_footer_required_height_counts_wrapped_tip_lines}` | complete_slice | Ports highlighted/plain tips, separator-aware wrapping, and footer height line count. |
| full overlay key handling, queueing, submission, paste burst, app-server request dismissal, snapshots | N/A | blocked | Requires broader `ChatComposer`, app-event, concrete protocol DTO, and ratatui render integration; not silently fabricated in this slice. |

### `bottom_pane/chat_composer.rs` - complete_slice

| Rust behavior/test | Python parity target | Status | Notes |
| --- | --- | --- | --- |
| large paste/input-size constants and too-large message | `tests/test_tui_bottom_pane_chat_composer.py::test_chat_composer_constants_and_large_input_message_match_rust_copy` | complete_slice | Ports `LARGE_PASTE_CHAR_THRESHOLD`, footer spacing height, and user-visible maximum-input error copy. |
| `QueuedInputAction` variants | `tests/test_tui_bottom_pane_chat_composer.py::test_queued_input_action_variants_match_rust` | complete | Ports Plain/ParseSlash/RunShell semantic variants. |
| `InputResult` payload shape | `tests/test_tui_bottom_pane_chat_composer.py::test_input_result_variants_preserve_payload_shapes` | complete_slice | Ports Submitted, Queued, Command, ServiceTierCommand, CommandWithArgs, and None payload structure as semantic dataclasses. |
| `ChatComposerConfig::default` and `plain_text` | `tests/test_tui_bottom_pane_chat_composer.py::test_chat_composer_config_default_and_plain_text_match_rust_flags` | complete | Ports default feature flags and plain-text preset used by embedded composer surfaces. |
| `ComposerDraftSnapshot` field shape | `tests/test_tui_bottom_pane_chat_composer.py::test_composer_draft_snapshot_preserves_attachment_and_pending_fields` | complete_slice | Ports visible snapshot DTO fields for text, elements, attachments, mentions, and pending paste markers. |
| plan-mode nudge visible copy | `tests/test_tui_bottom_pane_chat_composer.py::test_plan_mode_nudge_line_keeps_visible_actions` | complete_slice | Captures semantic action copy without ratatui span styling. |
| full ChatComposer editor/popup/history/submission/paste-burst/render state machine | N/A | blocked | Large parent module depends on TextArea, popups, history, AppEventSender, paste burst, slash-command dispatch, attachments, frame requester, and ratatui rendering; those are not silently fabricated in this initial slice. |
### diff_render.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/diff_render.rs`

Python module: `pycodex/tui/diff_render.py`

Python tests: `tests/test_tui_diff_render.py`

Status: `complete_slice`

Behavior mapped:

- Diff color-level and rich-color-level semantic models are represented with Python enums.
- Rust theme fallback background constants are mirrored for truecolor and ANSI-256 modes.
- ANSI-16 intentionally carries no semantic background color, matching the low-color fallback boundary.
- Scope-provided inserted/deleted backgrounds override fallback backgrounds only for rich color levels.
- Windows Terminal / `WT_SESSION` ANSI-16 promotion is modeled without probing the real terminal.
- Diff line/gutter styles are represented as dependency-light semantic `Style` objects rather than ratatui styles.
- Path language detection, line-number width, display width, and styled span wrapping are covered by parity tests.

Not in this slice:

- Full `FileChange` to ratatui buffer rendering.
- `diffy` patch parsing/rendering integration.
- Syntect/highlight integration and theme-scope extraction beyond injected semantic backgrounds.
- Snapshot parity against ratatui `TestBackend`.

Boundary status:

- Remaining renderer stack is `blocked` on shared Python ratatui-style buffer/render models and syntax-highlighting integration.
### history_cell/base.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/base.rs`

Python module: `pycodex/tui/history_cell/base.py`

Python tests: `tests/test_tui_history_cell_base.py`

Status: `complete_slice`

Behavior mapped:

- `PlainHistoryCell::new`, `display_lines`, and `raw_lines` are represented with semantic `Line` values.
- `WebHyperlinkHistoryCell` preserves display lines while `display_hyperlink_lines` and `transcript_hyperlink_lines` delegate to web URL annotation.
- `PrefixedWrappedHistoryCell` returns no lines at width zero and applies initial/subsequent prefixes during wrapping.
- `CompositeHistoryCell` concatenates non-empty child cells and inserts one blank separator line between non-empty parts for display, hyperlink display, transcript hyperlink, and raw output.
- `raw_lines` strips span styling while preserving visible text, matching the Rust `plain_lines` boundary.

Not in this slice:

- Exact ratatui wrapping parity from upstream `adaptive_wrap_lines` for every Unicode/indent edge case.
- Renderer-level styling and buffer snapshots owned by downstream history-cell modules.

Boundary status:

- Marked `complete_slice`; exact Rust renderer wrapping can be tightened later if a shared wrapping golden suite is introduced.
### history_cell/separators.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/separators.rs`

Python module: `pycodex/tui/history_cell/separators.py`

Python tests: `tests/test_tui_history_cell_separators.py`

Status: `complete_slice`

Behavior mapped:

- `FinalMessageSeparator::new` stores optional elapsed seconds and optional runtime metrics summary.
- `display_lines` emits a dim visual divider when no labels are present.
- `raw_lines` returns no line for purely visual separators.
- Elapsed labels are hidden at 60 seconds or below and shown after one minute with `fmt_elapsed_compact`.
- Runtime metrics labels mirror Rust ordering and wording for local tools, inference, websocket sends, streams, websocket receives, Responses API overhead/inference, TTFT, and TBT.
- Duration formatting and pluralization mirror the Rust helper functions.
- Display labels are width-truncated semantically before filling the divider suffix.

Not in this slice:

- Exact ratatui style serialization; Python records dim style as semantic span style.

Boundary status:

- Marked `complete_slice`; renderer-level style snapshots remain owned by the shared TUI rendering layer.
### history_cell/notices.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/notices.rs`

Python module: `pycodex/tui/history_cell/notices.py`

Python tests: `tests/test_tui_history_cell_notices.py`

Status: `complete_slice`

Behavior mapped:

- `UpdateAvailableHistoryCell` raw transcript lines mirror update title, version transition, command/repository installation instruction, release notes label, and release notes URL.
- Display hyperlink lines for update and cyber policy notices delegate to web URL annotation.
- `new_warning_event` returns a prefixed wrapped history cell with warning prefix semantics.
- `CyberPolicyNoticeCell` exposes display/raw/hyperlink/transcript hyperlink behavior and preserves the Trusted Access for Cyber URL.
- `DeprecationNoticeCell` preserves summary, optional details, and raw detail line splitting.
- `new_info_event` and `new_error_event` return plain cells with visible notice prefixes.

Not in this slice:

- Exact ratatui macro styling, emoji glyphs, and border cell snapshots.
- Full parity for upstream Unicode glyph rendering where source checkout text is encoding-damaged.

Boundary status:

- Marked `complete_slice`; renderer glyph/styling exactness remains a shared TUI rendering concern.
### history_cell/messages.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/messages.rs`

Python module: `pycodex/tui/history_cell/messages.py`

Python tests: `tests/test_tui_history_cell_messages.py`

Status: `complete_slice`

Behavior mapped:

- `UserHistoryCell` stores message text, text elements, local image paths, and remote image URLs.
- User message text elements are sorted by byte range and interleaved into styled spans while invalid UTF-8 byte boundaries are skipped.
- User display lines trim trailing blank message lines while preserving the outer blank separator behavior covered by Rust tests.
- User raw lines trim trailing CR/LF and append remote image labels separated by one blank line.
- `local_image_label_text` mirrors the protocol helper format `[Image #N]` as an interface constraint.
- `ReasoningSummaryCell` and `new_reasoning_summary_block` implement the Rust header-detection split and transcript-only fallback.
- `AgentMessageCell`, `AgentMarkdownCell`, and `StreamingAgentTailCell` preserve raw lines, visible prefixing, hyperlink-line forwarding, and stream-continuation status.

Not in this slice:

- Exact `append_markdown` / `render_markdown_agent_with_links_and_cwd` rendering.
- Exact `adaptive_wrap_hyperlink_lines` remapping for every hyperlink column across wrapped lines.
- Table holdback and streaming-controller width behavior, owned by streaming modules.

Boundary status:

- Marked `complete_slice`; full markdown/hyperlink reflow remains blocked on shared markdown renderer and hyperlink wrapping parity.
### history_cell/plans.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/plans.rs`

Python module: `pycodex/tui/history_cell/plans.py`

Python tests: `tests/test_tui_history_cell_plans.py`

Status: `complete_slice`

Behavior mapped:

- `StreamingPlanTailCell` and `ProposedPlanStreamCell` are display-fragment passthrough cells with raw-line plainification and stream-continuation status.
- `ProposedPlanCell` stores raw markdown and cwd, emits a proposed-plan header, empty fallback, body prefixing, hyperlink annotation, and raw source lines.
- `new_proposed_plan`, `new_proposed_plan_stream`, and `new_plan_update` construct the matching semantic cell types.
- `PlanUpdateCell` raw lines preserve `Updated Plan`, trimmed explanation, Rust-debug status labels, and `(no steps provided)` fallback.
- `StepStatus`, `PlanItemArg`, and `UpdatePlanArgs` provide protocol-like Python semantic models for the Rust arguments.

Not in this slice:

- Exact markdown agent rendering with cwd-aware local file links.
- Exact ratatui checkbox glyphs and plan background styling.
- Full hyperlink adaptive-wrap remapping for plan markdown.

Boundary status:

- Marked `complete_slice`; full renderer/style parity remains blocked on shared markdown and TUI render models.
### history_cell/approvals.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/approvals.rs`

Python module: `pycodex/tui/history_cell/approvals.py`

Python tests: `tests/test_tui_history_cell_approvals.py`

Status: `complete_slice`

Behavior mapped:

- Command snippets strip the common `bash -lc` wrapper, truncate after the first newline with an ellipsis marker, and suppress empty snippets.
- `ApprovalDecisionActor` subject wording matches user vs auto-reviewer branches.
- Command and network approval decisions cover approved, approved-for-session, denied, timed-out, abort, exec-policy amendment, and network-policy amendment cases.
- Guardian patch/action helper cells render denied, approved, and timed-out summaries with singular file vs file-count wording.
- Review status lines are represented as a plain cyan history cell.

Not in this slice:

- Exact upstream `strip_bash_lc_and_escape` shell escaping for every platform-specific command vector.
- Exact ratatui glyph/color styling; Python uses semantic `OK`/`NO` prefixes because this checkout's Rust glyphs are encoding-damaged.
- Full `codex_protocol` approval model; lightweight Python dataclasses/dict coercion model only the interface needed by this module.

Boundary status:

- Marked `complete_slice`; exact protocol type integration can be tightened when the Python protocol layer exposes these approval structs.
### history_cell/patches.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/patches.rs`

Python module: `pycodex/tui/history_cell/patches.py`

Python tests: `tests/test_tui_history_cell_patches.py`

Status: `complete_slice`

Behavior mapped:

- `PatchHistoryCell` stores file changes and cwd and renders deterministic file-level summary lines for display and raw transcript output.
- `new_patch_event` constructs the patch history cell.
- `new_patch_apply_failure` emits a failure title and includes stderr output through the existing Python exec output-line semantic model.
- `new_view_image_tool_call` renders a viewed-image title plus cwd-relative path.
- `new_image_generation_call` renders generated-image title, revised prompt or call id fallback, and optional saved-path file URL.

Not in this slice:

- Full Rust `diff_render::create_diff_summary` parity, including detailed hunks and exact wrapping.
- Exact ratatui glyph/color styling; Python uses stable semantic ASCII markers due encoding-damaged glyphs in the local Rust checkout.

Boundary status:

- Marked `complete_slice`; full diff summary rendering remains owned by `diff_render.rs` follow-up.
### history_cell/session.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/session.rs`

Python module: `pycodex/tui/history_cell/session.py`

Python tests: `tests/test_tui_history_cell_session.py`

Status: `complete_slice`

Behavior mapped:

- `card_inner_width` mirrors the Rust minimum-width and max-inner-width boundary.
- `with_border`, `with_border_with_inner_width`, and internal border padding centralize card border math in Python semantic lines.
- `padded_emoji` appends the Rust hair-space separator.
- `TooltipHistoryCell` displays a prefixed tip and emits raw `Tip: ...` transcript text.
- `SessionHeaderHistoryCell` models version, model, reasoning label, fast status, directory formatting/truncation, YOLO mode, display lines, and raw lines.
- `has_yolo_permissions` and `is_yolo_mode` support dict/attribute-shaped config objects.
- `new_session_info` composes the header with first-event help, later tooltip override, and model-changed notice.

Not in this slice:

- Exact ratatui box-drawing glyphs and style spans; Python uses stable ASCII semantic borders because this checkout's Rust glyphs are encoding-damaged.
- Real tooltip catalog lookup; callers may pass `tooltip_override`, while catalog selection remains owned by `tooltips.rs`.
- Full Rust `Config` / `ThreadSessionState` types; Python accepts dict/attribute facades.

Boundary status:

- Marked `complete_slice`; exact style/glyph rendering and tooltip catalog integration remain follow-up boundaries.
### history_cell/search.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/search.rs`

Python module: `pycodex/tui/history_cell/search.py`

Python tests: `tests/test_tui_history_cell_search.py`

Status: `complete_slice`

Behavior mapped:

- `web_search_header` returns active vs completed labels.
- `web_search_action_detail` mirrors search query fallback, multi-query ellipsis, open-page URL, find-in-page pattern/url combinations, and other/empty action behavior.
- `web_search_detail` falls back to the request query when the action detail is empty.
- `WebSearchCell` stores call id, query, action, completion state, and animation flag; `update` and `complete` mutate the same fields as Rust.
- Active and completed constructor helpers create the corresponding cell states.
- Display/raw lines use the same header/detail composition, with Python using a stable semantic bullet for the animated activity indicator boundary.

Not in this slice:

- Exact animated activity indicator timing and reduced-motion behavior.
- Exact ratatui style/glyph output; Python keeps semantic line content stable.

Boundary status:

- Marked `complete_slice`; animation rendering remains owned by motion/status indicator modules.
### history_cell/hook_cell.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/hook_cell.rs`

Python module: `pycodex/tui/history_cell/hook_cell.py`

Python tests: `tests/test_tui_history_cell_hook_cell.py`

Status: `complete_slice`

Behavior mapped:

- Hook run lifecycle states are represented as pending reveal, visible running, quiet linger, and completed.
- Reveal delay and quiet-success minimum visible duration are modeled as deterministic second values.
- Duplicate begin events refresh an existing run by id.
- Quiet successes disappear if never visible, linger briefly if visible, and do not persist to history.
- Failed/blocked/stopped/completed-with-output runs persist and can be extracted via `take_completed_persistent_runs`.
- Adjacent visible running hooks with the same event/status are grouped into one display row.
- Completed hook output prefixes and event labels mirror the Rust match arms.
- Transcript animation tick is active only for visible running hooks when animations are enabled.

Not in this slice:

- Exact ratatui `Renderable` buffer drawing.
- Exact motion shimmer/spinner glyph rendering; Python uses stable semantic text.
- Full app-server protocol structs; Python dataclasses/dict coercion model the local interface contract.

Boundary status:

- Marked `complete_slice`; exact animation/rendering remains owned by motion/render modules.
### history_cell/request_user_input.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/request_user_input.rs`

Python module: `pycodex/tui/history_cell/request_user_input.py`

Python tests: `tests/test_tui_history_cell_request_user_input.py`

Status: `complete_slice`

Behavior mapped:

- `RequestUserInputResultCell` stores questions, answers, and interrupted state.
- Display/raw headers count answered questions as questions with non-empty answer lists.
- Unanswered questions are marked in display and raw transcript output.
- Secret answers are masked with `******`.
- `split_request_user_input_answer` separates option labels from `user_note: ...` entries, keeping the last note.
- Notes render as `note:` when the question has options and as `answer:` for freeform questions.
- Interrupted display output includes an unanswered-count summary only when unanswered questions remain.

Not in this slice:

- Exact ratatui glyph/style rendering; Python uses stable semantic ASCII prefixes.
- Full protocol schema integration; Python uses lightweight question/answer dataclasses and dict coercion.

Boundary status:

- Marked `complete_slice`; renderer glyph/style parity remains a renderer-layer follow-up.
### history_cell/mcp.rs - complete_slice

Rust module: `codex/codex-rs/tui/src/history_cell/mcp.rs`

Python module: `pycodex/tui/history_cell/mcp.py`

Python tests: `tests/test_tui_history_cell_mcp.py`

Status: `complete_slice`

Behavior mapped:

- MCP auth status labels mirror Rust copy.
- `McpInvocation` formatting uses `server.tool(compact_json_args)`.
- `McpToolCallCell` models active/completed/error states, success detection, failed interruption, display/raw lines, and transcript animation ticks.
- MCP content block rendering covers text, image, audio, embedded resource, resource link, and unknown JSON fallback.
- Image-output affordance detects the first base64/data-url PNG/JPEG/GIF-like image block and returns one extra history cell.
- Empty `/mcp` output and status-based inventory output are rendered with sorted servers/tools and optional resources/templates.
- MCP inventory loading cell renders stable loading text and animation ticks only when enabled.

Not in this slice:

- Real MCP runtime/inventory RPC behavior.
- Full image decoding via the Rust `image` crate; Python detects valid base64 plus common image magic bytes without third-party dependencies.
- Exact ratatui glyph/style rendering and motion spinner output.
- In-process `Config` transport formatting parity for every MCP server config shape.

Boundary status:

- Marked `complete_slice`; runtime MCP integration and exact renderer styling remain follow-up boundaries.
### history_cell/exec.rs - complete_slice

| Rust module/test | Python parity | Status | Notes |
| --- | --- | --- | --- |
| `history_cell/exec.rs` `UnifiedExecInteractionCell::{display_lines,raw_lines}` and `new_unified_exec_interaction`; Rust tests `unified_exec_interaction_cell_renders_input`, `unified_exec_interaction_cell_renders_wait` | `tests/test_tui_history_cell_exec.py::{test_unified_exec_interaction_cell_renders_input_like_rust_transcript,test_unified_exec_interaction_cell_renders_wait_like_rust_transcript}` | `complete_slice` | Ports waited-vs-interacted state, optional command display, stdin raw transcript extraction, width-zero empty rendering, first-stdin-line marker plus subsequent continuation indent, and semantic wrapped display prefixes. Uses semantic Unicode prefixes instead of ratatui styled spans. |
| `history_cell/exec.rs` `UnifiedExecProcessDetails`, `UnifiedExecProcessesCell::{display_lines,raw_lines,desired_height}`, `new_unified_exec_processes_output`; Rust test `ps_output_empty_snapshot` plus source truncation contract | `tests/test_tui_history_cell_exec.py::{test_unified_exec_processes_output_empty_matches_ps_summary_shape,test_unified_exec_processes_truncates_commands_chunks_and_remaining_count,test_unified_exec_processes_tiny_width_keeps_prefix_only}` | `complete_slice` | Ports `/ps` composite output, empty-process message, 16-process cap, first-line/80-grapheme command snippet truncation, recent-chunk truncation, remaining-count line, tiny-width prefix-only behavior, and raw plain-line conversion. Exact ratatui colors/styles and adaptive-width glyph metrics remain semantic boundaries. |
| codex-rs/tui/src/pager_overlay.rs | transcript live-tail cache invalidation/removal | tests/test_tui_pager_overlay.py::test_transcript_overlay_sync_live_tail_rebuilds_on_key_change_and_clears_on_none | complete_slice | Extends transcript overlay live-tail parity: changed cache keys rebuild the tail, identical keys remain cached, and `None` keys remove cached tail/renderable state. Concrete hyperlink buffer marking and ratatui rendering remain framework boundaries. |
### codex-tui `terminal_hyperlinks.rs` - complete_slice update
- Rust behavior/test: `terminal_hyperlinks.rs::tests::buffer_hyperlinks_follow_word_wrapping`
- Python coverage: `tests/test_tui_terminal_hyperlinks.py::test_mark_buffer_hyperlinks_follow_word_wrapping`
- Status: `complete_slice`
- Notes: Added semantic wrapped-line buffer marking parity: `mark_buffer_hyperlinks` now wraps visible text into semantic lines, remaps source hyperlink ranges through `remap_wrapped_line`, and applies OSC8 markers to linked fragments across rows. Exact ratatui `Paragraph` wrapping fidelity and concrete `Buffer` cell integration remain renderer-framework boundaries.
### codex-tui `bottom_pane/status_line_style.rs` - complete update
- Rust behavior/tests: `status_line_segments_preserve_order_and_plain_text`, `status_line_segments_dim_separators_and_use_theme_styles_first`, `status_line_segments_soften_rgb_theme_styles_without_dimming_text`, `status_line_segments_can_disable_theme_colors`, `pull_request_number_uses_link_style`, `status_line_segments_return_none_when_empty`, plus full `StatusLineAccent::for_item` item-bucket mapping.
- Python coverage: `tests/test_tui_bottom_pane_status_line_style.py`
- Status: `complete`
- Notes: Module-owned behavior is represented in Python: segment order/text, dim separators, theme-style priority through an injected resolver, fallback accent colors, RGB and named-color softening, disabled-theme dimming, PR underline, empty-input `None`, and all Rust status-line item accent buckets. Concrete `foreground_style_for_scopes` theme lookup remains owned by the render/highlight dependency rather than this module.
### codex-tui `terminal_palette.rs` - complete_slice update
- Rust behavior: `rgb_color((u8, u8, u8))` / `indexed_color(u8)` type-bound color construction.
- Python coverage: `tests/test_tui_terminal_palette.py::{test_rgb_and_indexed_color_preserve_semantics,test_rgb_color_rejects_out_of_u8_channels,test_indexed_color_rejects_out_of_u8_range}`
- Status: `complete_slice`
- Notes: Added explicit Python enforcement of Rust's `u8` RGB channel boundary for `rgb_color`, matching the existing indexed-color u8 boundary. Real stdout capability probing and terminal default-color queries remain platform/runtime side effects.
### codex-tui `resize_reflow_cap.rs` - complete update
- Rust behavior/tests: `auto_resize_reflow_max_rows_uses_terminal_defaults`, `auto_resize_reflow_max_rows_prefers_vscode_probe`, `configured_resize_reflow_max_rows_overrides_auto_detection`, `disabled_resize_reflow_max_rows_keeps_all_rows`, `unknown_terminal_uses_fallback_even_under_multiplexer`, plus complete fallback-bucket coverage for terminal names not assigned a special cap.
- Python coverage: `tests/test_tui_resize_reflow_cap.py`
- Status: `complete`
- Notes: Module-owned row-cap strategy is covered: VS Code probe precedence, terminal-specific caps, fallback bucket, explicit disable as `None`, configured limit override, and Python's injectable resolver boundary for terminal detection. Real `codex_terminal_detection::terminal_info` and VS Code environment probing remain dependency/runtime inputs, not unfinished logic in this module.
### codex-tui `permission_compat.rs` - complete_slice update
- Rust behavior: fallback `legacy_compatible_permission_profile` rebuild computes `exclude_tmpdir_env_var` from whether `TMPDIR` resolves to a writable path under the source file-system policy.
- Python coverage: `tests/test_tui_permission_compat.py::test_legacy_compatible_permission_profile_sets_tmpdir_exclusion_from_write_access`
- Status: `complete_slice`
- Notes: Added parity for the controllable TMPDIR exclusion branch in the compatibility rebuild path. `/tmp` exclusion remains a platform/filesystem side-effect boundary because Rust checks absolute path existence plus policy writability against the real host.
### codex-tui `service_tier_resolution.rs` - complete update
- Rust behavior/tests: `configured_service_tier`, `effective_service_tier`, `service_tier_update_for_core`, and `model_supports_service_tier` full module contract.
- Python coverage: `tests/test_tui_service_tier_resolution.py`
- Status: `complete`
- Notes: Completed service-tier resolution semantics: explicit config precedence, `fast_default_opt_out == true` default sentinel only, FastMode guard, unknown-model configured passthrough, default sentinel preservation, supported/unsupported configured tier handling, supported/unsupported model defaults, known-model core fallback to default sentinel, unknown-model no-update, and model tier support lookup. Python's return shape represents Rust `Some(Some(value))` as a string and Rust outer `None` as `None`; upstream has no `Some(None)` branch in this module.
### codex-tui `shimmer.rs` - complete_slice update
- Rust behavior: `shimmer_spans` maps elapsed time through a two-second modulo sweep before calculating the shimmer band position.
- Python coverage: `tests/test_tui_shimmer.py::test_shimmer_sweep_repeats_every_two_seconds`
- Status: `complete_slice`
- Notes: Added explicit parity for the time-period repeat behavior while keeping terminal truecolor detection injectable. Concrete `supports_color` probing and ratatui `Style`/`Color` objects remain framework/runtime boundaries.
### codex-tui `motion.rs` - complete_slice update
- Rust behavior/test: `animation_primitives_are_only_used_by_motion_module` detects both direct `spinner(...)` and direct `shimmer_spans(...)` calls outside allowlisted files, ignoring line comments.
- Python coverage: `tests/test_tui_motion.py::test_animation_primitives_are_only_used_by_motion_module`
- Status: `complete_slice`
- Notes: Extended source-scan policy parity to cover direct spinner violations as well as direct shimmer violations. Exact terminal-color-dependent animated indicator rendering remains a renderer/runtime boundary.
### codex-tui `terminal_palette.rs` - complete_slice update
- Rust behavior: `best_color` only returns true RGB for `TrueColor`, nearest fixed indexed color for `Ansi256`, and `Color::default()` for lower/unknown color levels.
- Python coverage: `tests/test_tui_terminal_palette.py::test_best_color_truecolor_and_unknown_paths`
- Status: `complete_slice`
- Notes: Added explicit `Ansi16` default-color fallback parity for `best_color`. Real `supports_color::on_cached(stdout)` probing and crossterm default-color querying remain platform/runtime side effects.
### codex-tui `motion.rs` - complete_slice update
- Rust behavior: non-truecolor `animated_activity_indicator` alternates visible and dim activity glyphs on 600ms ticks using `(elapsed_ms / 600).is_multiple_of(2)`.
- Python coverage: `tests/test_tui_motion.py::test_animated_activity_indicator_blinks_on_six_hundred_ms_ticks`
- Status: `complete_slice`
- Notes: Added deterministic clock coverage for the animated activity blink cadence. Truecolor shimmer delegation and exact ratatui glyph/style output remain renderer/runtime boundaries.
### codex-tui `terminal_palette.rs` - complete_slice update
- Rust behavior: unix startup probe default colors are copied from `terminal_probe::DefaultColors { fg, bg }` into this module's cached `DefaultColors`.
- Python coverage: `tests/test_tui_terminal_palette.py::test_default_colors_can_be_seeded_from_startup_probe_facade`
- Status: `complete_slice`
- Notes: Added duck-typed startup-probe facade coverage for default-color cache seeding. Real crossterm OSC 10/11 querying and focus-event requery side effects remain platform/runtime boundaries.
### codex-tui `shimmer.rs` - complete_slice update
- Rust behavior: truecolor `shimmer_spans` blends terminal default background toward default foreground with center-band intensity scaled by `0.9`, and always marks truecolor spans bold.
- Python coverage: `tests/test_tui_shimmer.py::test_truecolor_shimmer_blends_default_background_toward_foreground`
- Status: `complete_slice`
- Notes: Added deterministic default-color blend coverage for the truecolor branch. Real terminal default-color discovery and `supports_color` probing remain renderer/runtime boundaries.
### codex-tui `markdown_stream.rs` - complete_slice update
- Rust behavior: `MarkdownStreamCollector::finalize_and_drain_source` clears collector state and returns an empty string when all buffered source has already been committed.
- Python coverage: `tests/test_tui_markdown_stream.py::test_finalize_and_drain_source_after_full_commit_clears_bookkeeping`
- Status: `complete_slice`
- Notes: Fixed Python newline literal handling in the module/tests and added explicit final-drain-after-full-commit parity. Full Rust markdown-to-ratatui rendering helpers remain dependency/renderer boundaries; Python keeps semantic plain-line helpers for source-boundary tests.
### codex-tui `token_usage.rs` - complete update
- Rust behavior: `Display for TokenUsage` appends the reasoning suffix only when `reasoning_output_tokens > 0`; zero and negative values omit it.
- Python coverage: `tests/test_tui_token_usage.py::test_display_format_omits_negative_reasoning_suffix`
- Status: `complete`
- Notes: Added the negative-reasoning display boundary while preserving the module's complete status. Token accounting, context-window percentage, separator formatting, wrapper defaults, and raw-output display behavior remain covered by existing tests.
### codex-tui `render/line_utils.rs` - complete update
- Rust behavior: `line_to_static`, `push_owned_lines`, `is_blank_line_spaces_only`, and `prefix_lines` including empty input.
- Python coverage: `tests/test_tui_render_line_utils.py`
- Status: `complete`
- Notes: Completed the low-level semantic line utility contract: owned cloning preserves style/alignment/spans, owned line pushing clones inputs, blank-line detection accepts only empty/literal-space spans, prefixing uses initial/subsequent spans and resets alignment like Rust's reconstructed line, and empty prefix input returns empty output. Concrete ratatui `Cow` ownership is represented by Python value semantics.
### codex-tui `render/renderable.rs` - complete_slice update
- Rust behavior: `FlexRenderable::allocate` gives integer-division rounding remainder to the last flex child.
- Python coverage: `tests/test_tui_render_renderable.py::test_flex_renderable_gives_rounding_remainder_to_last_flex_child`
- Status: `complete_slice`
- Notes: Added flex remainder allocation parity for semantic layout rects. Concrete ratatui `Buffer`, `Paragraph`, and crossterm cursor-style objects remain represented by Python semantic models.
### codex-tui `render/renderable.rs` - complete_slice update
- Rust behavior: `RowRenderable::render` clips child width to remaining area and stops before rendering children whose computed area is empty.
- Python coverage: `tests/test_tui_render_renderable.py::test_row_renderable_stops_rendering_when_width_is_exhausted`
- Status: `complete_slice`
- Notes: Added row-width exhaustion clipping parity for semantic render records. Concrete ratatui buffer mutation remains represented by the Python recording buffer.
### codex-tui `render/renderable.rs` - complete_slice update
- Rust behavior: `ColumnRenderable::render` intersects each child rect with the parent area before rendering, clipping partially visible children.
- Python coverage: `tests/test_tui_render_renderable.py::test_column_renderable_clips_children_to_visible_area`
- Status: `complete_slice`
- Notes: Added column child clipping parity for semantic render records. Concrete ratatui buffer mutation remains represented by the Python recording buffer.
### codex-tui `transcript_reflow.rs` - complete update
- Rust behavior: `has_pending_reflow` reflects whether a pending deadline exists, and `clear_pending_reflow` clears that state.
- Python coverage: `tests/test_tui_transcript_reflow.py::test_has_pending_reflow_tracks_pending_until_state`
- Status: `complete`
- Notes: Added explicit pending-state helper parity while preserving the module's complete status. Width observation, debounce scheduling, immediate scheduling, pending-target suppression, stream-finish flags, and clear semantics remain covered by existing tests.
### codex-tui `terminal_palette.rs` - complete_slice update
- Rust behavior: `set_default_colors_from_startup_probe(None)` clears cached default foreground/background colors while marking the startup-probe path as attempted.
- Python coverage: `tests/test_tui_terminal_palette.py::{test_default_colors_can_be_seeded_from_startup_probe,test_default_colors_can_be_seeded_from_startup_probe_facade}`
- Status: `complete_slice`
- Notes: Added explicit cache-clear assertions after startup-probe `None` input. Real attempted-cache retry suppression and crossterm OSC 10/11 queries remain platform/runtime boundaries.
| `bottom_pane/status_surface_preview.rs` | `status_line_for_items` empty filtered segment result | `tests/test_tui_bottom_pane_status_surface_preview.py::test_status_line_for_items_returns_none_when_all_preview_values_are_absent` | complete | Ports the missing-value branch where all requested preview values are absent and the semantic status line is omitted. Module-scoped data contract is complete; status-line styling internals remain owned by `status_line_style`/`status_line_setup`. |
| `bottom_pane/footer.rs` | `complete_slice` | `pycodex/tui/bottom_pane/footer.py`; `tests/test_tui_bottom_pane_footer.py` | Added passive footer status/active-agent parity coverage with `test_passive_status_line_combines_agent_and_yields_to_queue_hint`: mirrors Rust `status_line_right_indicator_line`, `shows_passive_footer_line`, and `uses_passive_footer_status_layout` behavior where the queue hint suppresses passive footer status rendering. |
| `bottom_pane/status_line_setup.rs` | StatusLineItem context-remaining ID plus exhaustive description/preview-item mapping | `tests/test_tui_bottom_pane_status_line_setup.py::{test_git_and_title_only_items_are_parseable,test_all_status_line_items_have_rust_descriptions_and_preview_items}` | complete_slice | Strengthens the module-scoped enum contract for all selectable status-line items, including the Rust `context_remaining_is_selectable_id` branch and every `StatusLineItem::description`/`preview_item` arm. Full ratatui snapshot rendering remains a renderer boundary. |
| `bottom_pane/action_required_title.rs` | `build_action_required_title_text` iterator/callback boundary | `tests/test_tui_bottom_pane_action_required_title.py::test_build_action_required_title_text_preserves_order_duplicates_and_skips_callbacks` | complete | Locks Rust's input-order/duplicate-preserving behavior and confirms `value_for` is not called for Spinner or explicitly excluded items. |
| `bottom_pane/unified_exec_footer.rs` | `Renderable::render` empty-area no-op | `tests/test_tui_bottom_pane_unified_exec_footer.py::test_render_clips_to_area_and_accepts_area_shapes` | complete_slice | Adds explicit width-zero render no-op coverage alongside height-zero clipping, mirroring Rust's `area.is_empty()` guard before paragraph rendering. |
| `bottom_pane/chat_composer/footer_state.rs` | `show_flash` replacement and line preservation | `tests/test_tui_bottom_pane_chat_composer_footer_state.py::test_show_flash_replaces_existing_flash_and_preserves_line_spans` | complete_slice | Ports Rust's assignment semantics for replacing an existing `FooterFlash` and preserving the provided semantic `Line` spans/content with a fresh expiry. |
| `bottom_pane/chat_composer/popup_state.rs` | active popup replacement and None payload boundary | `tests/test_tui_bottom_pane_chat_composer_popup_state.py::test_popup_state_active_variant_can_be_replaced_like_rust_field_assignment` | complete | Captures Rust container semantics for replacing the single active popup field, preserving payload identity for concrete variants, and returning inactive for the default no-payload `None` variant. |
| `bottom_pane/chat_composer/draft_state.rs` | mutable draft flags and mention binding key shape | `tests/test_tui_bottom_pane_chat_composer_draft_state.py::test_draft_state_mutable_flags_and_mention_key_shape_match_rust_fields` | complete_slice | Captures module-owned mutable state fields for bash/input/paste flags, pending paste tuple storage, and `HashMap<u64, ComposerMentionBinding>` shape as integer-keyed Python mapping. |
| `bottom_pane/chat_composer/attachment_state.rs` | placeholder-preserving take and remote clear boundary | `tests/test_tui_bottom_pane_chat_composer_attachment_state.py::test_take_recent_submission_images_with_placeholders_and_clear_remote_urls` | complete_slice | Ports `take_recent_submission_images_with_placeholders` clearing/preserving semantics and `clear_remote_image_urls` behavior: remote URLs/selection are cleared without relabeling local image placeholders. |
| `bottom_pane/chat_composer/slash_input.rs` | command-under-cursor slash-boundary behavior | `tests/test_tui_bottom_pane_chat_composer_slash_input.py::{test_command_element_range_and_command_under_cursor_use_byte_offsets,test_editing_command_name_and_popup_filter_text}` | complete_slice | Adds coverage for Rust's `cursor <= name_start` branch: a cursor before/on the slash uses the full command token for under-cursor extraction and popup filter text. |
| `bottom_pane/chat_composer/history_search.rs` | footer match action separator copy | `tests/test_tui_bottom_pane_chat_composer_history_search.py::test_history_search_footer_line_status_variants` | complete_slice | Corrects the semantic footer match action hint separator to Rust's ` 路 ` between `enter accept` and `esc cancel`. |
| `line_truncation.rs` | ellipsis overflow literal | `tests/test_tui_line_truncation.py::test_truncate_line_with_ellipsis_if_overflow_appends_ellipsis` | complete | Corrects Python's overflow suffix to Rust's semantic ellipsis character `…` while preserving the last-span style. |
| `clipboard_paste.rs` | WSL Windows-path conversion root and mixed separators | `tests/test_tui_clipboard_paste.py::test_convert_windows_path_to_wsl_trims_drive_root_and_empty_components` | complete_slice | Covers drive-root conversion, leading separator trimming, mixed slash/backslash splitting, and empty component filtering. |
| `clipboard_copy.rs` | local tmux fallback error composition | `tests/test_tui_clipboard_copy.py::test_local_tmux_reports_native_tmux_and_osc52_errors_when_all_fail` | complete_slice | Covers the native-failure path where terminal fallback is tmux, tmux copy fails, OSC 52 fallback also fails, and Rust composes all three error sources. |
| `approval_events.rs` | enum-like network Allow amendment matching | `tests/test_tui_approval_events.py::test_network_default_decisions_accept_enum_like_allow_action` | complete | Strengthens Rust `NetworkPolicyRuleAction::Allow` parity by accepting enum-like action values and preserving the first Allow amendment in default decision ordering. |
| `branch_summary.rs` | commit-to-PR REST parser first-open filtering | `tests/test_tui_branch_summary.py::test_status_line_pr_api_parser_returns_first_open_pr` | complete_slice | Covers `pull_request_from_api_output` behavior that skips non-open PRs, returns the first open REST item, and returns `None` when no open PR exists. |
| `collaboration_modes.rs` | returned mask clone semantics | `tests/test_tui_collaboration_modes.py::test_returned_masks_are_cloned_like_rust` | complete_slice | Covers Rust `.cloned()` behavior for filtered/default/kind/next helpers so returned `CollaborationModeMask` values are equal but not the original preset objects. |
| `custom_terminal.rs` | `Terminal::clear` empty viewport no-op | `tests/test_tui_custom_terminal.py::test_clear_empty_viewport_is_noop` | complete_slice | Covers Rust `clear` early-return behavior when `viewport_area.is_empty()`, preserving backend output and cursor state in the semantic Python terminal model. |
| `diff_model.rs` | direct variant construction required-field boundaries | `tests/test_tui_diff_model.py::test_file_change_to_dict_requires_variant_fields` | complete_slice | Strengthens Rust enum field invariants by rejecting semantic `to_dict` conversion for Add/Delete without `content` and Update without `unified_diff`. |
| `frames.rs` | `frames_for!` authoritative include file content | `tests/test_tui_frames.py::test_frame_sets_load_authoritative_upstream_files` | complete_slice | Strengthens Rust `include_str!` parity by checking Python frame sets load upstream `frame_1.txt`/`frame_36.txt` content from the same variant directories. |
| `npm_registry.rs` | package metadata object-map serde boundaries | `tests/test_tui_npm_registry.py::test_package_info_requires_object_maps_like_serde` | complete_slice | Captures Rust serde shape requirements that `dist-tags` and `versions` deserialize as maps/objects rather than arrays or scalar values. |
| `notifications/bel.rs` | `BelBackend::notify` emits per call | `tests/test_tui_notifications_bel.py::test_bel_backend_notify_emits_one_bel_per_call` | complete | Strengthens Rust `execute!(stdout(), PostNotification)` parity by ensuring each notify call writes exactly one BEL and does not coalesce or suppress repeated notifications. |
| `notifications/osc9.rs` | `Osc9Backend::notify` emits per call | `tests/test_tui_notifications_osc9.py::test_osc9_backend_notify_emits_one_sequence_per_call` | complete_slice | Strengthens Rust `execute!(stdout(), PostNotification { ... })` parity by ensuring each notify call writes one OSC 9 sequence and preserves message order. |
| `session_log.rs` | `SessionLogger::open` OnceLock first-file retention | `tests/test_tui_session_log.py::test_logger_open_keeps_first_file_like_once_lock` | complete_slice | Captures Rust `OnceLock::get_or_init` behavior: later `open` calls do not replace the active session log file, so writes continue to the first opened path. |

## 2026-06-12 - oss_selection.rs KeyEventKind press-only slice
- Rust module: `codex-tui::oss_selection`
- Rust anchor: `OssSelectionWidget::handle_key_event` only delegates to `handle_select_key` when `key.kind == KeyEventKind::Press`.
- Python module: `pycodex.tui.oss_selection`
- Python tests: `tests/test_tui_oss_selection.py::test_arrow_navigation_wraps_and_release_events_are_ignored`
- Status: `complete_slice`
- Notes: Added parity for non-press event filtering so release and repeat events do not move selection or trigger decisions; this preserves the existing terminal/raw-mode UI boundary.
| `external_agent_config_migration_startup.rs` | import failure retry loop preserves selected items and passes error message back to prompt | `tests/test_tui_external_agent_config_migration_startup.py::test_handle_prompt_retries_after_import_failure_with_error_message` | complete_slice | Strengthens Rust startup loop parity: failed `external_agent_config_import` records `Migration failed: ...`, re-enters the prompt with the previous selection, and succeeds on a later proceed attempt without exiting startup. |
| `model_migration.rs` | `migration_copy_for_models` empty target description fallback | `tests/test_tui_model_migration.py::test_migration_copy_empty_description_uses_recommended_fallback` | complete | Strengthens Rust `.filter(|desc| !desc.is_empty())` parity: an empty target description falls back to the default recommended-performance copy instead of rendering a blank description line. |
| `debug_config.rs` | `render_mdm_layer_details` empty MDM value branch | `tests/test_tui_debug_config.py::test_render_mdm_layer_details_empty_value_matches_rust_branch` | complete_slice | Strengthens Rust helper parity for the explicit empty raw-TOML branch: an empty MDM value renders `     MDM value: <empty>` instead of a multiline block or formatted table fallback. |
| `config_update.rs` | `build_feature_enabled_edit` accepts Rust `FeatureSpec.default_enabled` shape | `tests/test_tui_config_update.py::test_build_feature_enabled_edit_accepts_rust_feature_spec_shape` | complete_slice | Strengthens the injected feature-catalog boundary to mirror Rust `FEATURES` entries: disabling a default-false feature clears `features.<key>` when the spec exposes `default_enabled = false`. |
| `audio_device.rs` | selected output device default-config error boundary | `tests/test_tui_audio_device.py::test_select_configured_output_device_reports_default_config_error` | complete_slice | Strengthens Rust `default_config` parity for `RealtimeAudioDeviceKind::Speaker`: when a device exists but `default_output_config` fails, selection reports `failed to get default output config` rather than a missing-device error. |
| pp_command.rs | AppCommand::user_turn owns/copies input item vector | 	ests/test_tui_app_command.py::test_user_turn_copies_items_list_like_owned_vec | complete_slice | Strengthens Rust owned-Vec<UserInput> constructor semantics: Python copies the incoming item list so later caller mutations do not change the command payload. |
| `app_command.rs` | `AppCommand::user_turn` owns/copies input item vector | `tests/test_tui_app_command.py::test_user_turn_copies_items_list_like_owned_vec` | complete_slice | Strengthens Rust owned-`Vec<UserInput>` constructor semantics: Python copies the incoming item list so later caller mutations do not change the command payload. |
| `live_wrap.rs` | `RowBuilder::new` and `set_width` clamp zero width to one | `tests/test_tui_live_wrap.py::test_row_builder_clamps_zero_width_like_rust` | complete | Strengthens constructor and resize boundary parity: Rust uses `width.max(1)` for both initial and updated target widths, so zero-width inputs still produce one-column wrapping semantics. |
| `app/pets.rs` | ambient/picker pet image render error boundaries | `tests/test_tui_app_pets.py` | complete_slice | Ports module-owned error handling semantics: terminal render/clear errors propagate, asset render errors disable ambient pet or mark preview failure, asset clear failures are warning-only, and picker preview failures clear the preview request with `None`. Background loading and async config persistence remain explicit not-ported boundaries. |
| `app/background_requests.rs` | pure helper tests: marketplace source resolution, hidden marketplaces, MCP inventory maps, feedback upload params | `tests/test_tui_app_background_requests.py` | complete_slice | Ports the Rust unit-test-covered helper contract while keeping app-server RPC launchers explicit `not_ported` boundaries. Relative local marketplace sources resolve against cwd with suffix preservation, `openai-bundled` marketplaces are filtered, MCP tools are keyed as `mcp__{server}__{tool}`, and feedback upload params include/omit logs, thread IDs, and turn tags per Rust behavior. |
| `app/config_persistence.rs` | pure effective-config extraction helpers | `tests/test_tui_app_config_persistence.py` | complete_slice | Ports module-local helper behavior for overridden write messages, feature flag fallback/default resolution, approval reviewer/policy/sandbox extraction, memories extraction, and Windows sandbox extraction. Async ConfigBuilder/config-write/App sync paths remain explicit `not_ported` runtime boundaries. |
| `app/plugin_mentions.rs` | plugin list summaries to mention capability summaries | `tests/test_tui_app_plugin_mentions.py` | complete_slice | Ports Rust GUI-eligibility filtering and semantic mention conversion: only installed/enabled/non-admin-disabled plugins are included, display names and descriptions are trimmed from interface metadata, marketplace name is the description fallback, and capability flags/lists default empty. App-server fetch remains explicit `not_ported`. |
| `app/platform_actions.rs` | Windows sandbox state defaults, side return shortcuts, and failed scan warning event | `tests/test_tui_app_platform_actions.py` | complete_slice | Ports module-local semantics: `WindowsSandboxState::default`, `side_return_shortcut_matches` Press-only Ctrl-C/Ctrl-D matching, and the failed world-writable scan warning event shape. Actual Windows sandbox scanning remains an explicit `not_ported` side-effect boundary. |
| `app/thread_goal_actions.rs` | ephemeral goal errors and replace-confirm status predicate | `tests/test_tui_app_thread_goal_actions.py` | complete_slice | Ports Rust helper behavior for temporary-session goal error messaging and `should_confirm_before_replacing_goal`: completed goals skip replacement confirmation, while active/paused/blocked/usage-limited/budget-limited goals require confirmation. App-server goal get/set/clear and ChatWidget UI prompts remain explicit `not_ported` runtime boundaries. |
| `app/thread_routing.rs` | startup/thread-event routing predicates and active non-primary shutdown failover predicate | `tests/test_tui_app_thread_routing.py` | complete_slice | Ports pure module-owned routing decisions: initial-session waiting, paused-goal prompt gating after resume, active-thread receiver gating, stop-waiting predicate, and non-primary shutdown failover suppression for primary/pending shutdown-exit threads. App-server submission, replay, channel draining, and permission-profile integration remain explicit `not_ported` runtime boundaries. |
| `app/session_lifecycle.rs` | thread-read terminal error and includeTurns fallback classifiers | `tests/test_tui_app_session_lifecycle.py` | complete_slice | Ports Rust unit-test-covered error classification helpers: terminal `thread not loaded:` detection, closed-state inference preserving cached closed state, and includeTurns fallback detection for unmaterialized/ephemeral threads. Agent picker, attach/select, fresh-session, and resume app-server flows remain explicit `not_ported` runtime boundaries. |
| `app/thread_session_state.rs` | active cached-session sync and thread/read fallback session construction | `tests/test_tui_app_thread_session_state.py` | complete_slice | Ports Rust-tested session-state semantics with lightweight semantic sessions: service tier and permission sync only update the active cached session, side-thread cached sessions are not rewritten, thread/read fallback uses active widget permission settings, cross-thread collaboration/personality fields are cleared, and rollout paths without readable session model clear the model. Real async channel/store locks and StateDB model lookup remain runtime boundaries. |
| `app/thread_settings.rs` | thread settings update changed-field predicate and settings-to-session application | `tests/test_tui_app_thread_settings.py` | complete_slice | Ports module-local helper semantics: update params with no optional fields are skipped, any Rust-listed optional field counts as a change, settings update cached session provider/service/approval/permissions/cwd/personality/collaboration state, and model/effort are written to the session only for default collaboration mode while always embedded in collaboration settings. App-server update sending and async cached-session channel writes remain explicit `not_ported` boundaries. |
| `app/startup_prompts.rs` | model migration prompt predicates, accepted migration events, model availability NUX selection, and harness writable-root normalization | `tests/test_tui_app_startup_prompts.py` | complete_slice | Ports module-local startup helper semantics: migration prompt gating by current/target/seen/picker availability/upgrade relation, migration hide keys, target preset lookup, accepted migration config mutation and event order, NUX max-show first-match selection, and relative additional writable roots resolved against cwd. TUI prompt execution, ConfigEdits persistence, project/system warning rendering, and async tooltip persistence remain explicit `not_ported` runtime boundaries. |
| `app/event_dispatch.rs` | `handle_exit_mode` shutdown/immediate exit planning | `tests/test_tui_app_event_dispatch.py` | complete_slice | Ports module-owned exit-mode semantics as a deterministic plan: `ShutdownFirst` marks the active-or-widget thread for shutdown, uses the 2s timeout when a thread exists, clears the pending marker before returning user-requested exit, and `Immediate` clears the marker without scheduling shutdown. Full `AppEvent` dispatch and async app-server shutdown remain explicit `not_ported` runtime boundaries. |
| `app/app_server_event_targets.rs` | request thread-id extraction and notification thread targeting | `tests/test_tui_app_app_server_event_targets.py` | complete | Covers all module-owned public behavior: request variants with thread IDs parse valid UUID thread IDs and return `None` for invalid/global variants; warning/global/thread notification routing matches Rust tests; invalid notification thread IDs are reported as `InvalidThreadId` rather than treated as global. |
| `app/input.rs` | app-level input predicates and external-editor state transitions | `tests/test_tui_app_input.py` | complete_slice | Ports module-owned pure input behavior: app keymap shortcuts are disabled by overlays/modals, main-vs-side backtrack Esc predicates respect normal mode, empty composer, and Vim insert-Esc handling, side backtrack rejection resets primed state and emits the Rust error message, and external-editor request/reset update state, footer hint, and frame request. Full keyboard dispatch, editor process launch, transcript overlay, terminal clear, and app-server navigation remain explicit `not_ported` runtime boundaries. |
| `app/app_server_requests.rs` | pending app-server request correlation and Rust unit-test parity | `tests/test_tui_app_app_server_requests.py` | complete_slice | Adds parity coverage for the module-owned pending request store: exec/file/permissions/user-input/MCP request correlation, FIFO user-input resolution per turn, unsupported DynamicToolCall/attestation/legacy messages, ChatGPT auth refresh pass-through, notification resolution removal, `contains_server_request`, approval-id fallback, and `clear`. Transport-level `reject_app_server_request` remains an explicit app-server runtime boundary. |
| `app/side.rs` | side conversation prompt/status/blocking semantics | `tests/test_tui_app_side.py` | complete_slice | Ports module-owned side-conversation semantics: boundary prompt and developer instruction text, start-block/error messages, parent status labels/actionability/request mapping, notification-to-status changes, side UI label/rename/interrupted-mode sync, parent status set/clear/actionable transitions, side discard selection, message restore, and fork snapshot reset. App-server fork/inject/select/discard/interrupt runtime remains explicit `not_ported`. |
| `bottom_pane/app_link_view.rs` | URL elicitation auth/generic parameter boundaries | `tests/test_tui_bottom_pane_app_link_view.py` | complete_slice | Strengthens `AppLinkViewParams::from_url_app_server_request` parity: rejects non-URL elicitation variants, rejects missing/non-auth codex-app auth metadata, enforces ChatGPT-only hosts for `codex_apps` auth URLs, trims connector names, falls back blank connector IDs to elicitation IDs, and keeps generic HTTPS URL elicitations host-agnostic. Ratatui snapshot rendering remains represented by semantic line/action models. |
| `app/resize_reflow.rs` | trailing stream runs, replay row caps, wrap policy, and transcript-tail rendering | `tests/test_tui_app_resize_reflow.py` | complete_slice | Ports framework-free resize-reflow behavior: `trailing_run_start` includes the first non-continuation stream cell and ignores non-matching tails, initial replay buffering drops oldest rows over the cap, raw-output mode selects terminal wrapping, history insertion separators follow first-emission/stream-continuation rules, transcript tail rendering restores separators then enforces row caps, stream-time detection covers active streams and trailing agent/plan stream cells, and reset clears emission state. Terminal/TUI resize execution remains explicit `not_ported`. |
| `bin/md-events.rs` | stdin read-error boundary and pulldown-cmark parser dependency | `tests/test_tui_bin_md_events.py` | blocked | Ports the Rust read failure behavior (`failed to read stdin: {err}` and exit code 1) while explicitly blocking the successful Markdown event stream because it depends on `pulldown_cmark::Parser` plus Rust `Debug` event formatting. Python does not silently substitute a partial Markdown parser. |
| `chatwidget/status_state.rs` | status indicator, guardian-review aggregation, terminal title status, retry header cache | `tests/test_tui_chatwidget_status_state.py` | complete | Ports all module-owned behavior: `StatusIndicatorState::working` and guardian-review detection, `TerminalTitleStatusKind` variants/default intent, `PendingGuardianReviewStatus` start/update/finish/empty and 1/many/+N status formatting, `StatusState::default`, `set_status`, and retry header remember/take-once semantics. |
| `chatwidget/status_controls.rs` | status setter/setup preview/cwd-gated lookup/context percent helpers | `tests/test_tui_chatwidget_status_controls.py` | complete_slice | Ports module-owned pure controls: `set_status` details trim/capitalize/clear behavior and status-surface refresh trigger, status-line/footer pass-through setters, status-line setup config mutation, terminal-title preview/revert/commit semantics, branch/git-summary stale-cwd rejection and matching-cwd completion, context remaining/used/total usage helpers, rate-limit display clamping, and reasoning-effort label mapping. History-cell status output, setup view construction, async git lookup, and rendering remain explicit runtime boundaries. |

### codex-tui::chatwidget::notifications - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/notifications.rs`
- Python module: `pycodex/tui/chatwidget/notifications.py`
- Python parity tests: `tests/test_tui_chatwidget_notifications.py`
- Covered behavior: `Notification::display`, `type_name`, `priority`, `allowed_for`, `agent_turn_preview`, `user_input_request_summary`, and `ChatWidget::notify` / `maybe_post_pending_notification` pending-notification coalescing via a semantic `NotificationCoalescer`.
- Status: `complete_slice`; framework-specific `crate::tui::Tui::notify` side effect is represented as returned display text instead of copying the Rust TUI type.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::service_tiers - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/service_tiers.rs`
- Rust behavior evidence: `codex/codex-rs/tui/src/chatwidget/tests/slash_commands.rs` (`service_tier_commands_lowercase_catalog_names`, `fast_keybinding_toggle_uses_same_events_as_fast_slash_command`, `fast_keybinding_toggle_requires_feature_and_idle_surface`) plus the module's local `ChatWidget` methods.
- Python module: `pycodex/tui/chatwidget/service_tiers.py`
- Python parity tests: `tests/test_tui_chatwidget_service_tiers.py`
- Covered behavior: service tier set/current/configured accessors, core update delegation, fast status predicate, fast keybinding gate, fast/service-tier toggle selection, current-model command generation with lowercase names, model support lookup, and effective-tier refresh.
- Status: `complete_slice`; Rust `AppEvent`/`AppCommand` dispatch is represented by semantic `ServiceTierSelectionEvent` records instead of copying framework transport types.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::status_surfaces - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/status_surfaces.rs`
- Python module: `pycodex/tui/chatwidget/status_surfaces.py`
- Python parity tests: `tests/test_tui_chatwidget_status_surfaces.py`
- Covered behavior: default status/title item ids, parsed `StatusSurfaceSelections` git-branch/git-summary predicates, insertion-order invalid item deduplication with Rust-style quoted ids, 5h/weekly rate-limit window selection helpers, window-label matching, terminal-title part truncation, spinner frame selection, and action-required title prefix phase.
- Explicit boundary: full `ChatWidget` status-line rendering, git lookup/cache orchestration, OSC terminal-title writes, `permissions_display`, and `approval_mode_display` remain outside this pure-helper slice; permission/approval display functions raise `NotImplementedError` rather than faking framework config behavior.
- Status: `complete_slice`.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::streaming - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/streaming.rs`
- Python module: `pycodex/tui/chatwidget/streaming.py`
- Python parity tests: `tests/test_tui_chatwidget_streaming.py`
- Covered behavior: `restore_reasoning_status_header`, `stream_controllers_idle`, `maybe_restore_status_indicator_after_stream_idle`, reasoning delta/final/section-break state transitions, stream error status update, `on_agent_message_item_completed` phase-based pending restore flag, `handle_stream_finished`, active stream-tail detection and clearing, and the local `extract_first_bold` helper used by this module.
- Explicit boundary: live `StreamController`/`PlanStreamController` rendering, markdown parsing/consolidation events, adaptive chunking, interrupt manager flushing, commit tick batching, and real history-cell/TUI side effects remain outside this semantic state slice.
- Status: `complete_slice`.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::permissions_menu - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/permissions_menu.rs`
- Rust behavior evidence: `codex/codex-rs/tui/src/chatwidget/tests/permissions.rs` selection event expectations plus local menu construction/error branches.
- Python module: `pycodex/tui/chatwidget/permissions_menu.py`
- Python parity tests: `tests/test_tui_chatwidget_permissions_menu.py`
- Covered behavior: required builtin preset lookup and internal error messages, Default/Auto-review/Full Access/Read Only menu ordering, Default description suffix removal, GuardianApproval auto-review insertion, builtin current-state detection, custom profile append/default description/current-state behavior, disabled reason propagation, and `PermissionProfileSelection` action payload construction.
- Explicit boundary: real bottom-pane popup rendering, selection action dispatch through app event channels, full approval preset confirmation flow, and permission policy validation remain outside this semantic menu-construction slice.
- Status: `complete_slice`.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::model_popups - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/model_popups.rs`
- Rust behavior evidence: `codex/codex-rs/tui/src/chatwidget/tests/popups_and_settings.rs` model picker filtering/snapshots and `codex/codex-rs/tui/src/chatwidget/tests/plan_mode.rs` Plan reasoning scope prompt expectations.
- Python module: `pycodex/tui/chatwidget/model_popups.py`
- Python parity tests: `tests/test_tui_chatwidget_model_popups.py`
- Covered behavior: auto-model detection/order, hidden model filtering, quick auto popup construction, All models item construction, empty all-models info message, custom OpenAI base URL warning normalization, reasoning effort labels, single-effort immediate apply, multi-effort reasoning item/default/current/warning construction, Plan-mode reasoning scope prompt gate, Plan-only/all-modes action event sequences, and Plan mode prompt notification title.
- Explicit boundary: real `model_catalog.try_list_models` async/update error path, renderable headers/styles, bottom-pane popup rendering, live selection dispatch closures, and full snapshot rendering are outside this semantic popup-construction slice.
- Status: `complete_slice`.
- Tests not run in this heartbeat per instruction.

### codex-tui::chatwidget::review_popups - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/chatwidget/review_popups.rs`
- Rust behavior evidence: `codex/codex-rs/tui/src/chatwidget/tests/review_mode.rs` (`review_popup_custom_prompt_action_sends_event`, `review_commit_picker_shows_subjects_without_timestamps`, custom prompt trim/empty behavior) plus local popup builders.
- Python module: `pycodex/tui/chatwidget/review_popups.py`
- Python parity tests: `tests/test_tui_chatwidget_review_popups.py`
- Covered behavior: review preset popup item order/actions/dismiss flags, branch picker item labels/search values and detached-HEAD fallback, commit picker subject-only rows/search values/review payloads, custom prompt metadata, and trimmed custom review submission with empty input ignored.
- Explicit boundary: async `local_git_branches`, `current_branch_name`, `recent_commits`, real `CustomPromptView`, bottom-pane rendering, and app-event channel dispatch remain outside this semantic popup-construction slice.
- Status: `complete_slice`.
- Tests not run in this heartbeat per instruction.

### codex-tui::exec_cell - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/exec_cell/mod.rs`
- Python module: `pycodex.tui.exec_cell`
- Python parity tests: `tests/test_tui_exec_cell_facade.py`
- Covered behavior: parent facade declares `model` and `render` submodules and re-exports `CommandOutput`, test-visible `ExecCall`, `ExecCell`, `OutputLinesParams`, `TOOL_CALL_MAX_LINES`, `new_active_exec_command`, and `output_lines` from those submodules.
- Status: `complete`; this records only the parent facade boundary and does not change child module behavior status.
- Tests not run per instruction.

### codex-tui::onboarding - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/onboarding/mod.rs`
- Python module: `pycodex.tui.onboarding`
- Python parity tests: `tests/test_tui_onboarding_facade.py`
- Covered behavior: parent facade declares `auth`, `keys`, public `onboarding_screen`, `trust_directory`, and `welcome` submodules, and re-exports `mark_url_hyperlink` / `mark_underlined_hyperlink` from `onboarding::auth`.
- Status: `complete`; this records only the parent facade boundary and does not change child module behavior status.
- Tests not run per instruction.

### codex-tui::status - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/status/mod.rs`
- Python module: `pycodex.tui.status`
- Python parity tests: `tests/test_tui_status_facade.py`
- Covered behavior: parent facade declares `account`, `card`, `format`, `helpers`, `rate_limits`, and public `remote_connection` submodules, and re-exports the selected account/card/helper/rate-limit display functions and types from Rust `pub(crate) use` statements.
- Status: `complete`; this records only the parent facade boundary and does not change child module behavior status.
- Tests not run per instruction.

### codex-tui::bottom_pane::mentions_v2 - complete (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs`
- Python module: `pycodex.tui.bottom_pane.mentions_v2`
- Python parity tests: `tests/test_tui_bottom_pane_mentions_v2_facade.py`
- Covered behavior: parent facade declares `candidate`, `filter`, `footer`, `popup`, `render`, `search_catalog`, and `search_mode` submodules, and re-exports `Selection as MentionV2Selection`, `Popup as MentionV2Popup`, and `build_search_catalog`.
- Status: `complete`; this records only the parent facade boundary and does not change child module behavior status.
- Tests not run per instruction.

### codex-tui::tui - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/tui.rs`
- Python module: `pycodex.tui.tui`
- Python parity tests: `tests/test_tui_tui_slice.py`
- Covered behavior: Rust-test-covered `should_emit_notification` focus rules for `NotificationCondition::Unfocused` and `Always`, plus `EnableAlternateScroll` / `DisableAlternateScroll` ANSI sequences (`\x1b[?1007h` and `\x1b[?1007l`), ANSI support predicates, and WinAPI error boundaries.
- Explicit boundary: terminal raw mode setup/restore, real crossterm/ratatui terminal initialization, event streams, viewport clearing/reflow, drawing, notifications, history insertion, job control, panic hooks, and terminal image side effects remain runtime/framework work and continue to raise explicit `not_ported` where not covered.
- Status: `complete_slice`.
- Tests not run per instruction.

### codex-tui::status::tests - complete_slice (2026-06-12)

- Rust source: `codex/codex-rs/tui/src/status/tests.rs`
- Python module: `pycodex.tui.status.tests`
- Python parity tests: `tests/test_tui_status_tests_slice.py`
- Covered behavior: low-level test harness helpers `app_server_workspace_write_profile`, `set_workspace_cwd`, `test_status_account_display`, `render_lines`, `sanitize_directory`, and `reset_at_from` are ported with dependency-light semantic models.
- Explicit boundary: large async status-card snapshot tests, permission-profile integration, model-provider display, token-usage cards, rate-limit/credits snapshots, and full `new_status_output` rendering assertions remain owned by status production submodules and are not marked complete by this test-helper slice.
- Status: `complete_slice`.
- Tests not run per instruction.

### codex-tui markdown_render/table_key_value.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/markdown_render/table_key_value.rs`
- Python module: `pycodex/tui/markdown_render/table_key_value.py`
- Python tests: `tests/test_tui_markdown_render_table_key_value.py`
- Status: `complete_slice`
- Covered behavior:
  - `should_render_records` row-threshold logic for fragmented compact/token-heavy values and starved expansive cells.
  - `expansive_cells_are_starved` compact filtering plus cramped expansive/narrative catastrophic-height detection.
  - `render_records`, `render_aligned_field`, `render_stacked_field`, separator insertion, label styling, and width-dependent aligned vs stacked layout.
  - `wrap_cell`, `cell_width`, `widest_line_width`, and prefix hyperlink column remapping using Python semantic `Line`/`Span`/`HyperlinkLine` models.
- Boundary note: this ports the standalone key/value table record-rendering slice. Full markdown table parsing/classification in `markdown_render.rs` remains tracked by that parent module rather than this submodule.

### codex-tui pets/image_protocol.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/image_protocol.rs`
- Python module: `pycodex/tui/pets/image_protocol.py`
- Python tests: `tests/test_tui_pets_image_protocol.py`
- Status: `complete_slice`
- Covered behavior:
  - `ImageProtocol`, `ProtocolSelection`, `PetImageSupport`, and `PetImageUnsupportedReason` semantic models.
  - Protocol selection parsing and explicit Kitty/Sixel resolution independent of tmux.
  - Auto support detection precedence for tmux, Zellij, Kitty, WezTerm, terminal multiplexers, iTerm2 version support, Kitty graphics, Sixel, and unsupported fallback.
  - Dotted terminal-version parsing and minimum-version comparison.
  - Kitty delete/transmit commands, inline PNG base64 chunking, local-file payload encoding, optional image id formatting, and tmux passthrough escape wrapping.
- Boundary note: `sixel_frame` remains an explicit non-stdlib image resize/encoding boundary and raises `not_ported`; `pets/sixel.rs` is tracked separately.

### codex-tui pets/sixel.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/sixel.rs`
- Python module: `pycodex/tui/pets/sixel.py`
- Python tests: `tests/test_tui_pets_sixel.py`
- Status: `complete`
- Covered behavior:
  - `encode_rgba` transparent-background DCS framing, geometry header, palette definitions, pixel planes, ST terminator, non-zero dimension check, and RGBA byte-length validation.
  - Deterministic RGB332 color reduction, RGB332 palette expansion, Sixel percent conversion, alpha-threshold transparency handling, active band color scanning, sixel column masks, and sixel run-length encoding.
  - Multi-band advancement (`$-` and `-`) and transparent-pixel omission.
- Boundary note: this completes the standalone minimal Sixel byte encoder. Image loading/resizing before this encoder remains owned by `pets/image_protocol.rs` / caller modules.

### codex-tui pets/asset_pack.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/asset_pack.rs`
- Python module: `pycodex/tui/pets/asset_pack.py`
- Python tests: `tests/test_tui_pets_asset_pack.py`
- Status: `complete_slice`
- Covered behavior:
  - Versioned pet pack path construction and built-in spritesheet asset path construction.
  - Public CDN URL construction and HTTPS-only download URL validation.
  - Bounded byte download shape with timeout, final URL validation, content-length guard, and max-byte read guard.
  - Staging-file ensure flow: cached-valid fast path, download, parent directory creation, staging write, staging validation failure cleanup, install attempt, destination fallback validation, stale destination removal, and final install retry.
  - Downloaded spritesheet install via move/rename semantics and injectable test-pack writer path flow.
- Boundary note: `validate_cached_spritesheet` remains an explicit image-dimension validation boundary because Rust relies on `image::image_dimensions` for WebP decoding. `catalog.rs` built-in pet catalog behavior remains tracked separately; tests inject pet DTOs instead of marking catalog complete.

### codex-tui pets/catalog.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/catalog.rs`
- Python module: `pycodex/tui/pets/catalog.py`
- Python tests: `tests/test_tui_pets_catalog.py`
- Status: `complete`
- Covered behavior:
  - Frame and spritesheet dimension constants: 192x208 frames, 8x9 grid, 1536x1872 spritesheet.
  - Full built-in pet catalog entries, ordering, ids, display names, descriptions, and versioned spritesheet filenames.
  - `builtin_pet` lookup by id with missing-id `None` behavior.
  - `write_test_spritesheet` test-pack helper creates the requested file path; actual WebP image encoding remains outside this pure catalog table and is represented by a deterministic test marker in Python.

### codex-tui resume_picker.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/resume_picker.rs`
- Python module: `pycodex/tui/resume_picker/__init__.py`
- Python tests: `tests/test_tui_resume_picker_slice.py`
- Status: `complete_slice`
- Covered behavior:
  - Core constants for paging, load threshold, picker chrome/list inset, footer spacing, and metadata widths.
  - `SessionTarget.display_label` path-vs-thread fallback.
  - Semantic `SessionSelection` target variants and `SessionPickerAction` title/action-label/selection construction.
  - `SessionFilterMode::from_show_all` and toggle semantics, `ToolbarControl` previous/next wrap, and `SessionListDensity` toggle/from-view-mode slice.
  - `raw_reasoning_visibility`, local/remote cwd filter helpers, provider filter selection, pasted-query whitespace normalization, sort-key labels, and list viewport width calculation.
- Boundary note: interactive TUI runtime, app-server pagination, transcript loading, full `PickerState` key handling, ratatui rendering/snapshots, and transcript conversion remain explicit neighboring slices in this large module.

### codex-tui ide_context/ipc.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/ipc.rs`
- Python module: `pycodex/tui/ide_context/ipc.py`
- Python tests: `tests/test_tui_ide_context_ipc.py`
- Status: `complete_slice`
- Covered behavior:
  - IDE IPC constants, source client id, max frame size, and user-facing/prompt-skip hint branches for connect, send, read, invalid response, too-large response, and request-failed error codes.
  - `hint_with_retry`, IDE context request JSON shape, little-endian length-prefixed JSON frame writing/reading, max-frame rejection, short-read error boundary, and JSON object validation.
  - Response-loop protocol handling for broadcasts, unrelated responses, client discovery requests, unsupported inbound requests, missing/unknown message types, and matching request response selection.
  - Success/error response validation and `result.ideContext` extraction.
- Boundary note: actual Unix socket connection, peer-owner validation, fd readiness/deadline polling, Windows named-pipe transport, and live `fetch_ide_context` remain explicit platform/runtime boundaries.

### codex-tui ide_context/windows_pipe.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/windows_pipe.rs`
- Python module: `pycodex/tui/ide_context/windows_pipe.py`
- Python tests: `tests/test_tui_ide_context_windows_pipe.py`
- Status: `complete_slice`
- Covered behavior:
  - Win32 BOOL/null-handle constants and semantic stream/deadline wrapper.
  - Empty read/write branches returning zero and no-op flush branch.
  - `OwnedHandle.raw` wrapper behavior and no-op Python drop boundary.
  - `OverlappedOperation.cancel_and_timeout` timeout-error semantics.
  - Empty `TokenUserBuffer.sid` validation error boundary.
  - `remaining_timeout_ms` expired-zero, minimum-one-ms, and u32 clamp semantics; timeout error message.
- Boundary note: native Win32 `CreateFileW`, `ReadFile`/`WriteFile`, overlapped event completion, `CancelIoEx`, process-token/SID lookup, and pipe-server owner validation remain explicit platform boundaries and raise `not_ported` rather than being simulated.

### codex-tui app/app_server_events.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/app/app_server_events.rs`
- Python module: `pycodex/tui/app/app_server_events.py`
- Python tests: `tests/test_tui_app_app_server_events.py`
- Status: `complete_slice`
- Covered behavior:
  - Enabled MCP server extraction for startup expectation refresh.
  - Top-level app-server event routing for lagged, server notification, server request, disconnected, and unknown events.
  - Special server-notification branches: request resolved/dismissal, MCP status refresh, rate-limit update, account update, external-agent config import completion, and connector list update.
  - Thread-targeted notification routing to primary thread, other thread, invalid thread id, or global chat-widget handling.
  - Server-request unsupported rejection flow, threadless request warning, and primary/other thread request routing.
- Boundary note: Rust implements these as async `App` methods with real chat-widget/app-server side effects. Python exposes semantic action plans instead of mutating a full App runtime; queueing, rejection transport, config refresh, and UI updates remain runtime integration boundaries.

### codex-tui chatwidget/windows_sandbox_prompts.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/chatwidget/windows_sandbox_prompts.rs`
- Python module: `pycodex/tui/chatwidget/windows_sandbox_prompts.py`
- Python parity tests: `tests/test_tui_chatwidget_windows_sandbox_prompts.py`
- Status: `complete_slice`
- Covered behavior:
  - World-writable warning visibility gates and semantic detail tuple mapping.
  - Permission profile mode labels for Full Access, Agent, and Read-Only modes.
  - Warning confirmation header/sample/extra-count planning and Continue / Continue-and-remember action ordering.
  - Legacy and elevated Windows sandbox enable prompt item/action/telemetry marker planning.
  - Elevated setup fallback prompt header, items, and actions.
  - `maybe_prompt_windows_sandbox_enable` gate for `show_now`, disabled sandbox level, and auto preset availability.
  - Setup-status and clear-status composer/status-indicator action plans.
- Boundary note: real Windows filesystem scanning, permission-profile application closures, AppEvent dispatch, telemetry calls, BottomPane rendering, and ratatui widget rendering remain runtime/platform boundaries.

### codex-tui pets/model.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/model.rs`
- Python module: `pycodex/tui/pets/model.py`
- Python parity tests: `tests/test_tui_pets_model.py`
- Status: `complete_slice`
- Covered behavior:
  - `AnimationFrame`, `Animation`, `FrameSpec`, `AnimationSpec`, `PetFile`, and `Pet` semantic models.
  - Built-in pet selector loading from catalog metadata and cache spritesheet path.
  - Custom `custom:` selectors, legacy avatar fallback, explicit path and `pet.json` path loading.
  - Manifest defaulting for id/display name/description/spritesheet path/frame spec.
  - Path-like selector detection, `~` expansion with `HOME`, and spritesheet path escape rejection.
  - Frame-grid validation, maximum frame-count checks, animation fps/loop/fallback/index validation.
  - Default idle/app-state animations, sprite index rows, repeated app-state segments, and cache-key hash/frame-shape semantics.
- Boundary note: Rust validates real WebP dimensions with the `image` crate. Python validates dimensions only for the local catalog test-spritesheet marker and explicitly leaves real image decoding as a dependency boundary.

### codex-tui pets/frames.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/frames.rs`
- Python module: `pycodex/tui/pets/frames.py`
- Python parity tests: `tests/test_tui_pets_frames.py`
- Status: `complete_slice`
- Covered behavior:
  - `prepare_png_frames` output-directory creation and `frame_{index:03}.png` expected path generation.
  - Complete-cache reuse without invoking image slicing.
  - Incomplete-cache stale cleanup for direct child files whose names start with `frame_` and end with `.png`.
  - Row/column frame crop planning, checked index/x/y arithmetic, and grid-count boundary errors.
  - Injected slicer boundary for materializing PNG frame files without shelling out.
- Boundary note: Rust uses the `image` crate to open spritesheets and save real PNG crops. Python does not silently fake image decoding; missing slicer raises the explicit `not_ported` boundary.

### codex-tui pets/ambient.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/ambient.rs`
- Python module: `pycodex/tui/pets/ambient.py`
- Python parity tests: `tests/test_tui_pets_ambient.py`
- Status: `complete_slice`
- Covered behavior:
  - `PetNotificationKind` animation names, labels, fallback bodies, and lifetimes.
  - `PetNotification` creation, expiration checks, and notification-height semantics.
  - `current_animation_frame`, `frame_at_elapsed`, looping effective elapsed behavior, one-shot final-frame behavior, and per-frame delay calculation.
  - Reduced-motion stable first-frame behavior and no-follow-up scheduling semantics.
  - Ambient image size calculation, composer gap rows, current/idle frame path clamping, draw request anchoring above composer, and picker preview centering.
  - Unsupported protocol and too-small-layout draw suppression.
- Boundary note: `AmbientPet::load`, default terminal protocol probing, real `FrameRequester`, and terminal image rendering remain runtime boundaries. Python uses semantic protocol/support values and explicit `not_ported` for runtime loading/probing.

### codex-tui pets/preview.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/preview.rs`
- Python module: `pycodex/tui/pets/preview.py`
- Python parity tests: `tests/test_tui_pets_preview.py`
- Status: `complete`
- Covered behavior:
  - `PetPickerPreviewState` shared mutable state, renderable wrapper, status setters, `clear`, `area`, and update semantics.
  - `PetPickerPreviewStatus` Hidden/Loading/Disabled/Ready/Error states.
  - Render semantics for loading, disabled, and error states with centered text plans and bold/dim line styles.
  - Hidden and Ready render paths return no text while render still records `last_area`.
  - `desired_height` fixed value and `centered_text_area` vertical centering/clamping.
- Adaptation note: Rust renders ratatui `Paragraph` into a `Buffer`; Python exposes a semantic `PreviewRenderPlan` instead of copying framework types.

### codex-tui pets/picker.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/picker.rs`
- Python module: `pycodex/tui/pets/picker.py`
- Python parity tests: `tests/test_tui_pets_picker.py`
- Status: `complete_slice`
- Covered behavior:
  - `PET_PICKER_VIEW_ID`, preview side-content width/min-width, disabled/default pet ids, and disabled search terms.
  - Built-in catalog entries plus synthetic disabled entry plus custom pet and legacy avatar manifest entries.
  - Custom-entry filtering for reserved ids, invalid manifests, and selector deduplication by `custom:<id>`.
  - Display-name sorting with disabled entry forced to index 0.
  - Initial selection and `is_current` matching for direct selectors and legacy custom ids.
  - Selection item search values, dismiss-on-select behavior, semantic `PetSelected` / `PetDisabled` actions, and `PetPreviewRequested` selection-change events.
  - Semantic selection params for title/subtitle/search/footer/side-content metadata.
- Boundary note: Rust returns concrete bottom-pane `SelectionViewParams`, callbacks, and `AppEventSender` closures. Python exposes semantic dataclasses and action/event plans instead of copying framework types.

### codex-tui pets/mod.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/pets/mod.rs`
- Python module: `pycodex/tui/pets/__init__.py`
- Python parity tests: `tests/test_tui_pets_mod.py`
- Status: `complete_slice`
- Covered behavior:
  - TUI-facing constants `DEFAULT_PET_ID`, `DISABLED_PET_ID`, picker view export, and ambient/preview image ids `0xC0DE` / `0xC0DF`.
  - `ensure_builtin_pack_for_pet` built-in-only dispatch, with injected ensure function for deterministic parity tests.
  - `PetImageRenderError` terminal vs asset classification, source preservation, and Rust display strings.
  - `PetImageRenderState` bookkeeping for last Kitty/Sixel protocol and last Sixel clear area.
  - Kitty and KittyLocalFile draw output order: delete previous image, save cursor, move, transmit payload/file reference, restore, flush.
  - `None` request clear behavior for Kitty and Sixel state, including cursor preservation for Sixel area clearing.
  - `SixelClearArea::from`, `clear_sixel_area`, and `is_kitty_protocol` semantics.
- Boundary note: real Sixel frame generation remains delegated to `image_protocol.sixel_frame` or an injected resolver; concrete crossterm queueing is represented with equivalent ANSI semantic output.

### codex-tui ide_context/prompt.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/ide_context/prompt.rs`
- Python module: `pycodex/tui/ide_context/prompt.py`
- Python parity tests: `tests/test_tui_ide_context_prompt.py`
- Status: `complete`
- Covered behavior:
  - IDE context prompt rendering with exact desktop delimiter `## My request for Codex:`.
  - Active file, active selection content, single/multiple selection ranges with 1-based line/column rendering.
  - Empty-context omission and `has_prompt_context` behavior.
  - Active selection truncation at 40,000 characters with Rust warning text.
  - Open tabs cap at 100 entries and 20,000 rendered characters with omitted-count line.
  - Applying context to the first text `UserInput` while preserving image/text order.
  - Text-element byte-range offset adjustment after prefix insertion.
  - Inserting a new text item when a request contains no existing text item.
  - Extracting the request and byte offset after the last prompt delimiter.
- Adaptation note: Python uses lightweight semantic `UserInputText`, `UserInputLocalImage`, `TextElement`, and `ByteRange` dataclasses plus duck-typed IDE context objects instead of importing app-server protocol classes.

### codex-tui onboarding/welcome.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/welcome.rs`
- Python module: `pycodex/tui/onboarding/welcome.py`
- Python parity tests: `tests/test_tui_onboarding_welcome.py`
- Status: `complete_slice`
- Covered behavior:
  - `MIN_ANIMATION_HEIGHT` / `MIN_ANIMATION_WIDTH` breakpoints and welcome-line text.
  - `WelcomeWidget::new`, layout-area update, animation suppression, animation scheduling, and semantic render lines.
  - Animation visibility only when enabled, not suppressed, and layout area meets width/height breakpoints.
  - Welcome row placement after current animation frame lines plus a blank separator.
  - Ctrl+. and Ctrl+Shift+. press handling for rotating animation variants; release events and disabled animations are ignored.
  - Step-state mapping: logged-in users hide the welcome step, logged-out users mark it complete.
- Adaptation note: Rust renders ratatui `Paragraph` and owns `AsciiAnimation`; Python exposes a semantic `WelcomeRenderPlan` and deterministic `AsciiAnimationModel` rather than copying framework types.

### codex-tui onboarding/trust_directory.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/trust_directory.rs`
- Python module: `pycodex/tui/onboarding/trust_directory.py`
- Python parity tests: `tests/test_tui_onboarding_trust_directory.py`
- Status: `complete_slice`
- Covered behavior:
  - `TrustDirectorySelection::{Trust, Quit}` and step state mapping to `InProgress` / `Complete`.
  - Release key events are ignored.
  - Up/down highlight routing, first/second selection shortcuts, cancel/quit routing, and Enter selecting the highlighted option.
  - `handle_trust` sets Trust highlight, clears error, and records Trust selection.
  - `handle_quit` sets Quit highlight and `should_quit`.
  - Semantic render plan for cwd line, Git-root warning, trust prompt, option rows, optional error, and Windows sandbox hint footer.
- Adaptation note: Rust renders ratatui `ColumnRenderable`/`Paragraph` snapshots; Python exposes a semantic render plan and option-row strings instead of copying framework buffer types.

### codex-tui onboarding/onboarding_screen.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/onboarding/onboarding_screen.rs`
- Python module: `pycodex/tui/onboarding/onboarding_screen.py`
- Python parity tests: `tests/test_tui_onboarding_onboarding_screen.py`
- Status: `complete_slice`
- Covered behavior:
  - `StepState`, `ApiKeyEntryContext`, semantic `Step`, `OnboardingScreen`, `OnboardingResult`, `OnboardingScreenArgs`.
  - Current-step selection: skip hidden, include complete, stop after first in-progress.
  - `is_done`, `is_auth_in_progress`, `should_suppress_animations`, auth widget lookup/cancel, app-server notification forwarding.
  - Top-level key routing: ignores release/non-press-repeat, quit handling, auth cancellation+exit, welcome pre-routing, active-step dispatch, trust quit propagation, frame scheduling.
  - Paste routing: ignore empty, dispatch to active step, frame scheduling.
  - API-key quit suppression for printable char with active non-empty entry and no ctrl/alt.
  - Trust persistence success/failure semantics: no app server -> clear selection, set error, keep step in progress; injected writer success -> true.
  - Semantic render step suppression/plan aggregation and `used_rows`.
- Boundary note: `OnboardingScreen::new`, `run_onboarding_app`, real `Tui`, `AppServerSession`, config/git-root resolution, and `write_trusted_project` side effects remain runtime boundaries. Python uses semantic step wrappers and injected writer for persistence tests.

### codex-tui status_indicator_widget.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/status_indicator_widget.rs`
- Python module: `pycodex/tui/status_indicator_widget.py`
- Python parity tests: `tests/test_tui_status_indicator_widget.py`
- Status: `complete_slice`
- Covered behavior:
  - `fmt_elapsed_compact` seconds/minutes/hours formatting.
  - `StatusDetailsCapitalization`, details trimming, capitalization, empty-detail clearing, and max-lines clamp to at least one.
  - Inline message trimming/empty suppression and interrupt event forwarding.
  - Pause/resume timer accumulation with saturating non-negative elapsed calculation and idempotent resume scheduling.
  - Interrupt binding remapping, hidden interrupt hint fallback, elapsed-only header suffix, and inline-message placement.
  - Details wrapping prefix, desired-height calculation, render height clipping, overflow ellipsis, zero-width/empty-area no-op, and animation frame scheduling boundary.
- Boundary note: Python represents ratatui `Line`/`Span`/`Buffer`, shimmer/activity glyphs, Unicode-width wrapping, and `Renderable` painting with semantic line/span values. Exact snapshot rendering remains a framework renderer boundary.

### codex-tui terminal_title.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/terminal_title.rs`
- Python module: `pycodex/tui/terminal_title.py`
- Python parity tests: `tests/test_tui_terminal_title.py`
- Status: `complete`
- Covered Rust tests/behavior:
  - `sanitize_terminal_title` whitespace collapse, leading/trailing whitespace trimming, and terminal control stripping.
  - Invisible/bidi formatting character removal for Trojan-Source-style title safety.
  - `MAX_TERMINAL_TITLE_CHARS` truncation and visible-character preference over pending whitespace at the boundary.
  - `SetWindowTitle::write_ansi` OSC 0 + BEL encoding.
  - `set_terminal_title` terminal/no-terminal result semantics and no-visible-content no-op.
  - `clear_terminal_title` empty OSC title payload.
- Boundary note: Python uses injectable `TextIO` streams for terminal/no-terminal behavior instead of direct `stdout().is_terminal()` and crossterm `execute!`, preserving the module-owned sanitization and OSC encoding contract without copying Rust framework types.

### codex-tui update_versions.rs - complete (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/update_versions.rs`
- Python module: `pycodex/tui/update_versions.py`
- Python parity tests: `tests/test_tui_update_versions.py`
- Status: `complete`
- Covered Rust tests/behavior:
  - `extract_version_from_latest_tag` strips the `rust-v` prefix and rejects tags without it.
  - `is_newer` parses plain major/minor/patch triples and returns `None` for malformed/prerelease versions.
  - Tuple ordering matches Rust `(u64, u64, u64)` comparisons.
  - `is_source_build_version` recognizes only parsed `0.0.0` as the source-build sentinel.
  - Whitespace is trimmed before parsing.
  - Python also records Rust-source edge behavior for malformed, signed, empty, u64-overflow, and extra-component version strings.
- Boundary note: This module is pure parsing/comparison logic; no runtime or framework boundary remains for the module-owned behavior.

### codex-tui update_prompt.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/update_prompt.rs`
- Python module: `pycodex/tui/update_prompt.py`
- Python parity tests: `tests/test_tui_update_prompt.py`
- Status: `complete_slice`
- Covered behavior:
  - `UpdatePromptOutcome` and `UpdateSelection` semantic variants.
  - `UpdateSelection::next` / `prev` cyclic navigation.
  - `UpdatePromptScreen::new`, default highlight, latest/current version storage, selection completion, and frame scheduling on highlight/selection changes.
  - Key handling for release filtering, Ctrl-C/Ctrl-D skip, Up/Down/k/j navigation, numeric shortcuts 1/2/3, Enter confirmation, and Esc skip.
  - Visible modal text contract: update title, current/latest version transition, release-notes URL, update command text, three options, and Enter hint.
  - `run_update_prompt_if_needed` decision flow with injected latest-version/update-action dependencies, run-update terminal clear, don't-remind dismissal, paste ignore, and draw/resize redraw hooks.
  - Corrected Python visible-contract expectation to match Rust's actual `npm install -g @openai/codex` command string.
  - 2026-06-13: added ratatui-bridge buffer rendering for the prompt body, including area clearing, styled title/version/release-notes/link rows, highlighted option rows, and WidgetRef-style `render_ref`.
- Boundary note: Python models the release-only async prompt loop with injected TUI/update providers. Concrete VT100 snapshots, terminal hyperlink OSC8 marking, and real `updates::get_upgrade_version_for_popup` / `get_update_action` side effects remain framework/runtime boundaries.

### codex-tui wrapping.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/wrapping.rs`
- Python module: `pycodex/tui/wrapping.py`
- Python parity tests: `tests/test_tui_wrapping.py`
- Status: `complete_slice`
- Covered behavior:
  - Semantic `RtOptions` width, initial/subsequent indent, break-words, no-hyphenation, and URL-preserving option adaptation.
  - `word_wrap_line`, `word_wrap_lines`, and borrowed/multi-line input behavior with semantic `Line`/`Span` values.
  - Empty input, leading spaces, repeated-space trimming between words, break_words=false overflow, hyphen splitting, wide-character display-width splitting, and styled-span split preservation.
  - URL-like token detection for schemes, custom schemes, bare domains, localhost, IPv4+ports, punctuation trimming, invalid ports, file-path rejection, and decorative-marker suppression for mixed URL/prose detection.
  - `adaptive_wrap_line` / `adaptive_wrap_lines` URL-preserving behavior for URL-only and mixed URL/prose lines, including wrapping long non-URL tokens while preserving URL tokens.
  - `wrap_ranges` / `wrap_ranges_trim` semantic byte-range reconstruction, trailing-space sentinel behavior, and partial owned-line recovery guardrails.
- Blocked sub-boundary: exact Rust `textwrap::Cow::{Borrowed,Owned}` pointer identity, inserted penalty-character recovery, and non-space synthetic-indent edge cases require a deeper textwrap-compatible engine. Python keeps semantic range reconstruction and records this as explicit parity debt rather than fabricating pointer-level behavior.

### codex-tui markdown.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/markdown.rs`
- Python module: `pycodex/tui/markdown.py`
- Python parity tests: `tests/test_tui_markdown.py`
- Status: `complete_slice`
- Covered behavior:
  - Public entry-point shape for `append_markdown`, `append_markdown_agent`, and `render_markdown_agent_with_links_and_cwd` with explicit delegation to `markdown_render`.
  - `unwrap_markdown_fences` conservative state machine for backtick/tilde fences, passthrough fences, markdown-candidate buffering, and unclosed markdown fence restoration.
  - Up-to-3-column fence indentation handling with tab/4-column rejection.
  - Markdown fence info detection for `md` / `markdown`, including blockquoted fence opening/closing.
  - Markdown fence table detection requiring adjacent header + delimiter lines; blank lines reset the candidate header.
  - Table-containing markdown fences are unwrapped to bare markdown; non-markdown fences, markdown fences without tables, non-adjacent delimiter cases, and unclosed fences remain unchanged.
  - Helper semantic models for `Fence`, `MarkdownCandidateData`, and active-fence state.
- Boundary note: Full markdown-to-ratatui rendering is owned by `markdown_render.rs` and remains an explicit dependency boundary. Python entry points delegate to `pycodex.tui.markdown_render` and propagate its `NotImplementedError` rather than fabricating rendered output.

### codex-tui resume_picker/transcript.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/resume_picker/transcript.rs`
- Python module: `pycodex/tui/resume_picker/transcript.py`
- Python parity tests: `tests/test_tui_resume_picker_transcript.py`
- Status: `complete_slice`
- Covered behavior:
  - `RawReasoningVisibility::{Hidden,Visible}` and semantic `TranscriptCell` / `TranscriptCells` models for Rust `Vec<Arc<dyn HistoryCell>>`.
  - `load_session_transcript` calls `thread_read(thread_id, include_turns=true)` and converts the returned thread.
  - `thread_to_transcript_cells` walks turns/items, maps user messages, agent visible markdown after git-action directive stripping, non-empty plans, reasoning summary/raw-content selection, and empty transcript fallback.
  - Fallback transcript cells for hook prompts, command executions, file changes, MCP tool calls, dynamic tool calls, collab-agent tool calls, web search, image view, image generation, review enter/exit, and context compaction.
  - Owned core item variants (`UserMessage`, `AgentMessage`, `Plan`, `Reasoning`) are not duplicated through fallback handling.
- Boundary note: Python uses semantic transcript cell DTOs instead of Rust `HistoryCell` trait objects, `Arc`, ratatui `Line`, or concrete history-cell renderers. Exact display/render behavior stays owned by `history_cell` child modules and renderer/framework slices.

### codex-tui keymap_setup/debug.rs - complete_slice (2026-06-12)

- Rust module: `codex/codex-rs/tui/src/keymap_setup/debug.rs`
- Python module: `pycodex/tui/keymap_setup/debug.py`
- Python parity tests: `tests/test_tui_keymap_setup_debug.py`
- Status: `complete_slice`
- Covered behavior:
  - `MISSING_KEY_HINT_DELAY`, short/delayed missing-key hint text, and delayed-hint timing before any key report.
  - `KeymapDebugView` construction, initial waiting lines, semantic render lines, desired height, and wrapping helper.
  - Release key events are ignored; press/repeat-like events create a `KeymapDebugReport` with detected binding, config key, raw event summary, and matching actions.
  - Modifier debug labels use Rust order: ctrl, alt, shift, then other modifiers; empty modifiers render as `none`.
  - Assigned action rows include context, action, label, description, and source label; empty matches render `none`.
  - `on_ctrl_c` completes the view and returns handled cancellation semantics; Esc is preferred for inspection; next-frame delay is scheduled only until the delayed hint/report.
- Boundary note: Python uses semantic text lines and duck-typed/injected keymap action matches instead of Rust `RuntimeKeymap`, `TuiKeymap`, `BottomPaneView`, ratatui `Line`, or full parent `keymap_setup` key-spec serialization. Those neighboring modules remain separate behavior contracts.


### codex-tui keymap_setup/actions.rs - complete_slice (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/keymap_setup/actions.rs`.
- Python module: `pycodex/tui/keymap_setup/actions.py`.
- Python parity tests: `tests/test_tui_keymap_setup_actions.py`.
- Status: `complete_slice`.
- Covered behavior: keymap action descriptor/filter semantics, FastMode-gated visibility, full action catalog as a semantic tuple, Rust-style `action_label`, semantic config/runtime binding lookup, sorted deduplicated binding summaries with `unbound`, debug binding source precedence, and matching-action reports for key events.
- Boundary note: Python uses plain mapping/object paths and semantic binding adapters instead of Rust mutable references, `TuiKeymap`, `RuntimeKeymap`, `KeyBinding`, and crossterm key-event types; parent key-spec serialization remains a separate module boundary.


### codex-tui terminal_hyperlinks.rs - complete_slice update (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/terminal_hyperlinks.rs`.
- Python module: `pycodex/tui/terminal_hyperlinks.py`.
- Python parity tests: `tests/test_tui_terminal_hyperlinks.py::test_adaptive_wrap_hyperlink_lines_remaps_links_after_wrapping`.
- Status: `complete_slice`.
- Covered behavior: `adaptive_wrap_hyperlink_lines` now mirrors Rust's module-owned flow by applying `wrapping::adaptive_wrap_line`, switching later source lines to the subsequent indent, and remapping hyperlink column ranges through `remap_wrapped_line`.
- Boundary note: exact ratatui paragraph/buffer wrapping remains renderer-level debt; this update closes the prior explicit `not_ported` helper inside the Python terminal hyperlink semantic model.


### codex-tui history_cell/mod.rs - complete_slice (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/history_cell/mod.rs`.
- Python module: `pycodex/tui/history_cell/__init__.py`.
- Python parity tests: `tests/test_tui_history_cell_mod.py`.
- Status: `complete_slice`.
- Covered behavior: shared history-cell constants, `HistoryRenderMode::{Rich, Raw}`, `raw_lines_from_source` newline splitting including trailing-newline removal, `plain_lines` span flattening, default rich/raw display helpers, default hyperlink-line conversion, semantic wrapped height calculation, transcript whitespace height clamp, and default stream/animation methods.
- Boundary note: concrete child history-cell renderers remain separate module contracts; ratatui `Renderable for Box<dyn HistoryCell>` buffer mutation remains an explicit framework boundary instead of a fabricated render side effect.


### codex-tui bottom_pane/command_popup.rs - complete_slice update (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/bottom_pane/command_popup.rs`.
- Python module: `pycodex/tui/bottom_pane/command_popup.py`.
- Python parity tests: `tests/test_tui_bottom_pane_command_popup.py`.
- Status: `complete_slice`.
- Covered behavior: command popup flags conversion, built-in/service-tier command item model, command catalog filtering, alias hiding only for empty filters, exact-before-prefix ordering, prefix match indices shifted for displayed slash, first-line composer filter extraction, selection movement, row construction, and required-height delegation.
- Cleanup: removed generated Rust test-name `not_ported` scaffolds from the Python module because they were not Rust public APIs; the behavior is covered by parity tests instead.
- Boundary note: ratatui `WidgetRef` buffer rendering remains represented by semantic row rendering/inset helpers rather than exact terminal cell mutation.


### codex-tui chatwidget/mcp_startup.rs - complete_slice (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/chatwidget/mcp_startup.rs`.
- Python module: `pycodex/tui/chatwidget/mcp_startup.py`.
- Python parity tests: `tests/test_tui_chatwidget_mcp_startup.py`.
- Status: `complete_slice`.
- Covered behavior: MCP startup header prefixes, `McpStartupStatus` variants including failed errors, expected-server registration, active-round status updates, single/multi header progress formatting, settled-round completion, failed/cancelled warning text, queued-input release point, lag completion with missing/starting servers as cancelled, ignore-mode pending next-round promotion, and app-server notification status conversion with default failed error text.
- Boundary note: Python uses `McpStartupModel` as a semantic stand-in for the Rust `ChatWidget` fields/method side effects; full widget rendering, app-server transport, and bottom-pane runtime integration remain separate module/runtime boundaries.


### codex-tui chatwidget/pets.rs - complete_slice (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/chatwidget/pets.rs`.
- Python module: `pycodex/tui/chatwidget/pets.py`.
- Python parity tests: `tests/test_tui_chatwidget_pets.py`.
- Status: `complete_slice`.
- Covered behavior: ambient pet load gating for unset/disabled ids and loader errors, configured pet load gating and event emission, pet notification forwarding, ambient image enablement/reserved columns/history width, modal-gated draw requests, session disable redraw, unsupported warning gates for picker/select, picker preview request id wrapping model, disabled/loading/ready/error preview states, stale preview-result rejection, preview image visible/clear flag, render-failure state, selection loading popup request id and dismissal behavior.
- Boundary note: real built-in pack ensure/load, terminal image rendering, async tokio/thread spawning, and full `ChatWidget`/`BottomPane` integration are represented by semantic models and injectable loader/event boundaries rather than fabricated runtime side effects.


### codex-tui chatwidget/slash_dispatch.rs - complete_slice (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs`.
- Python module: `pycodex/tui/chatwidget/slash_dispatch.py`.
- Python parity tests: `tests/test_tui_chatwidget_slash_dispatch.py`.
- Status: `complete_slice`.
- Covered behavior: dispatch source enum, prepared slash-command argument payload model, user-facing usage/side-start constants, side-conversation and review-mode guard messages with drain flags, queued command drain continue/stop set, inline slash argument text-element byte-range remapping, prepared inline user-message construction, and pure argument classifiers for `/raw`, `/mcp`, `/keymap`, and `/pets`.
- Boundary note: full `ChatWidget::dispatch_command`, app-event transport, UI popups, async git diff, goal mutation, and runtime command side effects remain explicit neighboring runtime contracts; this slice only ports module-owned pure dispatch decisions and data shaping.


### codex-tui chatwidget/plan_implementation.rs - complete (2026-06-12)
- Rust module: `codex/codex-rs/tui/src/chatwidget/plan_implementation.rs`.
- Python module: `pycodex/tui/chatwidget/plan_implementation.py`.
- Python parity tests: `tests/test_tui_chatwidget_plan_implementation.py`.
- Status: `complete`.
- Covered behavior: all module constants, confirmation title/items/descriptions, standard footer hint placeholder, default-mode unavailable disabling, clear-context plan availability validation using trim, usage-label-specific clear-context description, and semantic action payloads for `SubmitUserMessageWithMode` and `ClearUiAndSubmitUserMessage`.
- Boundary note: Python uses semantic `SelectionViewParamsPlan`/`SelectionItemPlan`/`SelectionActionPlan` records instead of Rust closure-based `SelectionAction` and app-event sender types; no remaining module-owned behavior is left unimplemented.

### codex-tui chatwidget/realtime.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/realtime.rs`.
- Python target: `pycodex/tui/chatwidget/realtime.py`.
- Python parity tests: `tests/test_tui_chatwidget_realtime.py`.
- Status: `complete_slice`.
- Covered behavior: realtime conversation phase helpers, websocket/WebRTC transport state, start/close/reset/fail transitions, footer hints, semantic operation submission, started/audio/item/error/closed notifications, WebRTC offer/SDP/event handling, deleted-meter close guard, and semantic task hooks.
- Boundary note: real WebRTC sessions, microphone capture, audio playback, recording-meter background loops, AppCommand/AppEvent channels, and ratatui rendering are represented by semantic records or injected hooks rather than silently fabricated.

### codex-tui chatwidget/input_restore.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/input_restore.rs`.
- Python target: `pycodex/tui/chatwidget/input_restore.py`.
- Python parity tests: `tests/test_tui_chatwidget_input_restore.py`.
- Status: `complete_slice`.
- Covered behavior: initial-message suppression/submission, next/latest queued-message pop order, rejected-steer enqueueing, history override restoration, pending/rejected/queued/composer merge order, interrupted-turn submit-vs-restore paths, composer restore, thread input capture/restore, missing history-record defaults, pending compare-key defaults, queue autosend suppression, and semantic merge helpers.
- Boundary note: concrete `ChatWidget`, bottom-pane composer implementation, history-cell rendering, collaboration-mode concrete types, and exact Rust text-element byte-range/image-placeholder remapping fidelity remain neighboring/runtime boundaries.

### codex-tui chatwidget/plugins.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/plugins.rs`.
- Python target: `pycodex/tui/chatwidget/plugins.py`.
- Python parity tests: `tests/test_tui_chatwidget_plugins.py`.
- Status: `complete_slice`.
- Covered behavior: plugin UI constants, loading header height/line semantics, cache/fetch/auth-flow DTOs, marketplace tab IDs and saved-ID matching, duplicate tab label disambiguation, marketplace/plugin display-name fallback, status labels, brief descriptions, marketplace/plugin entry collection and sorting, detail descriptions, skills/apps/hooks/MCP summaries, popup hint strings, header tuple, and user-configured marketplace helpers.
- Boundary note: full `ChatWidget` plugin popup orchestration, bottom-pane selection views, app-server marketplace/install/uninstall/upgrade requests, custom prompt callbacks, ratatui rendering, hyperlink marking, and real marketplace configuration layers remain explicit runtime/dependency boundaries.

### codex-tui chatwidget/session_flow.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/session_flow.rs`.
- Python target: `pycodex/tui/chatwidget/session_flow.py`.
- Python parity tests: `tests/test_tui_chatwidget_session_flow.py`.
- Status: `complete_slice`.
- Covered behavior: normal/quiet/side session handlers, instruction-source path capture, session metadata application, thread-id/name/cwd/workspace/permission/service-tier state updates, collaboration-mode default/effective paths, review-denial reset on thread switch, normal session header plan, quiet/side session-header clearing, initial-message submit/suppress behavior, forked-thread history event formatting, redraw suppression, connector prefetch gating, skill reset/reload recording, and thread-name update handling.
- Boundary note: concrete `ChatWidget`, permission constraint mutation, history-cell construction, transcript internals, status surface rendering, model catalog lookup, connector fetch implementation, and app-event transport remain explicit neighboring/runtime boundaries.

### codex-tui chatwidget/tool_lifecycle.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/tool_lifecycle.rs`.
- Python target: `pycodex/tui/chatwidget/tool_lifecycle.py`.
- Python parity tests: `tests/test_tui_chatwidget_tool_lifecycle.py`.
- Status: `complete_slice`.
- Covered behavior: patch begin history insertion, view-image/image-generation stream flush and history behavior, file-change completion success/failure handling, MCP started/completed active-cell lifecycle, MCP result/error/no-result shaping, web-search active/fallback completion, collab event flushing/redraw, collab spawn-request caching/removal, defer-or-handle queueing, and queued started/completed dispatch for command/MCP/file-change variants.
- Boundary note: concrete history cell classes, ratatui rendering, command execution lifecycle internals, full deferred turn queue integration, multi-agent metadata lookup, AppEvent transport, and real transcript cell downcasting remain explicit neighboring/runtime boundaries.

### codex-tui chatwidget/tool_requests.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/tool_requests.rs`.
- Python target: `pycodex/tui/chatwidget/tool_requests.py`.
- Python parity tests: `tests/test_tui_chatwidget_tool_requests.py`.
- Status: `complete_slice`.
- Covered behavior: defer-or-handle routing for exec/apply-patch/elicitation/user-input/permission requests, exec approval command notification and request shaping, apply-patch approval request and edit notification, guardian in-progress footer aggregation and terminal approved/timed-out/denied history decisions, recent guardian denial tracking, guardian action summaries and command extraction, elicitation app-link/form/decline/approval routing, user-input prompt title selection, permission request shaping, ambient waiting notification, stream flushes, and redraw requests.
- Boundary note: concrete bottom-pane approval/form/user-input views, AppServer elicitation URL/form constructors, history-cell rendering, feature gating, shlex parity edge cases, pet notification rendering, and app-event transport remain explicit neighboring/runtime boundaries.

### codex-tui chatwidget/input_flow.rs - complete_slice (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/input_flow.rs`.
- Python target: `pycodex/tui/chatwidget/input_flow.py`.
- Python parity tests: `tests/test_tui_chatwidget_input_flow.py`.
- Status: `complete_slice`.
- Covered behavior: composer `InputResult` dispatch, empty-submit early return, immediate submit versus queue decision, user-shell-only running command queue guard, queued input actions, queue-submission gating before session configuration, maybe-send-next queue draining for plain/slash/shell actions, autosend suppression, pending/running turn guards, pending-input preview refresh, user-turn pending state, plan-mode reasoning effort override, collaboration-mode switch rejection while running, plan-streaming queue behavior, and queued-message text snapshot.
- Boundary note: concrete bottom-pane composer snapshots, slash command parsing/execution, shell prompt execution, command runtime state, input queue preview formatting, collaboration-mode concrete structs, and status rendering remain explicit neighboring/runtime boundaries.

### codex-tui chatwidget/turn_lifecycle.rs - complete (2026-06-13)
- Rust source: `codex/codex-rs/tui/src/chatwidget/turn_lifecycle.rs`.
- Python target: `pycodex/tui/chatwidget/turn_lifecycle.py`.
- Python parity tests: `tests/test_tui_chatwidget_turn_lifecycle.py`.
- Status: `complete`.
- Covered behavior: `TurnLifecycleState::new`, `start`, `finish`, `restore_running`, `reset_thread`, `set_prevent_idle_sleep`, `mark_budget_limited`, `take_budget_limited`, semantic `SleepInhibitor` turn-running state, and Rust unit-test behavior for start/finish plus budget-limited consumption.
- Boundary note: the OS-level sleep inhibitor side effect is represented by a semantic `SleepInhibitor`; there is no remaining module-owned behavior blocked by ratatui or other TUI runtime dependencies.
| `chatwidget/replay.rs` | `replay_thread_turns`, `replay_thread_item`, `handle_thread_item`; turn start/completion replay ordering, replay render-source dispatch, item variant routing, reasoning replay gating, no-op variants, unknown variant rejection, snapshot redraw | `tests/test_tui_chatwidget_replay.py::{test_replay_thread_turns_starts_in_progress_and_completes_terminal_turn,test_handle_thread_item_replays_reasoning_summary_and_optionally_raw_content,test_handle_thread_item_routes_status_sensitive_tool_items,test_handle_thread_item_skips_in_progress_file_change_and_noop_variants,test_thread_snapshot_without_turn_id_requests_redraw_after_dispatch,test_unknown_thread_item_variant_is_rejected}` | complete_slice | Python uses semantic DTOs/callback protocol instead of Rust app-server/ratatui types; surrounding live widget state is intentionally outside this module boundary. |
| `chatwidget/settings.rs` | Feature setting side effects, Plan/non-Plan reasoning effort scope, realtime audio device getters/labels, effective model/collaboration mask behavior, Plan-mode nudge visibility policy, model display/image unsupported message | `tests/test_tui_chatwidget_settings.py::{test_set_model_updates_collaboration_state_and_refreshes_surfaces,test_reasoning_effort_updates_non_plan_mask_but_plan_override_is_separate,test_feature_side_effects_match_rust_settings_branches,test_realtime_audio_device_helpers_use_system_default_label,test_plan_mode_nudge_policy_filters_commands_running_state_and_dismissal,test_collaboration_mask_applies_plan_override_dismisses_nudge_and_reports_model_change,test_display_name_and_image_error_message_use_effective_model}` | complete_slice | Python uses semantic DTOs and widget callback hooks rather than the full Rust `ChatWidget`. Thread settings sync, permission constraints, Windows sandbox, app-event submission, account/connectors, and catalog-backed support checks remain explicit integration debt. |
| `chatwidget/permission_popups.rs` | Permission popup preset construction, guardian auto-review item, full-access confirmation gating/options, profile-selection action, preset current-state matching, auto-review denials popup and approval event semantics | `tests/test_tui_chatwidget_permission_popups.py::{test_open_permissions_popup_builds_current_agent_and_guardian_auto_review_item,test_permission_mode_actions_require_confirmation_for_unacknowledged_full_access,test_permission_mode_actions_apply_selection_when_profile_selection_is_present,test_preset_matches_current_special_cases_full_read_only_and_auto,test_open_full_access_confirmation_builds_accept_remember_and_cancel_actions,test_open_auto_review_denials_popup_empty_and_nonempty_paths}` | complete_slice | Python returns semantic selection DTOs and declarative `AppEvent`s instead of Rust ratatui renderables and boxed tx closures. Windows sandbox prompts, world-writable warning confirmation, and concrete event transport remain explicit integration debt. |
| `chatwidget/protocol.rs` | Server notification dispatcher; replay-aware status restoration, turn started/completed state transitions, item started/completed routing, raw reasoning gating, retry/non-retry error handling, side-conversation MCP suppression, realtime replay suppression, no-op notification variants | `tests/test_tui_chatwidget_protocol.py::{test_handle_server_notification_turn_started_sets_turn_id_and_skips_resume_start,test_handle_turn_completed_completed_interrupted_and_failed_paths,test_error_notification_retry_live_only_and_non_retry_records_error,test_reasoning_raw_delta_obeys_config_and_completed_item_uses_replay_source,test_item_started_routes_replay_sensitive_review_and_tool_starts,test_side_conversation_suppresses_live_mcp_status_and_realtime_suppressed_during_replay}` | complete_slice | Python uses dict/object-friendly semantic notifications and widget callbacks instead of Rust app-server enums. Token usage conversion, ThreadId parsing, file display conversion, and full app-server integration remain explicit debt. |
| `chatwidget/protocol_requests.rs` | Server request dispatch for approval/permissions/elicitation/user-input flows, live-only stub errors, skills-list response routing, guardian review assessment conversion, shutdown/turn-diff/deprecation helper side effects, ignored patch output delta | `tests/test_tui_chatwidget_protocol_requests.py::{test_handle_server_request_routes_approval_permission_elicitation_and_user_input,test_stub_request_variants_emit_error_only_when_live,test_guardian_review_notification_maps_status_risk_auth_and_completion,test_small_notification_helpers_match_rust_side_effects}` | complete_slice | Python uses semantic request dicts/DTOs and callback hooks. Exact app-server DTO conversion, guardian action enum conversion, tracing, and real transport remain explicit integration debt. |
| `chatwidget/skills.rs` | Skill list/menu flows, manage-skills state delta summary, cwd skill filtering, enabled skill conversion, SKILL.md read annotation, tool mention parsing, skill/app mention matching, accessible/enabled app filtering Rust tests | `tests/test_tui_chatwidget_skills.py::{test_collect_tool_mentions_parses_plain_and_linked_mentions_skipping_env_vars,test_linked_tool_mention_parser_and_path_helpers_match_rust_rules,test_find_skill_mentions_prefers_bound_paths_then_names_and_dedupes,test_find_app_mentions_requires_accessible_enabled_apps_for_slugs_and_bound_paths,test_find_app_mentions_rejects_ambiguous_slug_and_skill_name_collision,test_skill_response_mapping_and_enabled_mentions,test_widget_skill_menu_manage_update_and_close_semantics,test_set_skills_from_response_updates_all_and_enabled_mentions}` | complete_slice | Python uses semantic DTOs and simplified connector slugging. Exact serde scope conversion, full connector metadata slug parity, ratatui toggle view wiring, and real event transport remain explicit integration debt. |
| `chatwidget/transcript.rs` | `TranscriptState` state contract, active-cell revision wrapping, agent markdown copy history replacement/capping, visible user turn count, copy history reset/truncate rollback behavior, reset turn flags; Rust tests `active_cell_revision_wraps`, `copy_history_tracks_latest_visible_turn` | `tests/test_tui_chatwidget_transcript.py::{test_active_cell_revision_wraps_like_rust_wrapping_add,test_copy_history_tracks_latest_visible_turn_after_rollback,test_record_agent_markdown_replaces_same_visible_turn_and_caps_history,test_reset_copy_history_clears_copy_state,test_truncate_copy_history_marks_evicted_when_all_history_removed,test_reset_turn_flags_preserves_separator_and_plan_progress_like_rust}` | complete | Full module-local behavior is state-only and ported. `active_cell` is intentionally opaque because concrete rendering is owned by neighboring history-cell modules. |
| `chatwidget/settings_popups.rs` | Theme picker surface delegation, personality popup guards and choices, realtime audio popup/device/restart selection items, experimental feature menu filtering, personality label/description helpers | `tests/test_tui_chatwidget_settings_popups.py::{test_open_theme_picker_delegates_or_builds_semantic_placeholder,test_open_personality_popup_guards_startup_and_model_support_then_builds_items,test_realtime_audio_popup_and_device_selection_match_current_state,test_realtime_audio_restart_prompt_builds_restart_and_apply_later_choices,test_open_experimental_popup_filters_specs_without_menu_metadata,test_personality_labels_and_descriptions_match_rust_strings}` | complete_slice | Python uses semantic DTOs/actions. Rust ratatui renderables, actual theme picker construction, OS audio enumeration, event channel closures, and concrete experimental view wiring remain explicit UI integration debt. |
| `chatwidget/input_submission.rs` | User message construction, shell command submission/help/history, queued shell prompt dispatch, pre-session queueing, empty input rejection, unsupported image restore, shell escape policy, user-turn item construction, mention-derived skill/app/plugin inputs, unavailable model restore, history mention encoding, pending steer during running turns | `tests/test_tui_chatwidget_input_submission.py::{test_user_message_from_submission_drains_images_urls_and_bindings,test_shell_command_empty_shows_help_and_nonempty_submits_with_history,test_user_message_queues_when_session_not_configured_and_rejects_empty,test_blocked_image_submission_restores_payload_and_warns,test_shell_escape_policy_can_return_app_command_without_model_turn,test_user_turn_items_history_display_and_mentions_are_submitted,test_running_turn_records_pending_steer_instead_of_displaying_history,test_unavailable_model_restores_message_and_does_not_submit}` | complete_slice | Python uses semantic `AppCommand`/`UserInput` DTOs. Exact core permission/service-tier DTO construction, IDE context expansion, text-element conversion, and app-server transport remain explicit integration debt. |
| `chatwidget/interaction.rs` | Attach-image guard, composer/external edit/selection helpers, Ctrl+L running-task guard, copy-last-agent markdown branches, paste burst scheduling, Ctrl+C realtime/handled/interrupt/double-quit behavior, Ctrl+D empty-composer quit behavior, active-goal pause on interrupt | `tests/test_tui_chatwidget_interaction.py::{test_attach_image_warns_when_model_lacks_support_otherwise_attaches,test_copy_last_agent_markdown_success_error_empty_and_evicted_paths,test_ctrl_l_clear_blocks_while_task_running,test_paste_and_selection_helpers_refresh_nudge_and_redraw,test_paste_burst_tick_flushes_or_schedules_or_allows_render,test_ctrl_c_stops_realtime_or_arms_interrupts_and_double_press_quits,test_ctrl_c_bottom_pane_handled_modal_clears_or_arms_hint,test_ctrl_d_only_arms_when_composer_empty_and_modal_clear_then_second_press_quits}` | complete_slice | Python uses semantic key/command DTOs and injectable copy backend. Full key-event routing, keymap matching, OS image paste, concrete clipboard lease, rename prompt view construction, and real timing integration remain explicit UI debt. |
| `chatwidget/constructor.rs` | ChatWidget construction slice: app-event target delegation, model trim/filter/config writeback, header/collaboration initialization, transcript active-cell setup, bottom-pane params, welcome/current-cwd/prevent-idle-sleep state, post-construction sync calls | `tests/test_tui_chatwidget_constructor.py::{test_new_with_app_event_delegates_to_app_event_target_and_filters_blank_model,test_new_with_op_target_uses_model_override_for_mask_header_and_collaboration_mode,test_bottom_pane_params_and_transcript_active_cell_are_wired,test_post_construct_sync_calls_bottom_pane_and_widget_hooks}` | complete_slice | Python uses semantic `ConstructedChatWidget` and recording bottom pane. Full Rust field inventory, keymap parsing, service-tier resolution, pets startup, terminal info, rate-limit prefetch, Windows sandbox wiring, and concrete UI construction remain explicit integration debt. |
| `chatwidget/rendering.rs` | Render composition for transcript/hook/bottom pane, right reserve and inset layout, transcript child area and overflow scroll, bottom-pane reserve delegation, desired height/cursor/style, last-rendered width update | `tests/test_tui_chatwidget_rendering.py::{test_transcript_area_child_area_saturates_width_height_and_adds_top,test_transcript_area_render_scrolls_to_bottom_when_lines_overflow,test_bottom_pane_composer_reserve_delegates_render_height_cursor_and_style,test_chatwidget_render_composes_active_hook_and_bottom_and_records_width,test_desired_height_cursor_pos_and_style_delegate_to_composed_renderable}` | complete_slice | Python uses semantic `Rect`/`RenderLog` rather than ratatui `Buffer`/`Paragraph`/`Clear`; concrete terminal drawing remains explicit backend debt. |
| `chatwidget/tests.rs` | Test-only aggregation facade: `chatwidget_snapshot_dir`, snapshot macro naming/path semantics, declared test submodules, helper re-export names | `tests/test_tui_chatwidget_tests_module.py::{test_chatwidget_snapshot_dir_matches_rust_resource_parent,test_snapshot_assertion_models_rust_macro_name_and_directory_binding,test_declared_test_modules_and_reexported_helpers_match_rust_tests_rs}` | complete_slice | Rust module is test support, not production TUI behavior. Python ports the aggregation/helper boundary; child Rust test modules remain parity evidence for their owning production modules. |
| `app/tests.rs` | test-only aggregation facade: child module declarations, snapshot macro path binding, absolute-path helper, line flattening helper, helper inventories, drop-notification helper, heavyweight fixture boundaries | `tests/test_tui_app_tests_module.py::{test_declared_test_modules_match_rust_mod_declarations,test_snapshot_assertion_models_rust_macro_binding,test_absolute_path_accepts_only_absolute_paths,test_lines_to_single_string_flattens_simple_line_shapes,test_helper_and_heavyweight_fixture_boundaries_are_declared,test_notify_on_drop_semantic_helper_marks_drop}` | complete_slice | Rust module is app-level test support and integration-test aggregation, not production App behavior. Python ports the aggregation/helper boundary while leaving full async App/AppServer fixture construction explicit `not_ported`. |
| `chatwidget/notifications.rs` | notification display/type/priority/filtering, pending notification coalescing, agent-turn preview, user-input request summary | `tests/test_tui_chatwidget_notifications.py::{test_agent_turn_preview_normalizes_whitespace_and_empty_falls_back,test_notification_display_strings_match_rust_variants,test_allowed_for_enabled_and_custom_settings,test_coalescer_preserves_higher_priority_pending_notification,test_coalescer_replaces_equal_or_lower_priority_and_requests_redraw,test_user_input_request_summary_uses_header_then_question}` | complete_slice | Python ports module-local notification semantics with a semantic coalescer. Actual TUI desktop notification delivery remains a backend boundary. |
| `chatwidget/service_tiers.rs` | service-tier state helpers, fast-mode toggle gating, tier command extraction, toggle/persist events, fast status visibility | `tests/test_tui_chatwidget_service_tiers.py::{test_service_tier_commands_lowercase_catalog_names,test_fast_toggle_updates_and_persists_local_service_tier,test_service_tier_toggle_turns_selected_tier_back_to_default,test_fast_keybinding_toggle_requires_feature_and_idle_surface,test_should_show_fast_status_requires_fast_supported_and_chatgpt_account,test_set_service_tier_refreshes_effective_tier_and_surfaces}` | complete_slice | Python uses a semantic ChatWidget service-tier state and event records. AppEvent transport, full model catalog runtime, and widget surface integration remain surrounding boundaries. |
| `chatwidget/review_popups.rs` | review preset popup, branch picker, commit picker, custom prompt metadata and trimmed submit action | `tests/test_tui_chatwidget_review_popups.py::{test_open_review_popup_builds_four_presets_in_rust_order,test_branch_picker_uses_current_branch_arrow_names_and_search_values,test_branch_picker_uses_detached_head_fallback,test_commit_picker_shows_subjects_without_timestamps_and_searches_sha,test_custom_prompt_view_metadata_and_trimmed_submit_behavior}` | complete_slice | Python ports semantic selection-view/action payload construction. Async git lookup and concrete bottom-pane CustomPromptView rendering remain dependency/runtime boundaries. |
| `chatwidget/model_popups.rs` | model picker filtering/sorting, all-models fallback, reasoning popup choices/defaults/warnings, Plan-mode scope prompt, helper labels and custom OpenAI base URL warning | `tests/test_tui_chatwidget_model_popups.py::{test_model_popup_filters_hidden_models_and_sorts_auto_models,test_all_models_popup_empty_returns_info_message,test_reasoning_popup_single_supported_effort_applies_immediately,test_reasoning_popup_multiple_choices_marks_default_current_and_warning,test_plan_mode_reasoning_scope_prompt_gate_matches_rust_noop_rules,test_plan_reasoning_scope_prompt_builds_two_action_paths_and_notifies,test_small_helpers_match_rust_literals}` | complete_slice | Python ports module-owned popup planning and event-shaping semantics. Concrete ChatWidget mutation, ratatui header rendering, model catalog fetch errors, and AppEvent transport remain boundaries. |
| `chatwidget/streaming.rs` | reasoning header extraction/status restore, stream-idle restore gate, reasoning delta/final buffering, stream error status, message completion restore flags, active stream-tail predicates | `tests/test_tui_chatwidget_streaming.py::{test_extract_first_bold_matches_rust_wait_for_closing_behavior,test_restore_reasoning_status_header_prefers_bold_header_then_working,test_restore_status_indicator_waits_for_pending_running_and_idle,test_reasoning_delta_updates_header_unless_exec_wait_streak_precedes_it,test_reasoning_section_break_and_final_record_transcript_only_summary,test_agent_message_completion_restore_flag_depends_on_phase,test_active_stream_tail_requires_controller_and_tail_cell_then_clear_bumps_revision}` | complete_slice | Python models streaming state transitions without fabricating stream-controller commit ticks, ratatui history cells, or app-event animation transport. |
| `history_cell/tests.rs` | test-support fixture helpers: small PNG, temp cwd/config, MCP config builders, TOML string map conversion, line/transcript flattening, unstyled assertion, content block builders, rendering-test inventory | `tests/test_tui_history_cell_tests_module.py::{test_test_cwd_and_png_fixture_match_rust_intent,test_mcp_server_config_helpers_build_semantic_tables,test_render_lines_and_transcript_flatten_line_shapes,test_assert_unstyled_lines_accepts_default_and_rejects_styled_spans,test_content_block_helpers_match_rust_rmcp_fixture_intent,test_helper_and_rendering_test_inventories_document_module_boundary}` | complete_slice | Rust module is test support/evidence for history-cell rendering, not production rendering ownership. Python ports reusable fixture helpers and records that concrete rendering snapshot behaviors belong to their respective history_cell modules. |
| `status/tests.rs` | test-support fixtures: workspace-write permission profile, temp config/cwd workspace roots, account display, token usage info, line flattening, directory sanitization, reset timestamps, snapshot-test inventory | `tests/test_tui_status_tests_module.py::{test_workspace_write_profile_matches_rust_shape,test_set_workspace_cwd_updates_roots_and_permissions,test_render_lines_and_sanitize_directory_helpers,test_reset_at_from_returns_utc_timestamp,test_token_info_and_account_display_helpers,test_snapshot_inventory_documents_status_module_ownership}` | complete_slice | Rust module is status snapshot/test support, not production status-card rendering ownership. Python ports reusable helpers and records snapshot tests as evidence for production status modules. |
| `markdown_render_tests.rs` | test-support helpers: `render_markdown_text_for_cwd`, `plain_lines`, and categorized markdown-render behavior inventory | `tests/test_tui_markdown_render_tests_module.py::{test_plain_lines_flattens_text_line_span_shapes,test_markdown_render_test_categories_document_renderer_evidence,test_render_markdown_text_for_cwd_delegates_to_renderer_boundary}` | complete_slice | Rust module is renderer evidence/test support, not production renderer ownership. Python ports reusable helpers and records the Rust test categories while production behavior remains in `markdown_render.rs`. |
| `keymap_setup/picker.rs` | keymap picker construction: visible action filtering, all/common/custom/unbound/context/debug tabs, header/count/hint text, row prefix indicators, search values, selected row, semantic action events | `tests/test_tui_keymap_setup_picker.py::{test_build_keymap_rows_filters_fast_mode_and_marks_custom_unbound,test_build_keymap_picker_params_matches_rust_picker_surface_shape,test_fast_mode_filter_selected_action_and_common_rows_follow_rust_order,test_selected_action_starts_on_matching_all_tab_row,test_selection_item_and_debug_tab_emit_semantic_events,test_action_count_line_and_picker_inventory_are_stable}` | complete_slice | Python models `SelectionViewParams`/tabs/items and AppEvent payloads as dataclasses instead of ratatui renderables and channels; concrete bottom-pane integration remains runtime debt. |
| `keymap_setup/debug.rs` | keypress inspector view: missing-key hint delay, report lines, release-event ignoring, detected/config/raw event display, action matches, Ctrl+C handled completion, Esc routing preference, next-frame delay, modifier debug labels | `tests/test_tui_keymap_setup_debug.py::{test_initial_and_delayed_missing_key_hints,test_handle_key_event_ignores_release_and_reports_detected_key,test_debug_view_reports_matching_actions_and_none_state,test_view_completion_ctrl_c_esc_preference_and_next_frame_delay,test_key_debug_helpers_format_modifiers_in_rust_order}` | complete_slice | Python models the bottom-pane debug view as semantic text lines and duck-typed key events instead of ratatui/crossterm objects; concrete view-stack rendering remains runtime debt. |
| `render/renderable.rs` | shared buffer migration: `Rect`/`Buffer` model unification with ratatui bridge, text/paragraph render writes to cell buffer, column/row/flex/inset tests migrated from recording assertions to plain cell output | `tests/test_tui_render_renderable.py`, `tests/test_tui_ratatui_bridge.py` | complete_slice | `render.renderable` now targets `ratatui_bridge.Rect/Buffer`; concrete ratatui widget rendering and Rich/Textual backend painting remain bridge/runtime boundaries. Tests not run in this migration step. |
| `render/renderable.rs` | ratatui `Span`, `Line`, `Text`-equivalent, and `Paragraph` renderable trait impl shape after shared bridge migration | `tests/test_tui_render_renderable.py::test_bridge_span_line_text_and_paragraph_are_renderable_like_ratatui_types` | complete_slice | Python `render.renderable.as_renderable` now accepts bridge `Span`, `Line`, `Text`, and `Paragraph`, preserving span styles in `Buffer` and delegating paragraph rendering through `ratatui_bridge.widgets.Paragraph`. Tests added as parity evidence but not run in this step. |
| `ratatui_bridge` | codex-tui-used ratatui bridge behavior: layout constraints/remainder, side-specific block borders, paragraph wrap/alignment/scroll/clear, Textual adapter conversion, WidgetRef dispatch, Terminal/TestBackend draw | `tests/test_tui_ratatui_bridge.py::{test_layout_constraints_split_area_with_rust_like_remainder_rules,test_block_borders_support_side_flags_inner_area_and_unicode_border_types,test_paragraph_wrap_alignment_scroll_and_clear_render_to_buffer,test_textual_adapter_converts_buffer_and_renderables_without_terminal_io,test_widget_ref_helper_prefers_render_ref_and_falls_back_to_render,test_terminal_draw_uses_test_backend_buffer_and_flushes_once}` | complete_slice | Adds focused behavior evidence for the bridge surface used by codex-tui modules. Real terminal/crossterm side effects remain intentionally delegated to Textual/runtime boundaries. |
| `ratatui_bridge` | high-risk bridge contract tests: fixed-overflow layout clipping, min-constraint remainder, zero-area safety, nonzero-origin buffer intersection, buffer indexing, multispan paragraph style with horizontal scroll, no-wrap truncation, block inner rendering, tiny/title block boundaries, adapter immutability, and explicit crossterm no-side-effect errors | `tests/test_tui_ratatui_bridge.py::{test_layout_clips_when_fixed_constraints_exceed_available_space,test_layout_min_constraints_share_remaining_space_and_zero_area_is_safe,test_buffer_fill_and_style_are_clipped_to_intersection_with_nonzero_origin,test_buffer_indexing_matches_cell_access_and_ignores_out_of_bounds_writes,test_paragraph_preserves_multispan_styles_with_horizontal_scroll,test_paragraph_no_wrap_truncates_to_width_and_respects_height_limit,test_paragraph_with_block_renders_inside_inner_area,test_block_handles_tiny_areas_and_truncates_title,test_adapter_region_conversion_trims_right_edges_without_mutating_buffer,test_crossterm_terminal_side_effects_are_explicitly_not_implemented}` | complete_slice | Adds contract-level guardrails for bridge semantics and the Textual terminal boundary. Verified with `python -m pytest tests\\test_tui_render_renderable.py tests\\test_tui_ratatui_bridge.py -q` -> 36 passed. |

| `render/highlight.rs` | syntax highlighting via syntect/two_face; theme listing and guard helpers | `pycodex/tui/render/highlight.py` | blocked | Deliberately downgraded to a no-op highlighter: public interfaces remain, `highlight_to_line_spans*` / `highlight_code_to_styled_spans` return `None`, and `highlight_code_to_lines` preserves plain text only. Exact token/style parity is blocked pending a Python 3.7-compatible TextMate/syntect-equivalent engine; Pygments approximation was removed to avoid misleading behavior parity. |
| `tui/event_stream.rs` | `EventBroker`, `TuiEventStream`, fake source tests: key skip, draw/key fairness, lagged draw, resize, error/EOF, pause/resume wake | `tests/test_tui_event_stream.py` | complete_slice | Ports module-local event-stream semantics with deterministic in-memory sources and draw queues. Real crossterm stdin/EventStream, tokio Stream polling, Unix suspend handling, and terminal palette requery side effects remain runtime boundaries. |
| `tui/event_stream.rs` | Textual runtime adapter for Rust-style event source boundary | `tests/test_tui_textual_event_source.py` | complete_slice | Adds a backend adapter that maps Textual-like key/resize/paste/focus/blur events into the existing `EventBroker`/`TuiEventStream` Rust-style API. Real Textual app lifecycle remains the terminal runtime boundary; codex-tui modules still consume Rust-facing event APIs only. |
| `tui/event_stream.rs` | Textual lifecycle hook bridge: `on_key`/`on_resize`/`on_paste`/`on_focus`/`on_blur` into Rust-style stream | `tests/test_tui_textual_event_source.py::test_textual_event_bridge_lifecycle_hooks_feed_rust_style_stream` | complete_slice | Adds the runtime binding layer needed for Textual apps/widgets to feed `TuiEventStream` without exposing Textual to business modules. Actual Textual app scheduling remains framework-owned. |

### codex-tui `tui/event_stream.rs` - complete update
- Python module: `pycodex.tui.tui.event_stream`
- Textual adapter: `pycodex.tui.tui.textual_event_source`
- Tests: `tests/test_tui_event_stream.py`, `tests/test_tui_textual_event_source.py`
- Status: `complete`
- Notes: Promoted after adding the Rust-facing semantic event stream plus Textual-backed event source and lifecycle bridge. Module-owned behavior is covered: broker pause/resume lifecycle, fake source, draw/key/resize/paste/focus mapping, skipped unmapped events, error/EOF termination, draw/input polling, and Textual `on_key`/`on_resize`/`on_paste`/`on_focus`/`on_blur` ingress through the same Rust-style `TuiEventStream` API. Rust `crossterm::EventStream` and `tokio::Stream` internals are replaced by the Python/Textual runtime backend and are no longer tracked as unfinished module behavior.
| `chatwidget/turn_runtime.rs` | task running derivation, task start reset, runtime metrics delta, finalize-turn cleanup, warning display, plan update progress, plan implementation prompt guards/context label, interrupted turn message | `tests/test_tui_chatwidget_turn_runtime.py` | complete_slice | Ports module-owned ChatWidget turn-runtime state transitions with a semantic runtime object. Full `ChatWidget`, concrete history cells, bottom-pane rendering, app-server errors/rate-limit transport, and real notification backends remain neighboring/runtime boundaries. |

## 2026-06-14 - notifications/osc9.rs complete promotion

- Rust module: `codex-tui::notifications::osc9`
- Python module: `pycodex.tui.notifications.osc9`
- Status: `complete`
- Rust tests mapped:
  - `post_notification_writes_plain_osc9_sequence` -> `tests/test_tui_notifications_osc9.py::test_post_notification_writes_plain_osc9_sequence`
  - `post_notification_writes_tmux_dcs_wrapped_osc9_sequence` -> `tests/test_tui_notifications_osc9.py::test_post_notification_writes_tmux_dcs_wrapped_osc9_sequence`
  - `post_notification_escapes_escape_bytes_inside_tmux_payload` -> `tests/test_tui_notifications_osc9.py::test_post_notification_escapes_escape_bytes_inside_tmux_payload`
- Notes: Completed the module-owned behavior contract: plain OSC 9 emission, tmux DCS passthrough wrapping, ESC-byte escaping inside tmux payloads, ANSI-only WinAPI rejection semantics, backend notify flushing, and tmux detection semantics via the conventional `TMUX` environment marker. No tests were run in this step.

## 2026-06-14 - config_update.rs complete promotion

- Rust module: `codex-tui::config_update`
- Python module: `pycodex.tui.config_update`
- Status: `complete`
- Rust tests mapped:
  - `app_scoped_key_path_quotes_dotted_app_ids` -> `tests/test_tui_config_update.py::test_app_scoped_key_path_quotes_dotted_app_ids`
  - `trusted_project_edit_targets_project_trust_level` -> `tests/test_tui_config_update.py::test_trusted_project_edit_targets_project_trust_level`
- Behavior covered: replace/null edit shape, app-scoped JSON key quoting, trusted project trust-level edit escaping, model/effort edits, service-tier normalization, Windows sandbox migration edits, feature-toggle default-false clearing with the Rust `FEATURES` key/default table, memory and OSS-provider edits, config read/write request shapes, skill-config write request shape, and Rust request-id prefixes. App-server transport remains injected exactly at the request-handle boundary. No tests were run in this step.

## 2026-06-14 - collaboration_modes.rs complete promotion

- Rust module: `codex-tui::collaboration_modes`
- Python module: `pycodex.tui.collaboration_modes`
- Status: `complete`
- Rust behavior covered: `filtered_presets`, `default_mask`, `mask_for_kind`, `next_mask`, `default_mode_mask`, and `plan_mask`.
- Tests: `tests/test_tui_collaboration_modes.py`
- Notes: Completed the module-owned collaboration-mode preset helper contract: TUI-visible filtering, Rust's intentionally ignored `ModelCatalog` argument, default-mode preference, first-visible fallback, non-visible kind rejection, list-order cycling, helper delegation, builtin preset use, and cloned-return semantics. Remaining changes in this step only normalized Python 3.7-compatible type annotations. No tests were run in this step.

## 2026-06-14 - motion.rs complete promotion

- Rust module: `codex-tui::motion`
- Python module: `pycodex.tui.motion`
- Status: `complete`
- Rust tests mapped:
  - `reduced_motion_activity_indicator_uses_explicit_fallback` -> `tests/test_tui_motion.py::test_reduced_motion_activity_indicator_uses_explicit_fallback`
  - `reduced_motion_shimmer_text_is_plain_text` -> `tests/test_tui_motion.py::test_reduced_motion_shimmer_text_is_plain_text`
  - `animation_primitives_are_only_used_by_motion_module` -> `tests/test_tui_motion.py::test_animation_primitives_are_only_used_by_motion_module`
- Behavior covered: animation/reduced mode selection, explicit reduced-motion activity fallback, reduced shimmer as plain text, animated truecolor shimmer delegation, non-truecolor 600ms blink cadence using Rust-like integer millisecond truncation, recursive Rust source scanning, line-comment stripping, spinner/shimmer primitive violation detection, and allowlisted `motion.rs`/`shimmer.rs` paths. Terminal color probing is represented by the injectable `supports_truecolor_stdout` semantic boundary. No tests were run in this step.

## 2026-06-14 - wrapping.rs completion audit

- Rust module: `codex-tui::wrapping`
- Python module: `pycodex.tui.wrapping`
- Status: `complete_slice`
- Notes: Re-audited for complete promotion and intentionally did not promote. The Python module covers the user-visible semantic wrapping contract for line/span wrapping, URL-like token detection, URL-preserving adaptive wrapping, mixed URL/prose wrapping, style preservation, indents, and source-range helpers. The remaining blocker is Rust `textwrap` fidelity at the internal `Cow::Borrowed`/`Cow::Owned`, pointer-derived byte range, synthetic indent, and penalty-character reconstruction boundary. This step normalized public/internal type annotations touched by the module to Python 3.7-compatible `typing` forms. No tests were run in this step.

## 2026-06-14 - shimmer.rs complete promotion

- Rust module: `codex-tui::shimmer`
- Python module: `pycodex.tui.shimmer`
- Status: `complete`
- Rust behavior covered: process-start elapsed sweep, empty text, one span per character, 10-column padding, two-second modulo period, cosine shimmer band, fallback dim/plain/bold thresholds, truecolor RGB blend using default background/foreground and `0.9` highlight scaling, and stdout truecolor probe boundary.
- Tests: `tests/test_tui_shimmer.py`
- Notes: Promoted from `complete_slice` to `complete`. Python uses semantic `ShimmerStyle` rather than ratatui `Style`/`Color`, which is the accepted framework mapping for this port; terminal color capability probing is represented by `supports_truecolor_stdout` and remains injectable for deterministic tests. No tests were run in this step.

## 2026-06-14 - tooltips.rs completion audit

- Rust module: `codex-tui::tooltips`
- Python module: `pycodex.tui.tooltips`
- Status: `complete_slice`
- Notes: Re-audited for complete promotion and intentionally did not promote. Improved parity by loading the tooltip catalog from the upstream `codex/codex-rs/tui/tooltips.txt` path, matching Rust `include_str!("../tooltips.txt")` in the workspace, with a packaged snapshot fallback. Added a Python 3.7-compatible TOML parser fallback for the announcement-tip subset when stdlib `tomllib` is unavailable. The remaining blocker is Rust's real `reqwest` announcement prewarm/fetch side effect with timeout/no-proxy behavior; Python still requires an injected fetcher and does not perform implicit network I/O. No tests were run in this step.

## 2026-06-14 - update_action.rs complete promotion

- Rust module: `codex-tui::update_action`
- Python module: `pycodex.tui.update_action`
- Status: `complete`
- Rust tests mapped:
  - `maps_install_context_to_update_action` -> `tests/test_tui_update_action.py::test_maps_install_context_to_update_action`
  - `standalone_update_commands_rerun_latest_installer` -> `tests/test_tui_update_action.py::test_standalone_update_commands_rerun_latest_installer`
- Behavior covered: install-method/platform mapping for npm, bun, brew, standalone Unix, standalone Windows, and other; full command argument table; shell-joined command string; and release-style `get_update_action` delegation to the ported `pycodex.install_context.InstallContext.current` with injected-context support for deterministic tests. No update command is executed by this module. No tests were run in this step.

### notifications/bel.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `notifications/bel.rs` | `BelBackend::notify`, `PostNotification::write_ansi`, Windows ANSI support / WinAPI rejection | `pycodex/tui/notifications/bel.py`, `tests/test_tui_notifications_bel.py` | complete | Audited against Rust source: module has no Rust unit tests, and the full local behavior contract is BEL ANSI emission, message ignoring, repeated writes, flush side effect for Python stream semantics, and explicit WinAPI rejection. |

### update_versions.rs Python 3.7 compatibility audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `update_versions.rs` | `is_newer`, `extract_version_from_latest_tag`, `is_source_build_version`, `parse_version`, Rust unit tests | `pycodex/tui/update_versions.py`, `tests/test_tui_update_versions.py` | complete | Behavior was already complete; this audit normalizes annotations to Python 3.7-compatible `typing` forms and fixes the parity ledger's parse-version test reference. |

### app_server_approval_conversions.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `app_server_approval_conversions.rs` | `granted_permission_profile_from_request`, `file_update_changes_to_display`, Rust unit tests | `pycodex/tui/app_server_approval_conversions.py`, `tests/test_tui_app_server_approval_conversions.py` | complete | Full module contract is covered: request permission network/filesystem passthrough, canonical filesystem entries, Add/Delete/Update patch display conversion, update move paths, and explicit invalid-kind/path boundaries. Python annotations were normalized for Python 3.7 compatibility. |

### approval_events.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `approval_events.rs` | `ExecApprovalRequestEvent`, `ApplyPatchApprovalRequestEvent`, effective approval id, explicit/default decision selection | `pycodex/tui/approval_events.py`, `tests/test_tui_approval_events.py` | complete | Full module-owned contract is covered: approval-id fallback, explicit decision clone semantics, network-context decision ordering with first Allow amendment, additional-permissions branch, execpolicy amendment branch, plain exec branch, patch approval fields/path normalization/change validation, and semantic app-server decision DTOs. Python annotations were normalized for Python 3.7 compatibility. |

### key_hint.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `key_hint.rs` | `KeyBinding`, key normalization, C0 control mapping, plain-text classification, binding constructors, display labels/spans, AltGr boundary, Rust unit tests | `pycodex/tui/key_hint.py`, `tests/test_tui_key_hint.py` | complete | Full module-owned behavior is covered with semantic key/modifier strings and Span DTOs: press/repeat filtering, release rejection, shifted uppercase compatibility, raw C0 ctrl compatibility, ambiguous ESC/delete rejection, binding-list alternatives, plain/alt/shift/ctrl/ctrl-alt constructors, display-label ordering, dim key-hint span, platform AltGr boundary, and Python 3.7-compatible typing without `typing.Protocol`. |

### model_migration.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `model_migration.rs` | `migration_copy_for_models`, `ModelMigrationScreen`, `run_model_migration_prompt`, Rust prompt key tests and snapshot-visible contracts | `pycodex/tui/model_migration.py`, `tests/test_tui_model_migration.py` | complete | Full module-owned semantic contract is covered: markdown placeholder fill, default/custom copy branches, empty-description fallback, opt-out/non-opt-out prompt text, menu navigation and numeric selection, Esc-as-confirm, Ctrl-C/Ctrl-D exit, release filtering, long URL tail preservation, alt-screen enter/leave lifecycle, initial draw, Draw/Resize redraw, Paste ignore, and event-stream exhaustion accept. Ratatui snapshot cells are represented by semantic rendered rows. |

### slash_command.rs completion audit

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `slash_command.rs` | `SlashCommand` enum table, descriptions, command strings/aliases, inline args, side/task availability, visibility, built-in presentation order, Rust unit tests | `pycodex/tui/slash_command.py`, `tests/test_tui_slash_command.py` | complete | Full module-owned command table contract is covered. Python now avoids 3.9+ `removeprefix`, keeps runtime visibility predicates, preserves declaration/popup order, and treats `subagents` as the canonical `MultiAgents` command while accepting `multi-agents` as a compatibility alias. |

### keymap.rs completion audit - remains complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | Runtime keymap resolution, full built-in defaults, global fallback, explicit unbinding, legacy-default pruning, fixed shortcut exceptions, cross-surface conflict validation, key spec parsing, Rust unit tests | `pycodex/tui/keymap.py`, `tests/test_tui_keymap.py` | complete_slice | Audited for promotion and intentionally not marked complete. Python covers key spec parsing, primary binding, selected defaults, remap/unbind, and basic duplicate validation, but does not yet cover the full Rust resolver table, legacy pruning rules, fixed shortcut exceptions, app/composer/list/approval cross-surface validation matrix, or all Rust keymap tests. Type annotations were normalized toward Python 3.7-compatible `typing` forms. |

### keymap.rs resolver behavior expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | global fallback, explicit unbinding, legacy default pruning, configured cross-surface pruning, fixed shortcut/reserved conflicts, approval overlay conflicts, optional-action remapping, interrupt-turn remap/unbind rules | `pycodex/tui/keymap.py`, `tests/test_tui_keymap.py` | complete_slice | Expanded the Python resolver from a selected-default slice into a broader semantic resolver. Added Python coverage for Rust-visible rules: composer global fallback vs explicit local unbind, legacy list binding pruning, app/approval configured binding pruning of new list defaults, Vim normal/operator legacy pruning, reserved Ctrl+V and transcript-left conflicts, approval overlay list/approval conflicts, kill_whole_line/toggle_fast_mode optional action assignment, and interrupt_turn remap/unbind/reserved collision behavior. Still not marked complete until the full Rust built-in table and all Rust conflict-validation tests are exhaustively mirrored. |

### keymap.rs legacy pruning and explicit-conflict expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | legacy default pruning must not hide explicit new-action conflicts; approval/list overlay conflicts; reassignable fixed shortcuts after unbinding original action | `pycodex/tui/keymap.py`, `tests/test_tui_keymap.py` | complete_slice | Corrected pruning so configured legacy bindings only remove unconfigured new defaults. Explicitly configured new bindings that duplicate legacy/configured keys now surface conflicts, matching Rust tests for list page bindings and Vim operator text-object bindings. Added parity coverage for approval deny/decline conflicts and `alt-.` copy remap conflict release after unbinding `chat.increase_reasoning_effort`. |

### keymap.rs interrupt-question-navigation conflict expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | `interrupt_turn_rejects_request_user_input_question_navigation_bindings` | `pycodex/tui/keymap.py`, `tests/test_tui_keymap.py::test_interrupt_turn_can_use_escape_but_rejects_other_reserved_or_list_navigation_collisions` | complete_slice | Added the module-owned validation pass that rejects `chat.interrupt_turn` collisions with list left/right question navigation bindings, matching Rust's request-user-input navigation guard without broadening into a full chat-vs-list conflict pass. |

### keymap.rs parser and precedence expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | named key parsing and resolver precedence | `pycodex/tui/keymap.py`, `tests/test_tui_keymap.py` | complete_slice | Expanded semantic parser coverage for additional named keys (`insert`, `pageup`, `pagedown`) and strengthened precedence tests for app-level global config plus composer local override behavior. This continues closing resolver behavior without claiming full default-table/conflict-matrix completion. |

### keymap.rs binding helper precedence expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | `resolve_bindings`, `resolve_bindings_with_global_fallback`, explicit empty binding specs | `tests/test_tui_keymap.py::{test_parse_bindings_supports_string_array_and_deduplicates,test_resolve_binding_helpers_match_rust_precedence_and_unbind_semantics}` | complete_slice | Added focused parity coverage for helper-level precedence: local configured bindings override global, explicit local empty arrays unbind instead of falling back, global bindings precede defaults only when local config is absent, and empty arrays parse as empty binding lists. |

### keymap.rs diagnostics expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | invalid binding diagnostics and conflict action-name diagnostics | `tests/test_tui_keymap.py::{test_invalid_global_copy_binding_reports_global_path,test_conflict_errors_include_both_action_names}` | complete_slice | Added parity coverage for user-facing resolver diagnostics: invalid key specs preserve the stable config path (`tui.keymap.global.copy`) and rejected conflicts include both involved action names so users can repair ambiguous bindings. |

### keymap.rs struct inventory expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | `RuntimeKeymap` child keymap struct field inventory | `tests/test_tui_keymap.py::test_keymap_struct_field_inventory_matches_rust_module` | complete_slice | Added field-inventory parity coverage for App, Chat, Composer, Editor, VimNormal, VimOperator, VimTextObject, Pager, List, and Approval keymap structs. This locks the module's data-shape foundation before completing the full default table and resolver matrix. |

### keymap.rs conflict scope and modifier parser expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | Vim normal/text-object and pager conflict validation; `control-*` and multi-modifier key specs | `tests/test_tui_keymap.py::{test_conflict_validation_covers_vim_and_pager_scopes,test_parse_bindings_supports_string_array_and_deduplicates}` | complete_slice | Added parity evidence for additional internal conflict scopes (`vim_normal`, `vim_text_object`, `pager`) and modifier parser aliases/combinations (`control-o`, `ctrl-shift-u`). These strengthen resolver coverage but do not yet complete the full Rust keymap test inventory. |

### keymap.rs default alias and explicit-unbind expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | `explicit_empty_array_unbinds_action`, raw output toggle default/remap, editor newline/deletion aliases, composer shortcut alias, approval fullscreen alias | `tests/test_tui_keymap.py::{test_explicit_empty_array_unbinds_action,test_raw_output_toggle_defaults_and_can_be_remapped,test_editor_and_approval_default_aliases_match_rust_contract}` | complete_slice | Added focused parity coverage for additional Rust-tested default aliases and explicit empty-array unbinding. These tests make user-visible shortcut regressions easier to localize while full default-table parity remains outstanding. |

### keymap.rs new-default helper and symmetric list conflict expansion - still complete_slice

| Rust module | Rust behavior/test | Python parity | Status | Notes |
|---|---|---:|---|---|
| `keymap.rs` | `resolve_new_default_bindings`, configured legacy list bindings, explicit new list binding conflicts | `tests/test_tui_keymap.py::{test_resolve_new_default_bindings_preserves_configured_legacy_keys,test_legacy_list_bindings_prune_new_default_keys}` | complete_slice | Added direct parity coverage for new-default pruning helpers and the symmetric `move_down`/`page_down` explicit conflict case, matching the Rust resolver distinction between pruning unconfigured new defaults and rejecting explicitly duplicated bindings. |

### codex-tui::keymap.rs cross-surface shadowing expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors covered in this slice:
- `rejects_shadowing_editor_binding_in_main_scope`
- `rejects_shadowing_editor_binding_from_outer_main_handler`
- `rejects_shadowing_approval_binding_in_app_scope`
- `rejects_shadowing_list_binding_in_app_scope`
- `parses_canonical_binding`

Python coverage:
- `pycodex/tui/keymap.py` now validates Rust-style app-handler shadowing against list and approval handlers, including the allowed `clear_terminal` / `list.move_right` `ctrl-l` overlap.
- `pycodex/tui/keymap.py` now validates main handler shadowing against editor handlers so composer/app/chat bindings cannot silently preempt editor actions.
- `tests/test_tui_keymap.py` adds parity tests for canonical `ctrl-alt-shift-a` parsing and the newly covered cross-surface shadowing cases.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; remaining work is the full Rust default table and any still-unmirrored validation edge cases from the large runtime resolver.

### codex-tui::keymap.rs editor newline default ownership expansion - 2026-06-14

Status: `complete_slice`.

Rust behavior clarified in this slice:
- Plain `Enter` belongs to composer submit handling, not editor newline insertion.
- Editor newline aliases remain available through modified/newline-oriented bindings such as `ctrl-j`, `ctrl-m`, `shift-enter`, and `alt-enter`.
- If `editor.insert_newline` is explicitly configured to plain `Enter`, it conflicts with `composer.submit` under the main-handler shadowing rules.

Python coverage:
- `pycodex/tui/keymap.py` removes plain `Enter` from the default `editor.insert_newline` bindings.
- `tests/test_tui_keymap.py` updates default alias expectations and adds an explicit conflict test for `editor.insert_newline = enter`.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; the exact full Rust default table and exhaustive resolver matrix are still being closed incrementally.

### codex-tui::keymap.rs composer shadowing parity guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors covered in this slice:
- `rejects_shadowing_composer_queue_in_app_scope`
- `rejects_shadowing_composer_toggle_shortcuts_in_app_scope`

Python coverage:
- `tests/test_tui_keymap.py` now verifies that app/global bindings cannot shadow `composer.queue` or `composer.toggle_shortcuts`.
- The behavior is provided by the existing `validate_no_shadow_with_allowed_overlaps("main", [app, chat, composer])` resolver rule.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; this adds Rust-test parity evidence but does not yet close the full default table or exhaustive resolver matrix.

### codex-tui::keymap.rs composer submit shadowing parity guard - 2026-06-14

Status: `complete_slice`.

Rust anchor covered in this slice:
- `rejects_shadowing_composer_binding_in_app_scope`

Python coverage:
- `tests/test_tui_keymap.py` now verifies that an app/global binding such as `open_transcript = ctrl-t` cannot shadow `composer.submit = ctrl-t`.
- Together with the previous `composer.queue` and `composer.toggle_shortcuts` tests, the Rust composer shadowing group is now represented in Python parity tests.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; the full default table and any remaining resolver edge cases are still being closed incrementally.

### codex-tui::keymap.rs main/editor allowed-overlap correction - 2026-06-14

Status: `complete_slice`.

Rust behavior corrected in this slice:
- `RuntimeKeymap::built_in_defaults` includes plain `Enter` in both `composer.submit` and `editor.insert_newline`.
- `validate_conflicts` explicitly allows the overlap `composer.submit` / `editor.insert_newline` on plain `Enter`.
- The main-surface shadow validation primary set matches Rust more closely: it excludes `composer.queue`, `composer.toggle_shortcuts`, `composer.history_search_next`, and `chat.edit_queued_message` from the main-vs-editor shadow pass.

Python coverage:
- `pycodex/tui/keymap.py` restores plain `Enter` in default `editor.insert_newline` and adds the Rust allowed overlap.
- `tests/test_tui_keymap.py` restores default alias expectations and now verifies the explicit `editor.insert_newline = enter` overlap is accepted.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; this fixes one important parity correction while the rest of the default table and resolver inventory remain in progress.

### codex-tui::keymap.rs main-surface default table expansion - 2026-06-14

Status: `complete_slice`.

Rust defaults aligned in this slice:
- `app.open_external_editor = ctrl-g`
- `app.toggle_vim_mode = []`
- `chat.edit_queued_message = alt-up, shift-left`
- `composer.queue = tab`
- `composer.toggle_shortcuts = ?, shift-?`

Python coverage:
- `pycodex/tui/keymap.py` updates the built-in default keymap for the app/chat/composer surface to match Rust source.
- `tests/test_tui_keymap.py` adds `test_runtime_keymap_main_surface_defaults_match_rust` to guard these defaults alongside existing resolver tests.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; more default-table groups and resolver edge cases remain to be closed before module completion.

### codex-tui::keymap.rs editor default table expansion - 2026-06-14

Status: `complete_slice`.

Rust defaults aligned in this slice:
- Full `EditorKeymap` built-in default binding vectors, including movement aliases, word movement aliases, line start/end ordering, deletion aliases, kill/yank actions, and modified Backspace/Delete bindings.

Python coverage:
- `pycodex/tui/keymap.py` updates `RuntimeKeymap.built_in_defaults().editor` to match Rust ordering and binding contents.
- `tests/test_tui_keymap.py` adds `test_runtime_keymap_editor_defaults_match_rust`, asserting the complete editor default table instead of only checking selected aliases.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; Vim, pager, list, approval default-table groups and any remaining resolver edge cases still need to be closed before module completion.

### codex-tui::keymap.rs Vim default table expansion - 2026-06-14

Status: `complete_slice`.

Rust defaults aligned in this slice:
- Full `VimNormalKeymap`, `VimOperatorKeymap`, and `VimTextObjectKeymap` built-in default binding vectors.
- Corrected Vim operator motions to Rust's operator-only `h/l/k/j` defaults without arrow aliases.
- Corrected `$` line-end bindings and expanded text-object aliases for parentheses, braces, brackets, and quotes.

Python coverage:
- `pycodex/tui/keymap.py` updates the Vim built-in defaults to match Rust source contents and ordering.
- `tests/test_tui_keymap.py` adds `test_runtime_keymap_vim_defaults_match_rust`, asserting the complete Vim default groups.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; pager/list/approval default-table groups and any remaining resolver edge cases still need to be closed before module completion.

### codex-tui::keymap.rs pager/list/approval default table expansion - 2026-06-14

Status: `complete_slice`.

Rust defaults aligned in this slice:
- Full `PagerKeymap`, `ListKeymap`, and `ApprovalKeymap` built-in default binding vectors.
- Corrected pager page-space aliases, close/close-transcript bindings, list Ctrl navigation aliases, and approval approve/session/deny/decline bindings.

Python coverage:
- `pycodex/tui/keymap.py` updates pager/list/approval built-in defaults to match Rust source contents and ordering.
- `tests/test_tui_keymap.py` adds `test_runtime_keymap_pager_list_approval_defaults_match_rust`, asserting the complete default groups.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; the default table is now substantially covered, but remaining resolver edge cases and Rust test inventory need final audit before marking complete.

### codex-tui::keymap.rs invalid path and prune-all guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors covered in this slice:
- `invalid_global_open_transcript_binding_reports_global_path`
- `invalid_global_open_external_editor_binding_reports_global_path`
- `configured_legacy_list_bindings_can_prune_all_new_default_keys`

Python coverage:
- `tests/test_tui_keymap.py` now verifies invalid global binding diagnostics include the exact `tui.keymap.global.*` path for transcript and external-editor actions.
- `tests/test_tui_keymap.py` now verifies legacy `list.move_up = [page-up, ctrl-b]` prunes all new `list.page_up` defaults, leaving it empty.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; remaining work is the final resolver test inventory audit before promotion.

### codex-tui::keymap.rs exact pruning guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors strengthened in this slice:
- `configured_app_bindings_prune_new_list_default_overlaps`
- `configured_approval_bindings_prune_new_list_default_overlaps`
- `explicit_new_list_bindings_still_conflict_with_configured_approval_bindings`
- `configured_legacy_vim_normal_bindings_prune_new_change_operator_default`
- `explicit_new_vim_normal_binding_still_conflicts_with_legacy_binding`
- `configured_legacy_vim_operator_bindings_prune_new_text_object_defaults`
- `explicit_new_vim_operator_binding_still_conflicts_with_legacy_binding`

Python coverage:
- `tests/test_tui_keymap.py` adds exact result guards for app/list and approval/list pruning after default-table alignment.
- `tests/test_tui_keymap.py` adds exact Vim normal/operator pruning and explicit-conflict guards matching the Rust test cases.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; remaining work is final audit of validation matrices and any Python/Rust parser edge differences.

### codex-tui::keymap.rs approval overlay allowed-overlap correction - 2026-06-14

Status: `complete_slice`.

Rust behavior corrected in this slice:
- Approval overlay validation allows exactly `list.cancel` and `approval.decline` to overlap on plain `Esc`.
- Other approval overlay overlaps still conflict, including `list.cancel = c` versus `approval.cancel = c`.

Python coverage:
- `pycodex/tui/keymap.py` replaces the coarse approval-overlay shadow check with pair-based validation and the Rust `Esc` exception.
- `tests/test_tui_keymap.py` adds a guard proving defaults validate with the `Esc` overlap and that the `c` cancel conflict still errors.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; this closes another validator/default-table interaction while final parser and test-inventory audit remains.

### codex-tui::keymap.rs context conflict guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors covered/strengthened in this slice:
- `invalid_global_copy_binding_reports_global_path`
- `rejects_conflicting_editor_bindings`
- `rejects_conflicting_pager_bindings`
- `rejects_conflicting_list_bindings`
- `rejects_conflicting_list_page_and_jump_bindings`

Python coverage:
- `tests/test_tui_keymap.py` now has explicit parity guards for editor, pager, list movement, and list page/jump same-context conflicts.
- `tests/test_tui_keymap.py` now verifies the Rust `meta-o` invalid global copy diagnostic path.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; remaining work is final parser/validation inventory audit and any last Rust-test-specific edge cases.

### codex-tui::keymap.rs fixed shortcut edge guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors strengthened in this slice:
- `reassignable_fixed_shortcuts_conflict_until_original_action_is_unbound`
- `kill_whole_line_can_be_assigned_without_default_binding`
- `kill_whole_line_conflicts_until_kill_line_start_is_unbound`
- `toggle_fast_mode_can_be_assigned_without_default_binding`
- `toggle_fast_mode_conflicts_with_existing_main_surface_bindings`
- `rejects_main_bindings_that_collide_with_remaining_fixed_shortcuts`

Python coverage:
- `tests/test_tui_keymap.py` adds explicit guards for reserved `ctrl-v`, reassigning `alt-.` after unbinding reasoning increase, assigning `kill_whole_line`, and assigning `toggle_fast_mode` while preserving conflicts with existing defaults.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; final promotion still needs a concise audit that all Rust tests and public behavior contracts are represented.

### codex-tui::keymap.rs pair validator interface cleanup - 2026-06-14

Status: `complete_slice`.

Python cleanup:
- `pycodex/tui/keymap.py` now exports `validate_no_shadow_pairs`, matching the other validator helpers exposed by the Python module.
- `tests/test_tui_keymap.py` adds a focused guard for exact allowed-overlap behavior versus unallowed shadow conflicts.

Remaining status:
- Keep `keymap.rs` as `complete_slice`; final promotion still needs a concise full Rust-test inventory audit and, if approved, test execution.

### codex-tui::keymap.rs completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Public/module-local behavior represented in Python: `RuntimeKeymap`, all child keymap structs, `KeyBinding`, parser helpers, resolver helpers, default tables, conflict validators, reserved/fixed shortcut checks, pruning rules, and primary binding helper.
- Rust default table parity covered for app/chat/composer, editor, Vim normal/operator/text-object, pager, list, and approval groups.
- Rust test inventory covered by Python parity tests or grouped guard tests:
  - parser behavior: canonical modifiers, function keys, named keys, modifier-only rejection, minus aliases.
  - binding resolution: string/array specs, deduplication, local/global/default precedence, explicit unbinds, new-default pruning.
  - validation matrix: app/composer shadowing, main/editor shadowing with allowed Enter overlap, app/list/approval shadowing, request-user-input navigation conflicts, approval overlay allowed Esc overlap, same-context conflicts, reserved fixed shortcuts, transcript backtrack collisions.
  - reassignable defaults: raw output, copy/remap, kill whole line, fast mode.
  - diagnostics: invalid global paths and conflict messages containing the relevant action names.

Python evidence:
- `pycodex/tui/keymap.py`
- `tests/test_tui_keymap.py`

Validation note:
- Tests were not run in this turn per current porting-loop constraint. Status is promoted by source/test inventory parity, not by fresh execution.

### codex-tui::wrapping.rs display-width and indent guard expansion - 2026-06-14

Status: `complete_slice`.

Rust anchors strengthened in this slice:
- `indent_consumes_width_leaving_one_char_space`
- `wide_unicode_wraps_by_display_width`
- `line_height_counts_double_width_emoji`
- `wrap_lines_without_indents_is_concat_of_single_wraps`
- `wrap_lines_accepts_borrowed_iterators` / `wrap_lines_accepts_str_slices` semantic coverage through Python iterable inputs.

Python coverage:
- `tests/test_tui_wrapping.py` adds parity guards for indent width accounting, double-width emoji wrapping, and multi-line wrapping without indents.

Remaining status:
- Keep `wrapping.rs` as `complete_slice`; Rust has additional range-mapping and mixed-URL continuation-width tests that should be audited before promotion.

### codex-tui::bottom_pane::status_line_style completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Python module mirrors Rust's semantic status-line model: accent grouping, fallback styles, theme resolver override, separator spans, dim behavior, pull-request underline, RGB softening, named-color softening, and empty-segment handling.
- Fixed a user-visible parity bug: `STATUS_LINE_SEPARATOR` now matches Rust's `" 路 "` instead of mojibake text.
- Python tests cover the Rust module's unit-test contract: ordered plain text, dim separators, theme-first style resolution, softened RGB style, disabled theme colors, PR underline, empty result, accent mapping, and color helper math.
- Type annotations were adjusted away from Python 3.10 union syntax for better portability.

Python evidence:
- `pycodex/tui/bottom_pane/status_line_style.py`
- `tests/test_tui_bottom_pane_status_line_style.py`

Validation note:
- Tests were not run in this turn; completion is based on source/test inventory audit and targeted parity fix.

### codex-tui::render::renderable completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Python module mirrors Rust's renderable layout contract with semantic `Rect`/`Buffer` equivalents: default empty renderable, text/span/line/paragraph renderables, owned/borrowed `RenderableItem`, `ColumnRenderable`, `FlexRenderable`, `RowRenderable`, `InsetRenderable`, and inset helper behavior.
- Cursor behavior matches Rust defaults and delegation rules: default cursor position is `None`, default style is `DefaultUserShape`, column/row/flex/inset forward the first child cursor/style using the computed child area.
- Layout behavior covered: column stacking with clipping, flex non-flex-first allocation and last-flex rounding remainder, row width exhaustion and max-height reporting, inset area shrinking and height expansion.
- Rust source has no in-file unit tests; Python parity tests provide module-scoped evidence for all public behavior anchors.

Python evidence:
- `pycodex/tui/render/renderable.py`
- `tests/test_tui_render_renderable.py`

Validation note:
- Tests were not run in this turn per current loop; completion is based on source/test inventory audit.

### codex-tui::keymap_setup::debug completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Rust module: `codex/codex-rs/tui/src/keymap_setup/debug.rs`.
- Python module: `pycodex/tui/keymap_setup/debug.py`.
- Parity tests: `tests/test_tui_keymap_setup_debug.py`.
- Covered behavior: debug view construction, missing-key short/delayed hints, delayed frame scheduling, release-event ignore path, detected key/config key/raw event report construction, unsupported config-key error display, matched-action rendering, empty-match rendering, Ctrl-C completion, Esc inspection preference, and modifier debug-label ordering.
- Framework adaptation: Rust `Line`/`Span` styling and `Paragraph` rendering are represented as semantic text lines in Python; this preserves the module behavior contract without copying ratatui types.

Validation note: tests were not run in this turn per the no-test constraint.

### codex-tui::keymap_setup::picker completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Rust module: `codex/codex-rs/tui/src/keymap_setup/picker.rs`.
- Python module: `pycodex/tui/keymap_setup/picker.py`.
- Parity tests: `tests/test_tui_keymap_setup_picker.py`.
- Covered behavior: picker constants, all/common/custom/unbound/context/debug tabs, header text, action counts, hidden fast-mode filtering, selected-action initial index, row construction, binding summaries, custom/unbound row indicators, disabled empty rows, search values, semantic action events, footer hint visible copy, and Unicode display-width based name-column sizing.
- Framework adaptation: Rust `SelectionViewParams`, `SelectionTab`, `SelectionItem`, `Line`, and `Span` are represented by Python semantic dataclasses; event-channel actions are represented as deterministic semantic payloads.

Validation note: tests were not run in this turn per the no-test constraint.

### codex-tui::keymap_setup::actions completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Rust module: `codex/codex-rs/tui/src/keymap_setup/actions.rs`.
- Python module: `pycodex/tui/keymap_setup/actions.py`.
- Parity tests: `tests/test_tui_keymap_setup_actions.py`.
- Covered behavior: action descriptor/filter construction, FastMode-gated visibility, full catalog action coordinates and Rust UI descriptions, Rust-style action label capitalization, root-config binding slots, composer global fallback slots, runtime binding lookup with `global` mapped to `app`, binding summary formatting with runtime-order de-duplication and `unbound`, debug binding source precedence, and matching action reports for semantic key events including binding objects with `is_press`.
- Framework adaptation: Rust `TuiKeymap`, `RuntimeKeymap`, `KeyBinding`, and `KeyEvent` are represented by Python mappings/objects and duck-typed binding/event helpers while preserving module-owned catalog/accessor behavior.

Validation note: tests were not run in this turn per the no-test constraint.

### codex-tui::keymap_setup root module audit - 2026-06-14

Status: `blocked`.

Blocked reason:
- Rust module: `codex/codex-rs/tui/src/keymap_setup.rs`.
- Python module: `pycodex/tui/keymap_setup/__init__.py`.
- This is not a simple `mod.rs` facade. The root module owns the interactive keymap editing flow: action menu construction, replace-binding menu construction, conflict menu construction, capture view lifecycle, key event serialization, binding mutation outcomes, custom-binding removal, active binding extraction, and many Rust tests/snapshots.
- Neighbor modules `keymap_setup::actions`, `keymap_setup::picker`, and `keymap_setup::debug` are now complete, but the root module still needs a dedicated implementation pass before it can be promoted.

Required completion slices before `complete`:
- Implement semantic `KeymapEditOutcome`, action/replace/conflict menu builders, capture view lifecycle, `key_event_to_config_key_spec`, `binding_to_config_key_spec`, `key_parts_to_config_key_spec`, `keymap_with_edit`, `keymap_with_bindings`, `keymap_without_custom_binding`, `active_binding_specs`, `dedup_bindings`, and `has_custom_binding`.
- Add Python parity tests derived from the Rust tests in `keymap_setup.rs` for key serialization, replacement/add/clear behavior, stale replacement rejection, action menu shape, capture view lines, and completion return routing.

Validation note: tests were not run in this turn per the no-test constraint.

### codex-tui::session_log completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Rust module: `codex/codex-rs/tui/src/session_log.rs`.
- Python module: `pycodex/tui/session_log.py`.
- Parity tests: `tests/test_tui_session_log.py`.
- Covered behavior: env-gated `maybe_init`, explicit and default log path selection, parent directory creation, truncating open, best-effort Unix 0600 mode, OnceLock-style first-file retention, disabled logger no-ops, JSONL write/flush, `session_start` and `session_end` records, special inbound `AppEvent` summaries, pet result ok/error summaries, generic inbound variant summaries, outbound operation payload records, and generic `write_record` shape.
- Framework adaptation: Rust global `LazyLock<SessionLogger>` and `OnceLock<Mutex<File>>` are represented with a Python global logger plus injectable logger instances for deterministic tests; app events and commands are represented by semantic Python objects/dicts.

Validation note: tests were not run in this turn per the no-test constraint.

### codex-tui::file_search completion audit - 2026-06-14

Status: `complete`.

Completion basis:
- Rust module: `codex/codex-rs/tui/src/file_search.rs`.
- Python module: `pycodex/tui/file_search.py`.
- Parity tests: `tests/test_tui_file_search.py`.
- Covered behavior: manager construction, latest-query deduplication, empty-query session drop, search-directory update clearing state, session creation roots/options/cancel flag, swallowed session-start errors, 64-bit wrapping session token, query update after session creation, reporter token guard, empty latest-query guard, empty snapshot-query guard, match cloning into `AppEvent::FileSearchResult`, and no-op completion callback.
- Dependency boundary: actual `codex-file-search` indexing/session backend remains injected as a session factory. This is a dependency interface, not behavior owned by `codex-tui::file_search`.

Validation note: tests were not run in this turn per the no-test constraint.
