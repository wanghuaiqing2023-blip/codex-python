from __future__ import annotations

from dataclasses import dataclass

from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.markdown_render.table_key_value import (
    TABLE_BODY_SEPARATOR_CHAR,
    render_records,
    should_render_records,
    wrap_cell,
)
from pycodex.tui.terminal_hyperlinks import HyperlinkLine, TerminalHyperlink, line_text


@dataclass
class Cell:
    lines: list[HyperlinkLine]

    @classmethod
    def text(cls, text: str) -> "Cell":
        return cls([HyperlinkLine.new(text)])

    def plain_text(self) -> str:
        return "\n".join(line_text(line.line) for line in self.lines)


@dataclass
class Metric:
    kind: str


def test_should_render_records_for_fragmented_compact_token() -> None:
    rows = [[Cell.text("ordinary"), Cell.text("averyverylongtoken")]]
    assert should_render_records(rows, [8, 5], [Metric("Compact"), Metric("Compact")])


def test_should_render_records_for_starved_expansive_cells_and_threshold() -> None:
    rows = [
        [Cell.text("alpha beta gamma delta"), Cell.text("one two three four")],
        [Cell.text("short"), Cell.text("short")],
        [Cell.text("short"), Cell.text("short")],
    ]

    assert not should_render_records(
        rows,
        [8, 8],
        [Metric("Narrative"), Metric("TokenHeavy")],
    )

    assert should_render_records(
        rows[:1],
        [8, 8],
        [Metric("Narrative"), Metric("TokenHeavy")],
    )


def test_render_records_uses_aligned_fields_when_width_allows() -> None:
    rendered = render_records(
        [Cell.text("Name"), Cell.text("URL")],
        [[Cell.text("Codex"), Cell.text("https://example.com")]],
        [Metric("Compact"), Metric("TokenHeavy")],
        40,
        label_style="label",
        separator_style="separator",
    )

    assert [line_text(line.line) for line in rendered] == [
        " Name  Codex",
        " URL   https://example.com",
    ]
    assert rendered[0].line.spans[1] == Span("Name", "label")


def test_render_records_inserts_separator_between_rows() -> None:
    rendered = render_records(
        [Cell.text("K")],
        [[Cell.text("one")], [Cell.text("two")]],
        [Metric("Compact")],
        6,
        label_style="label",
        separator_style="separator",
    )

    assert [line_text(line.line) for line in rendered] == [
        " K  one",
        TABLE_BODY_SEPARATOR_CHAR * 6,
        " K  two",
    ]
    assert rendered[1].line.spans[0].style == "separator"


def test_render_records_uses_stacked_fields_when_width_is_tight() -> None:
    rendered = render_records(
        [Cell.text("Desc")],
        [[Cell.text("alpha beta gamma")]],
        [Metric("Narrative")],
        10,
        label_style="label",
        separator_style="separator",
    )

    assert [line_text(line.line) for line in rendered] == [
        " Desc",
        "  alpha",
        "  beta",
        "  gamma",
    ]


def test_wrap_cell_preserves_hyperlink_columns_after_wrapping() -> None:
    source = HyperlinkLine(
        Line.from_text("see https://example.com now"),
        [TerminalHyperlink(range(4, 23), "https://example.com")],
    )

    wrapped = wrap_cell(Cell([source]), 12)

    assert [line_text(line.line) for line in wrapped] == ["see", "https://exam", "ple.com now"]
    assert wrapped[1].hyperlinks[0].destination == "https://example.com"
    assert wrapped[1].hyperlinks[0].columns == range(0, 12)
