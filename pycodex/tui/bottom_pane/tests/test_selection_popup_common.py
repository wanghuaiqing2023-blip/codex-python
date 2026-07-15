"""Parity tests for Rust ``codex-tui::bottom_pane::selection_popup_common``."""

from pycodex.tui.bottom_pane.scroll_state import ScrollState
from typing import List

from pycodex.tui.bottom_pane.selection_popup_common import (
    ColumnWidthConfig,
    ColumnWidthMode,
    GenericDisplayRow,
    Line,
    Rect,
    Span,
    TerminalPopupLine,
    build_full_line,
    compute_desc_col,
    measure_rows_height,
    measure_rows_height_with_col_width_mode,
    menu_surface_inset,
    menu_surface_padding_height,
    render_menu_surface,
    render_rows,
    render_rows_single_line,
    render_terminal_popup_lines,
    should_wrap_name_in_column,
    terminal_popup_line_for_width,
    terminal_popup_lines_for_width,
    terminal_popup_line_style,
    wrap_indent,
    wrap_two_column_row,
)
from pycodex.tui.ratatui_bridge import Color as RatatuiColor


def test_menu_surface_inset_and_padding_match_rust_constants() -> None:
    assert menu_surface_inset(Rect(1, 2, 10, 6)) == Rect(3, 3, 6, 4)
    assert menu_surface_padding_height() == 2
    assert menu_surface_inset(Rect(0, 0, 1, 1)) == Rect(2, 1, 0, 0)


def test_one_cell_width_falls_back_without_panic_for_wrapped_two_column_rows() -> None:
    # Rust test: one_cell_width_falls_back_without_panic_for_wrapped_two_column_rows.
    row = GenericDisplayRow(name="1. Very long option label", description="Very long description", wrap_indent=4)

    assert wrap_two_column_row(row, desc_col=0, width=1) == []


def test_selected_rows_use_the_shared_accent_style_semantics() -> None:
    # Rust test: selected_rows_use_the_shared_accent_style.
    rows = [GenericDisplayRow(name="selected")]
    state = ScrollState(selected_idx=0)
    rendered: List[Line] = []

    render_rows(Rect(0, 0, 16, 1), rendered, rows, state, max_results=1, empty_message="no rows")

    assert rendered
    assert all(span.style == "accent" for span in rendered[0].spans)


def test_terminal_popup_lines_preserve_selected_row_semantics() -> None:
    # Rust owner: codex-tui::bottom_pane::selection_popup_common owns selected
    # row styling before terminal adapters project rows into the live viewport.
    rows = [
        GenericDisplayRow(name="/model", description="choose model"),
        GenericDisplayRow(name="/memories", description="configure memory"),
    ]
    state = ScrollState(selected_idx=1)

    rendered = render_terminal_popup_lines(
        rows,
        state,
        width=80,
        max_results=4,
        empty_message="no matches",
        column_width=ColumnWidthConfig(ColumnWidthMode.AUTO_ALL_ROWS),
    )

    assert rendered[0].text.startswith("/model")
    assert rendered[0].selected is False
    assert rendered[1].text.startswith("/memories")
    assert rendered[1].selected is True


def test_terminal_popup_lines_reserve_measured_height_for_all_wrapped_items() -> None:
    # Rust source: selection_popup_common requires wrapped rendering to be
    # paired with measure_rows_height_with_col_width_mode to avoid clipping.
    rows = [
        GenericDisplayRow(
            name=f"{index}. Option {index}",
            description="A long description that wraps onto another terminal row.",
        )
        for index in range(1, 5)
    ]
    state = ScrollState(selected_idx=0)
    column_width = ColumnWidthConfig(ColumnWidthMode.AUTO_ALL_ROWS)
    width = 44

    rendered = render_terminal_popup_lines(
        rows,
        state,
        width=width,
        max_results=4,
        empty_message="no matches",
        column_width=column_width,
    )

    expected_height = measure_rows_height_with_col_width_mode(
        rows,
        state,
        max_results=4,
        width=width + 1,
        column_width=column_width,
    )
    assert len(rendered) == expected_height
    for index in range(1, 5):
        assert any(line.text.startswith(f"{index}. Option {index}") for line in rendered)


def test_terminal_popup_line_style_maps_selected_semantics_to_terminal_style() -> None:
    # Rust owner: codex-tui::bottom_pane::selection_popup_common owns selected
    # row style before the terminal frame projects rows into ratatui cells.
    assert terminal_popup_line_style(selected=True).fg == RatatuiColor.LightBlue
    assert terminal_popup_line_style(selected=False).fg is None


def test_terminal_popup_line_for_width_clips_by_terminal_cell_width() -> None:
    # Rust owner: codex-tui::bottom_pane::selection_popup_common owns popup row
    # width handling. The terminal frame should consume clipped popup rows
    # instead of applying its own terminal truncation.
    line = TerminalPopupLine("你好abc", selected=True)

    clipped = terminal_popup_line_for_width(line, 5)

    assert clipped == TerminalPopupLine("你好a", selected=True)


def test_terminal_popup_lines_for_width_clips_rows_and_preserves_selection() -> None:
    # Rust owner: codex-tui::bottom_pane::selection_popup_common owns terminal
    # popup row width handling for all rows before chatwidget.rendering places them.
    lines = [
        TerminalPopupLine("你好abc", selected=True),
        TerminalPopupLine("plain-text", selected=False),
    ]

    clipped = terminal_popup_lines_for_width(lines, 5)

    assert clipped == [
        TerminalPopupLine("你好a", selected=True),
        TerminalPopupLine("plain", selected=False),
    ]


def test_build_full_line_combines_prefix_match_description_disabled_and_category() -> None:
    row = GenericDisplayRow(
        name="alpha",
        name_prefix_spans=[Span("> ")],
        match_indices=[0, 2],
        description="desc",
        disabled_reason="reason",
        category_tag="cat",
    )

    line = build_full_line(row, desc_col=10)

    assert line.text == "> alpha (disabled)desc (disabled: reason)  cat"
    assert [span.style for span in line.spans if span.text in {"a", "p"}][:2] == ["bold", "bold"]


def test_compute_desc_col_modes_and_wrap_indent_contracts() -> None:
    rows = [
        GenericDisplayRow(name="short", description="desc"),
        GenericDisplayRow(name="longer-name", disabled_reason="off"),
    ]

    assert compute_desc_col(rows, 0, 1, 20, ColumnWidthConfig(ColumnWidthMode.AUTO_VISIBLE)) == 7
    assert compute_desc_col(rows, 0, 1, 20, ColumnWidthConfig(ColumnWidthMode.AUTO_ALL_ROWS)) == 19
    assert compute_desc_col(rows, 0, 2, 20, ColumnWidthConfig(ColumnWidthMode.FIXED)) == 6
    assert wrap_indent(rows[0], desc_col=7, max_width=20) == 7
    assert wrap_indent(GenericDisplayRow(name="x", wrap_indent=99), desc_col=7, max_width=5) == 4


def test_should_wrap_name_in_column_and_render_single_line_empty_placeholder() -> None:
    assert should_wrap_name_in_column(GenericDisplayRow(name="option", description="desc", wrap_indent=2)) is True
    assert should_wrap_name_in_column(GenericDisplayRow(name="option", description="desc", wrap_indent=2, match_indices=[0])) is False

    rendered: List[Line] = []
    assert render_rows_single_line(Rect(0, 0, 10, 1), rendered, [], ScrollState(), 5, "empty") == 1
    assert rendered == [Line.from_text("empty", "dim+italic")]


def test_menu_surface_render_empty_area_is_noop_and_measure_empty_rows_placeholder() -> None:
    # Rust source: render_menu_surface returns the original empty area without
    # painting, and measure_rows_height reserves one placeholder row for empty
    # row sets.
    rendered: List[object] = []
    empty = Rect(0, 0, 0, 5)

    assert render_menu_surface(empty, rendered) == empty
    assert rendered == []
    assert measure_rows_height([], ScrollState(), max_results=5, width=10) == 1


def test_terminal_cell_width_truncation_keeps_wide_name_within_description_column() -> None:
    # Rust source: build_full_line truncates by unicode_width terminal cells,
    # not by Python codepoint count.
    row = GenericDisplayRow(name="模型alpha", description="desc")

    line = build_full_line(row, desc_col=6)

    assert line.text.startswith("模型…")
    assert "alpha" not in line.text

