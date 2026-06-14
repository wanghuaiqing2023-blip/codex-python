# Parity source: codex-rs/tui/src/selection_list.rs

import pytest

from pycodex.tui.selection_list import (
    MAX_LABEL_WIDTH,
    SELECTED_MARKER,
    SelectionStyle,
    display_width,
    selection_option_prefix,
    selection_option_row,
    selection_option_row_with_dim,
    selection_option_style,
)


def test_selection_option_row_marks_selected_row_with_cyan_prefix():
    row = selection_option_row(0, "First option", True)

    assert row.prefix.text == f"{SELECTED_MARKER} 1. "
    assert row.prefix.width == display_width(row.prefix.text)
    assert row.prefix.style == SelectionStyle(foreground="cyan")
    assert row.label.text == "First option"
    assert row.label.width == MAX_LABEL_WIDTH
    assert row.label.wrap is True
    assert row.label.trim is False
    assert row.label.style == SelectionStyle(foreground="cyan")


def test_selection_option_row_uses_plain_style_for_unselected_row():
    row = selection_option_row(2, "Third option", False)

    assert row.prefix.text == "  3. "
    assert row.prefix.style == SelectionStyle()
    assert row.label.style == SelectionStyle()
    assert row.plain_text() == "  3. Third option"


def test_selection_option_row_with_dim_dims_only_unselected_rows():
    dimmed = selection_option_row_with_dim(1, "Dimmed", False, dim=True)
    selected = selection_option_row_with_dim(1, "Selected", True, dim=True)

    assert dimmed.prefix.style == SelectionStyle(dim=True)
    assert dimmed.label.style == SelectionStyle(dim=True)
    assert selected.prefix.style == SelectionStyle(foreground="cyan")
    assert selected.label.style == SelectionStyle(foreground="cyan")


def test_selection_option_prefix_is_one_based_like_rust():
    assert selection_option_prefix(9, False) == "  10. "


def test_selection_option_style_matches_rust_precedence():
    assert selection_option_style(True, dim=True) == SelectionStyle(foreground="cyan")
    assert selection_option_style(False, dim=True) == SelectionStyle(dim=True)
    assert selection_option_style(False, dim=False) == SelectionStyle()


def test_negative_index_is_rejected_at_python_boundary():
    with pytest.raises(ValueError, match="non-negative"):
        selection_option_row(-1, "bad", False)
