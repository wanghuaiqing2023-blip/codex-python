from pycodex.tui.history_cell import HistoryRenderMode
from pycodex.tui.streaming.controller import (
    PlanStreamController,
    StreamController,
    collect_plan_streamed_lines,
    collect_streamed_lines,
    hyperlink_lines_to_plain_strings,
    plan_stream_controller,
    stream_controller,
    test_cwd,
)
from pycodex.tui.terminal_hyperlinks import line_text


def texts(lines):
    return [line_text(line) for line in lines]


def test_controller_newline_gates_stable_queue_and_finalize_drains_remainder() -> None:
    # Rust: StreamCore::push_delta commits only newline-terminated source.
    ctrl = stream_controller(width=80)

    assert not ctrl.push("partial")
    assert ctrl.queued_lines() == 0
    assert ctrl.current_tail_lines() == []

    cell, raw_source = ctrl.finalize()

    assert raw_source == "partial\n"
    assert cell is not None
    assert texts(cell.raw_lines()) == ["partial"]


def test_controller_commit_tick_emits_stable_lines_and_reports_idle() -> None:
    # Rust: StreamController::on_commit_tick emits one queued stable line.
    ctrl = stream_controller(width=80)
    assert ctrl.push("first\nsecond\n")
    assert ctrl.queued_lines() == 2

    first, idle = ctrl.on_commit_tick()
    second, idle2 = ctrl.on_commit_tick()

    assert first is not None
    assert second is not None
    assert texts(first.raw_lines()) == ["first"]
    assert texts(second.raw_lines()) == ["second"]
    assert not idle
    assert idle2


def test_controller_tick_batch_zero_is_noop_and_batch_drains_many() -> None:
    # Rust: controller_tick_batch_zero_is_noop.
    ctrl = stream_controller(width=80)
    ctrl.push("a\nb\nc\n")

    none, idle = ctrl.on_commit_tick_batch(0)
    batch, idle2 = ctrl.on_commit_tick_batch(2)

    assert none is None
    assert not idle
    assert batch is not None
    assert texts(batch.raw_lines()) == ["a", "b"]
    assert not idle2
    assert ctrl.queued_lines() == 1


def test_controller_holds_table_header_as_live_tail_until_finalize() -> None:
    # Rust: table holdback keeps pipe table header/delimiter mutable.
    ctrl = stream_controller(width=80)

    ctrl.push("before\n")
    assert ctrl.queued_lines() == 1
    emitted, _ = ctrl.on_commit_tick()
    assert emitted is not None
    assert texts(emitted.raw_lines()) == ["before"]

    ctrl.push("| A | B |\n")
    assert ctrl.queued_lines() == 0
    assert hyperlink_lines_to_plain_strings(ctrl.current_tail_lines()) == ["| A | B |"]

    ctrl.push("| --- | --- |\n")
    assert ctrl.queued_lines() == 0
    assert hyperlink_lines_to_plain_strings(ctrl.current_tail_lines()) == ["| A | B |", "| --- | --- |"]

    cell, _ = ctrl.finalize()
    assert cell is not None
    assert texts(cell.raw_lines()) == ["| A | B |", "| --- | --- |"]


def test_controller_keeps_possible_header_as_pending_tail_without_delimiter() -> None:
    # Rust: PendingHeader holds a possible table header as live tail until more source arrives.
    ctrl = stream_controller(width=80)
    ctrl.push("alpha | beta\n")

    assert ctrl.queued_lines() == 0
    assert hyperlink_lines_to_plain_strings(ctrl.current_tail_lines()) == ["alpha | beta"]


def test_controller_set_width_after_emit_does_not_requeue_first_line() -> None:
    # Rust: controller_set_width_after_first_line_emit_does_not_requeue_first_line.
    ctrl = stream_controller(width=120)
    ctrl.push("FIRSTTOKEN line\n")
    ctrl.push("second line\n")

    first, _ = ctrl.on_commit_tick()
    assert first is not None

    ctrl.set_width(20)
    cell, _ = ctrl.finalize()
    remaining = texts(cell.raw_lines()) if cell else []

    assert "FIRSTTOKEN line" not in remaining
    assert "second line" in remaining


def test_raw_render_mode_disables_table_holdback() -> None:
    # Rust: StreamCore::active_tail_budget_lines returns 0 in Raw mode.
    ctrl = StreamController.new(80, test_cwd(), HistoryRenderMode.RAW)
    ctrl.push("| A | B |\n")
    ctrl.push("| --- | --- |\n")

    assert ctrl.queued_lines() == 2
    assert ctrl.current_tail_lines() == []


def test_plan_controller_uses_same_core_queue_and_tail_contract() -> None:
    # Rust: PlanStreamController delegates core behavior and emits plan stream cells.
    ctrl = plan_stream_controller(width=80)
    ctrl.push("## Plan\n")
    cell, idle = ctrl.on_commit_tick()

    assert cell is not None
    assert idle
    assert texts(cell.raw_lines()) == ["## Plan"]


def test_collect_helpers_preserve_stream_order() -> None:
    # Rust test helpers collect streamed lines after commit ticks and finalize.
    assert collect_streamed_lines(["a\n", "b"]) == ["a", "b"]
    assert collect_plan_streamed_lines(["x\n", "y"]) == ["x", "y"]
