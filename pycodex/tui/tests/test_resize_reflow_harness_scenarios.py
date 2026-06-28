from __future__ import annotations

import textwrap

from pycodex.tui.app.resize_reflow import (
    HistoryCell,
    HyperlinkLine,
    ResizeReflowState,
    handle_draw_size_change_plan,
    maybe_run_resize_reflow,
    reflow_transcript_now,
)
from pycodex.tui.tests.harness.terminal import TerminalCapture


class WrappingHistoryCell(HistoryCell):
    def display_hyperlink_lines_for_mode(self, width: int, mode=None) -> list[HyperlinkLine]:
        rows: list[HyperlinkLine] = []
        for line in self.lines:
            wrapped = textwrap.wrap(line, width=max(1, width), break_long_words=False) or [""]
            rows.extend(HyperlinkLine.new(row) for row in wrapped)
        return rows


def _screen_for_reflow(state: ResizeReflowState, width: int, draft: str) -> TerminalCapture:
    plan = reflow_transcript_now(state, width)
    capture = TerminalCapture()
    capture.write_lines([line.text for line in plan.lines])
    capture.write_lines([f"> {draft}"])
    return capture


def _resize_state(*, row_cap: int | None = 40) -> ResizeReflowState:
    sentinel = (
        "resize reflow sentinel says hi. This paragraph is intentionally long "
        "enough to exercise terminal wrapping, scrollback redraw, and pane "
        "resize behavior without requiring a live model response."
    )
    return ResizeReflowState(
        transcript_cells=[
            HistoryCell(["user", "Say hi."], cell_type="UserMessageCell"),
            WrappingHistoryCell([sentinel], cell_type="AgentMessageCell"),
            HistoryCell(["gpt-5.4 default"], cell_type="StatusCell"),
            WrappingHistoryCell(
                [
                    "final visible tail content should remain reachable after "
                    "height and width resize reflow"
                ],
                cell_type="AgentMessageCell",
            ),
        ],
        resize_reflow_max_rows_value=row_cap,
    )


def test_resize_reflow_harness_split_restore_keeps_history_and_composer_rows_anchored() -> None:
    """Rust codex-tui tests/suite/resize_reflow.rs split/restore contract.

    The Rust smoke uses tmux to split a pane and then restore it.  The stable
    behavior contract is that the history sentinel and composer row return to
    their original positions after resize reflow.
    """

    state = _resize_state()
    draft = "Notice where we are here in terms of y location."

    baseline = _screen_for_reflow(state, 120, draft)
    split = _screen_for_reflow(state, 60, draft)
    restored = _screen_for_reflow(state, 120, draft)

    assert split.first_row_containing("resize reflow sentinel") is not None
    assert restored.text() == baseline.text()
    assert restored.first_row_containing("resize reflow sentinel") == baseline.first_row_containing(
        "resize reflow sentinel"
    )
    assert restored.last_row_matching_prefix(">") == baseline.last_row_matching_prefix(">")


def test_resize_reflow_harness_repeated_resizes_do_not_push_composer_down() -> None:
    """Rust codex-tui tests/suite/resize_reflow.rs repeated resize contract."""

    state = _resize_state(row_cap=12)
    draft = "Notice where we are here in terms of y location."
    composer_rows: list[int] = []

    for width in (120, 70, 120, 70, 120):
        capture = _screen_for_reflow(state, width, draft)
        row = capture.last_row_matching_prefix(">")
        assert row is not None
        composer_rows.append(row)

    restored_rows = composer_rows[::2]
    assert restored_rows == [restored_rows[0]] * len(restored_rows)


def test_resize_reflow_harness_width_restore_keeps_visible_content_anchored() -> None:
    """Rust codex-tui tests/suite/resize_reflow.rs width restore contract."""

    state = _resize_state(row_cap=20)
    draft = "Notice where we are here in terms of y location."

    baseline = _screen_for_reflow(state, 120, draft)
    narrow = _screen_for_reflow(state, 40, draft)
    restored = _screen_for_reflow(state, 120, draft)

    assert narrow.text() != baseline.text()
    assert restored.first_row_containing("gpt-5.4 default") == baseline.first_row_containing("gpt-5.4 default")
    assert restored.last_row_matching_prefix(">") == baseline.last_row_matching_prefix(">")
    assert restored.text() == baseline.text()


def test_resize_reflow_harness_draw_resize_schedules_then_replays_transcript_tail() -> None:
    """Rust codex-tui app::resize_reflow scheduling and replay contract."""

    state = _resize_state(row_cap=16)

    schedule = handle_draw_size_change_plan(
        state,
        width=100,
        height=24,
        last_width=120,
        last_height=40,
        stream_time=True,
    )
    assert schedule.action == "schedule_resize_reflow"
    assert schedule.schedule_frame is True
    assert ("transcript_reflow.stream_time", True) in schedule.updates

    replay = maybe_run_resize_reflow(state, 100, pending_due=True, active_stream=True)
    capture = TerminalCapture()
    capture.write_lines([line.text for line in replay.lines])

    assert replay.action == "run_resize_reflow"
    assert ("clear_terminal_for_resize_replay", True) in replay.updates
    assert ("transcript_reflow.mark_ran_during_stream", True) in replay.updates
    assert capture.first_row_containing("resize reflow sentinel") is not None
