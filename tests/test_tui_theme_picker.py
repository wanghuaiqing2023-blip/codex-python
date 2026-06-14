# Parity source: codex-rs/tui/src/theme_picker.rs

from pycodex.tui.ratatui_bridge import Buffer, Modifier, Rect
from pycodex.tui.theme_picker import (
    DiffLineType,
    NARROW_PREVIEW_ROWS,
    PREVIEW_FALLBACK_SUBTITLE,
    WIDE_PREVIEW_LEFT_INSET,
    WIDE_PREVIEW_MIN_WIDTH,
    WIDE_PREVIEW_ROWS,
    PreviewDiffKind,
    ThemePreviewNarrowRenderable,
    ThemePreviewWideRenderable,
    build_theme_picker_params,
    centered_offset,
    configured_theme_name,
    preview_diff_line_type,
    preview_line_marker,
    preview_line_number,
    render_preview,
    subtitle_available_width,
    theme_picker_subtitle,
)


def test_preview_diff_line_type_maps_to_diff_render_kinds():
    assert preview_diff_line_type(PreviewDiffKind.CONTEXT) == DiffLineType.CONTEXT
    assert preview_diff_line_type(PreviewDiffKind.ADDED) == DiffLineType.INSERT
    assert preview_diff_line_type(PreviewDiffKind.REMOVED) == DiffLineType.DELETE


def test_centered_offset_matches_rust_frame_padding_behavior():
    assert centered_offset(20, 8, 1) == 6
    assert centered_offset(9, 8, 1) == 0


def test_wide_preview_renders_all_lines_centered_and_inset():
    rendered = ThemePreviewWideRenderable().render_lines(width=80, height=20)

    assert len(rendered) == len(WIDE_PREVIEW_ROWS)
    assert rendered[0].y > 0
    assert rendered[-1].y < 19
    assert rendered[0].x == WIDE_PREVIEW_LEFT_INSET
    assert rendered[0].line_no == 31
    assert any(line.marker == "+" for line in rendered)
    assert any(line.marker == "-" for line in rendered)


def test_narrow_preview_renders_one_add_and_one_remove_in_four_lines():
    rendered = ThemePreviewNarrowRenderable().render_lines(width=80, height=6)

    assert [line.line_no for line in rendered] == [12, 13, 13, 14]
    assert [line.marker for line in rendered].count("+") == 1
    assert [line.marker for line in rendered].count("-") == 1
    assert rendered[0].x == 0


def test_removed_preview_lines_are_marked_dim_semantically():
    rendered = render_preview(80, 6, NARROW_PREVIEW_ROWS, center_vertically=False, left_inset=0)

    removed = next(line for line in rendered if line.marker == "-")
    assert removed.dim is True



def test_wide_preview_renders_to_bridge_buffer_centered_and_inset():
    area = Rect.new(0, 0, 80, 20)
    buffer = Buffer.empty(area)

    ThemePreviewWideRenderable().render(area, buffer)

    lines = buffer.to_plain_text(trim_end=True).splitlines()
    numbered_rows = [idx for idx, line in enumerate(lines) if preview_line_number(line) is not None]
    assert len(numbered_rows) == len(WIDE_PREVIEW_ROWS)
    assert numbered_rows[0] > 0
    assert numbered_rows[-1] < 19
    assert lines[numbered_rows[0]].startswith("  31  fn summarize")
    assert any(preview_line_marker(line) == "+" for line in lines)
    assert any(preview_line_marker(line) == "-" for line in lines)


def test_narrow_preview_renders_to_bridge_buffer_and_preserves_delete_dim_style():
    area = Rect.new(0, 0, 80, 6)
    buffer = Buffer.empty(area)

    ThemePreviewNarrowRenderable().render_ref(area, buffer)

    lines = buffer.to_plain_text(trim_end=True).splitlines()
    assert [preview_line_number(line) for line in lines[:4]] == [12, 13, 13, 14]
    deleted_row = next(idx for idx, line in enumerate(lines) if preview_line_marker(line) == "-")
    marker_col = lines[deleted_row].index("-")
    first_code_col = marker_col + 1
    while buffer.cell(first_code_col, deleted_row).symbol == " ":
        first_code_col += 1
    assert Modifier.DIM in buffer.cell(first_code_col, deleted_row).style.modifiers
def test_subtitle_uses_tilde_path_when_it_fits(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    codex_home = tmp_path / ".codex"

    subtitle = theme_picker_subtitle(codex_home, terminal_width=200)

    assert "~" in subtitle
    assert "directory" in subtitle


def test_subtitle_falls_back_when_no_codex_home_or_too_narrow(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert theme_picker_subtitle(None, None) == PREVIEW_FALLBACK_SUBTITLE

    long_home = tmp_path / ("a" * 120) / ".codex"
    assert theme_picker_subtitle(long_home, terminal_width=140) == PREVIEW_FALLBACK_SUBTITLE


def test_subtitle_falls_back_for_94_column_side_by_side_layout(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert theme_picker_subtitle(tmp_path / ".codex", terminal_width=94) == PREVIEW_FALLBACK_SUBTITLE


def test_theme_picker_uses_half_width_with_stacked_fallback_preview():
    params = build_theme_picker_params(current_name=None, codex_home=None, terminal_width=None)

    assert params.side_content_width == "half"
    assert params.side_content_min_width == WIDE_PREVIEW_MIN_WIDTH
    assert isinstance(params.side_content, ThemePreviewWideRenderable)
    assert isinstance(params.stacked_side_content, ThemePreviewNarrowRenderable)


def test_theme_picker_items_include_search_values_for_preview_mapping(tmp_path):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "my-custom.tmTheme").write_text("theme", encoding="utf-8")

    params = build_theme_picker_params(codex_home=tmp_path)

    assert all(item.search_value for item in params.items)
    assert any(item.name == "my-custom (custom)" for item in params.items)
    idx = next(i for i, item in enumerate(params.items) if item.search_value == "my-custom")
    assert params.on_selection_changed is not None
    assert params.on_selection_changed(idx) == "SyntaxThemePreviewed:my-custom"


def test_unavailable_configured_theme_falls_back_to_configured_or_default_selection():
    params = build_theme_picker_params(current_name="not-a-real-theme", codex_home=None, terminal_width=120)

    assert params.initial_selected_idx is not None
    selected = params.items[params.initial_selected_idx]
    assert selected.search_value == configured_theme_name()
    assert selected.is_current is True


def test_preview_line_number_and_marker_helpers_match_rust_tests():
    line = "  13 -    format!"

    assert preview_line_number(line) == 13
    assert preview_line_marker(line) == "-"
