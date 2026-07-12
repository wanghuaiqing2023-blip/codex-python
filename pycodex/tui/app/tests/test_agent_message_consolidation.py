from pycodex.tui.app.agent_message_consolidation import (
    AgentMarkdownCell,
    AgentMessageCell,
    AgentMessageConsolidationApp,
    TranscriptOverlay,
    Tui,
    TerminalAgentMessageConsolidator,
    TerminalTranscriptState,
    consolidates_trailing_agent_message_cells,
    deferred_history_cell_is_inserted_before_consolidation,
    no_trailing_agent_cells_finishes_stream_reflow_only,
    trailing_agent_message_run_start,
)


def test_terminal_consolidator_retains_source_before_required_reflow() -> None:
    # Rust source: codex-rs/tui/src/app/agent_message_consolidation.rs
    # Fixed Rust baseline 1c7832f:
    # chatwidget::streaming -> AppEvent::ConsolidateAgentMessage ->
    # app::agent_message_consolidation, before finish_required_stream_reflow.
    calls: list[tuple[str, object]] = []
    consolidator = TerminalAgentMessageConsolidator(
        transcript=TerminalTranscriptState(),
        write_transient_cell=lambda cell: calls.append(("write", cell)),
        replace_projection_run=lambda count, cell: calls.append(("replace", (count, cell))),
        run_required_reflow=lambda: calls.append(("required", None)),
        run_conditional_reflow=lambda: calls.append(("conditional", None)),
    )

    transient = AgentMessageCell.new(["answer"], True)
    consolidator.append_transient(transient)
    canonical = consolidator.consolidate(
        "answer",
        "/tmp",
        ConsolidationScrollbackReflow.REQUIRED,
    )

    assert canonical.markdown_source == "answer"
    assert consolidator.transcript.cells == [canonical]
    assert calls[0] == ("write", transient)
    assert calls[1][0] == "replace" and calls[1][1][0] == 1
    assert calls[2] == ("required", None)
from pycodex.tui.app_event import ConsolidationScrollbackReflow


def test_consolidates_trailing_agent_message_cells() -> None:
    # Rust: app/agent_message_consolidation.rs replaces trailing AgentMessageCell run.
    assert consolidates_trailing_agent_message_cells()


def test_deferred_history_cell_is_inserted_before_consolidation() -> None:
    # Rust inserts deferred cell into overlay/transcript before searching the trailing run.
    assert deferred_history_cell_is_inserted_before_consolidation()


def test_deferred_non_agent_cell_breaks_trailing_run_before_consolidation() -> None:
    # Rust inserts deferred_history_cell before trailing_run_start; a non-agent deferred
    # cell therefore prevents replacing the earlier provisional agent message.
    deferred = AgentMarkdownCell.new("deferred", "/tmp/cwd")
    first = AgentMessageCell(("streaming",), True)
    app = AgentMessageConsolidationApp(
        transcript_cells=[first],
        overlay=TranscriptOverlay([first]),
    )
    tui = Tui()

    consolidated = app.handle_consolidate_agent_message(
        tui,
        "streaming",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.REQUIRED,
        deferred_history_cell=deferred,
    )

    assert consolidated is None
    assert app.transcript_cells == [first, deferred]
    assert app.overlay is not None
    assert app.overlay.inserted_cells == [deferred]
    assert app.overlay.consolidated_ranges == []
    assert app.maybe_finish_stream_reflow_calls == 1
    assert app.finish_required_stream_reflow_calls == 0
    assert tui.frame_requester.scheduled_frames == 0


def test_no_trailing_agent_cells_finishes_stream_reflow_only() -> None:
    # Rust calls maybe_finish_stream_reflow when there is no trailing run to replace.
    assert no_trailing_agent_cells_finishes_stream_reflow_only()


def test_trailing_run_start_ignores_non_tail_agent_cells() -> None:
    cells = [
        AgentMessageCell(("old stream",), True),
        AgentMarkdownCell.new("markdown", "/tmp/cwd"),
        AgentMessageCell(("tail",), True),
    ]

    assert trailing_agent_message_run_start(cells) == 2


def test_consolidation_without_overlay_replaces_transcript_without_frame_request() -> None:
    app = AgentMessageConsolidationApp(
        transcript_cells=[AgentMessageCell(("tail",), True)],
        overlay=None,
    )
    tui = Tui()

    consolidated = app.handle_consolidate_agent_message(
        tui,
        "tail",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.IF_RESIZE_REFLOW_RAN,
    )

    assert app.transcript_cells == [consolidated]
    assert tui.frame_requester.scheduled_frames == 0
    assert app.maybe_finish_stream_reflow_calls == 1


def test_dict_and_object_agent_message_cells_are_supported_semantically() -> None:
    class ObjectAgentMessage:
        kind = "AgentMessageCell"

    app = AgentMessageConsolidationApp(
        transcript_cells=[
            {"kind": "AgentMessageCell"},
            ObjectAgentMessage(),
        ],
        overlay=TranscriptOverlay([{"kind": "AgentMessageCell"}, ObjectAgentMessage()]),
    )
    tui = Tui()

    consolidated = app.handle_consolidate_agent_message(
        tui,
        "source",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.REQUIRED,
    )

    assert app.transcript_cells == [consolidated]
    assert app.finish_required_stream_reflow_calls == 1
