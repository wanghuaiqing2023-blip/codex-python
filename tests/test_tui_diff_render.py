"""Parity tests for codex-rs/tui/src/diff_render.rs semantic helpers."""

from pycodex.tui.diff_render import (
    DARK_TC_ADD_LINE_BG_RGB,
    DiffColorLevel,
    DiffLineType,
    DiffSummary,
    DiffTheme,
    FileChange,
    ResolvedDiffBackgrounds,
    Span,
    Style,
    calculate_add_remove_from_diff,
    collect_rows,
    create_diff_summary,
    detect_lang_for_path,
    desired_height,
    diff_color_level_for_terminal,
    display_width,
    fallback_diff_backgrounds,
    indexed_color,
    line_number_width,
    resolve_diff_backgrounds_for,
    rgb_color,
    style_gutter_for,
    style_line_bg_for,
    wrap_styled_spans,
)


def test_fallback_backgrounds_match_rust_theme_tables() -> None:
    dark_truecolor = fallback_diff_backgrounds(
        DiffTheme.Dark, DiffColorLevel.TrueColor
    )
    assert dark_truecolor.add == rgb_color(DARK_TC_ADD_LINE_BG_RGB)

    light_ansi256 = fallback_diff_backgrounds(DiffTheme.Light, DiffColorLevel.Ansi256)
    assert light_ansi256.add == indexed_color(194)
    assert light_ansi256.delete == indexed_color(224)

    ansi16 = fallback_diff_backgrounds(DiffTheme.Dark, DiffColorLevel.Ansi16)
    assert ansi16 == ResolvedDiffBackgrounds()


def test_scope_backgrounds_override_rich_color_levels_only() -> None:
    truecolor = resolve_diff_backgrounds_for(
        DiffTheme.Dark,
        DiffColorLevel.TrueColor,
        {"inserted": (0, 95, 0), "deleted": (95, 0, 0)},
    )
    assert truecolor.add == rgb_color((0, 95, 0))
    assert truecolor.delete == rgb_color((95, 0, 0))

    ansi256 = resolve_diff_backgrounds_for(
        DiffTheme.Dark,
        DiffColorLevel.Ansi256,
        {"inserted": (0, 95, 0)},
    )
    assert ansi256.add == indexed_color(22)

    ansi16 = resolve_diff_backgrounds_for(
        DiffTheme.Dark,
        DiffColorLevel.Ansi16,
        {"inserted": (0, 95, 0)},
    )
    assert ansi16 == ResolvedDiffBackgrounds()


def test_line_and_gutter_styles_follow_line_type() -> None:
    backgrounds = ResolvedDiffBackgrounds(add="green", delete="red")
    assert style_line_bg_for(DiffLineType.Insert, backgrounds).bg == "green"
    assert style_line_bg_for(DiffLineType.Delete, backgrounds).bg == "red"
    assert style_line_bg_for(DiffLineType.Context, backgrounds).bg is None

    light_insert = style_gutter_for(
        DiffLineType.Insert, DiffTheme.Light, DiffColorLevel.Ansi256
    )
    assert light_insert.fg == indexed_color(236)
    assert light_insert.bg == indexed_color(157)

    dark_delete = style_gutter_for(
        DiffLineType.Delete, DiffTheme.Dark, DiffColorLevel.TrueColor
    )
    assert "dim" in dark_delete.modifiers


def test_windows_terminal_promotes_ansi16_without_force_override() -> None:
    assert (
        diff_color_level_for_terminal(
            DiffColorLevel.Ansi16, "windows_terminal", has_wt_session=False
        )
        is DiffColorLevel.TrueColor
    )
    assert (
        diff_color_level_for_terminal(
            DiffColorLevel.Ansi16,
            "wezterm",
            has_wt_session=False,
            has_force_color_override=True,
        )
        is DiffColorLevel.Ansi16
    )
    assert (
        diff_color_level_for_terminal(
            DiffColorLevel.Ansi16, None, has_wt_session=True
        )
        is DiffColorLevel.TrueColor
    )
    assert (
        diff_color_level_for_terminal(None, "wezterm", has_wt_session=False)
        is DiffColorLevel.Ansi16
    )


def test_path_language_and_line_number_helpers() -> None:
    assert detect_lang_for_path("src/main.rs") == "rs"
    assert detect_lang_for_path("Dockerfile") == "dockerfile"
    assert detect_lang_for_path("README") is None
    assert line_number_width(0) == 1
    assert line_number_width(1234) == 4


def test_wrap_styled_spans_preserves_styles_and_display_width() -> None:
    bold = Style(fg="yellow").add_modifier("bold")
    lines = wrap_styled_spans([Span("abc\t界z", bold)], max_cols=6)

    assert [line.text() for line in lines] == ["abc", "\t", "界z"]
    assert all(span.style == bold for line in lines for span in line.spans)
    assert [display_width(line.text()) for line in lines] == [3, 4, 3]


def test_wrap_styled_spans_handles_explicit_newlines() -> None:
    lines = wrap_styled_spans([Span("ab\ncd")], max_cols=10)
    assert [line.text() for line in lines] == ["ab", "cd"]


def test_calculate_add_remove_from_diff_ignores_headers() -> None:
    # Rust: codex-tui/src/diff_render.rs::calculate_add_remove_from_diff.
    diff = "\n".join(
        [
            "--- a/src/lib.rs",
            "+++ b/src/lib.rs",
            "@@ -1,2 +1,3 @@",
            " context",
            "-old",
            "+new",
            "+extra",
        ]
    )
    assert calculate_add_remove_from_diff(diff) == (2, 1)


def test_create_diff_summary_orders_rows_and_renders_semantic_blocks() -> None:
    # Rust: codex-tui/src/diff_render.rs create_diff_summary/collect_rows
    # sort by path, summarize counts, and render per-file blocks.
    changes = {
        "z_delete.txt": FileChange.Delete("gone\n"),
        "a_add.txt": FileChange.Add("one\ntwo\n"),
        "m_update.txt": FileChange.Update("@@ -1 +1 @@\n-old\n+new\n", move_path="renamed.rs"),
    }

    rows = collect_rows(changes)
    assert [row.path.as_posix() for row in rows] == ["a_add.txt", "m_update.txt", "z_delete.txt"]
    assert [(row.added, row.removed) for row in rows] == [(2, 0), (1, 1), (0, 1)]

    lines = create_diff_summary(changes, ".", wrap_cols=80)
    text = [line.text() for line in lines]
    assert text[0] == "• Edited 3 files (+3 -2)"
    assert any("a_add.txt (+2 -0)" in line for line in text)
    assert any("m_update.txt → renamed.rs (+1 -1)" in line for line in text)
    assert any("+ one" in line for line in text)
    assert any("- old" in line for line in text)


def test_diff_summary_render_and_desired_height_share_line_count() -> None:
    # Rust Renderable::desired_height renders to a temporary line buffer and
    # returns that line count.
    summary = DiffSummary.new({"src/lib.rs": FileChange.Add("hello\n")}, cwd=".")
    lines = create_diff_summary(summary.changes, summary.cwd, wrap_cols=40)
    assert desired_height(summary, width=40) == len(lines)
