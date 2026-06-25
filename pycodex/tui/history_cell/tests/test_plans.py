"""Parity tests for codex-rs/tui/src/history_cell/plans.rs."""

from pycodex.tui.history_cell.plans import (
    PlanItemArg,
    ProposedPlanCell,
    StepStatus,
    StreamingPlanTailCell,
    UpdatePlanArgs,
    line_text,
    new_plan_update,
    new_proposed_plan,
    new_proposed_plan_stream,
)
from pycodex.tui.line_truncation import Line
from pycodex.tui.terminal_hyperlinks import HyperlinkLine


def texts(lines):
    return [line_text(line) for line in lines]


def hyperlink_texts(lines):
    return [line_text(line.line) for line in lines]


def test_streaming_plan_tail_is_passthrough_and_reports_continuation() -> None:
    cell = StreamingPlanTailCell.new([HyperlinkLine.new("already rendered")], True)

    assert texts(cell.display_lines(10)) == ["already rendered"]
    assert hyperlink_texts(cell.display_hyperlink_lines(10)) == ["already rendered"]
    assert texts(cell.raw_lines()) == ["already rendered"]
    assert cell.is_stream_continuation() is True


def test_proposed_plan_cell_headers_body_empty_and_raw_lines() -> None:
    cell = new_proposed_plan("", ".")

    assert hyperlink_texts(cell.display_hyperlink_lines(80)) == [
        "> Proposed Plan",
        " ",
        "  (empty)",
        " ",
    ]
    assert cell.raw_lines() == []


def test_proposed_plan_cell_renders_source_backed_body_and_links() -> None:
    cell = ProposedPlanCell("- visit https://example.com", ".")

    display = cell.display_hyperlink_lines(80)

    assert hyperlink_texts(display) == ["> Proposed Plan", " ", "  - visit https://example.com", " "]
    assert display[2].hyperlinks[0].destination == "https://example.com"
    assert texts(cell.raw_lines()) == ["- visit https://example.com"]


def test_proposed_plan_stream_is_passthrough() -> None:
    cell = new_proposed_plan_stream([Line.from_text("stream")], False)

    assert texts(cell.display_lines(80)) == ["stream"]
    assert texts(cell.raw_lines()) == ["stream"]
    assert cell.is_stream_continuation() is False


def test_plan_update_raw_lines_include_explanation_and_debug_statuses() -> None:
    cell = new_plan_update(
        UpdatePlanArgs(
            explanation=" why now ",
            plan=(
                PlanItemArg("done step", StepStatus.Completed),
                PlanItemArg("active step", StepStatus.InProgress),
                PlanItemArg("later step", StepStatus.Pending),
            ),
        )
    )

    assert texts(cell.raw_lines()) == [
        "Updated Plan",
        "why now",
        "Completed: done step",
        "InProgress: active step",
        "Pending: later step",
    ]


def test_plan_update_display_lines_cover_empty_plan() -> None:
    cell = new_plan_update({"explanation": "note", "plan": []})

    rendered = texts(cell.display_lines(80))

    assert rendered[0] == "> Updated Plan"
    assert "note" in "\n".join(rendered)
    assert "(no steps provided)" in "\n".join(rendered)


def test_step_status_coercion_accepts_protocol_like_strings() -> None:
    assert StepStatus.coerce("completed") is StepStatus.Completed
    assert StepStatus.coerce("in_progress") is StepStatus.InProgress
    assert StepStatus.coerce("pending") is StepStatus.Pending
