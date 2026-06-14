"""Parity tests for Rust ``codex-tui::bottom_pane::selection_tabs``."""

from dataclasses import dataclass

from pycodex.tui.bottom_pane.selection_tabs import (
    TAB_GAP_WIDTH,
    SelectionTab,
    StyledLine,
    StyledSpan,
    render_tab_bar,
    tab_bar_height,
    tab_bar_lines,
    tab_unit,
)


def _tabs(*labels: str) -> list[SelectionTab]:
    return [SelectionTab(id=label.lower(), label=label) for label in labels]


def test_tab_gap_width_and_active_unit_semantics() -> None:
    assert TAB_GAP_WIDTH == 2
    assert tab_unit("Models", active=True) == [
        StyledSpan("[", "accent"),
        StyledSpan("Models", "accent"),
        StyledSpan("]", "accent"),
    ]
    assert tab_unit("Models", active=False) == [StyledSpan("Models", "dim")]


def test_tab_bar_lines_wrap_when_next_unit_would_exceed_width() -> None:
    # Rust contract: active unit width includes brackets, gaps are two spaces,
    # and wrapping happens before adding a unit that would exceed max width.
    lines = tab_bar_lines(_tabs("One", "Two", "Three"), active_idx=1, width=12)

    assert [line.text for line in lines] == ["One  [Two]", "Three"]
    assert lines[0].width == len("One  [Two]")


def test_tab_bar_width_is_clamped_to_at_least_one_and_empty_tabs_have_zero_height() -> None:
    assert tab_bar_lines([], active_idx=0, width=10) == []
    assert tab_bar_height([], active_idx=0, width=10) == 0

    lines = tab_bar_lines(_tabs("Long", "B"), active_idx=0, width=0)
    assert [line.text for line in lines] == ["[Long]", "B"]
    assert tab_bar_height(_tabs("Long", "B"), active_idx=0, width=0) == 2


def test_render_tab_bar_appends_only_lines_that_fit_area_height() -> None:
    @dataclass
    class Area:
        width: int
        height: int

    rendered: list[StyledLine] = []
    render_tab_bar(_tabs("One", "Two", "Three"), active_idx=1, area=Area(width=12, height=1), buf=rendered)

    assert [line.text for line in rendered] == ["One  [Two]"]


def test_render_tab_bar_accepts_mapping_area() -> None:
    rendered: list[StyledLine] = []
    render_tab_bar(_tabs("A", "B"), active_idx=0, area={"width": 20, "height": 2}, buf=rendered)

    assert [line.text for line in rendered] == ["[A]  B"]


def test_active_index_out_of_range_leaves_all_tabs_inactive() -> None:
    # Rust source: tab_unit receives idx == active_idx; an out-of-range
    # active_idx does not clamp and therefore leaves every tab inactive.
    lines = tab_bar_lines(_tabs("One", "Two"), active_idx=99, width=20)

    assert [line.text for line in lines] == ["One  Two"]
    assert [span.style for span in lines[0].spans] == ["dim", "plain", "dim"]
