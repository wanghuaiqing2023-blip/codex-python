"""Textual TUI scenarios using the shared Textual automation harness.

Rust evidence:
- `codex-tui/tests/suite/vt100_live_commit.rs`
- `codex-tui/tests/suite/vt100_history.rs`
- `codex-tui/src/chatwidget/tests/status_and_layout.rs`
- `codex-tui/src/chatwidget/tests/composer_submission.rs`

These tests keep the Rust-shaped event trace boundary from the old virtual
terminal harness while moving the UI driver to the Textual product shell.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from pycodex.tui.app.runtime import user_turn_prompt
from pycodex.tui.tests.harness import textual_scenarios

from .harness import agent_delta
from .harness import assert_no_duplicate
from .harness import assert_text_present
from .harness import item_completed_command
from .harness import item_completed_reasoning
from .harness import item_started_command
from .harness import ManualActiveThreadRuntime
from .harness import mcp_server_status_updated
from .harness import reasoning_raw_delta
from .harness import reasoning_summary_delta
from .harness import reasoning_summary_part_added
from .harness import start_textual_scenario
from .harness import thread_closed
from .harness import thread_token_usage_updated
from .harness import turn_completed
from .harness import turn_failed
from .harness import turn_started


def _assert_idle_footer(text: str) -> None:
    assert "gpt-5.5" in text
    assert "codex-python" in text
    assert "status: Ready" not in text


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_textual_harness_runtime_uses_textual_active_thread_boundary() -> None:
    # Rust ownership:
    # codex-tui::app owns the active-thread runtime submit boundary. Textual
    # product harnesses should model that boundary directly.
    assert textual_scenarios.ManualActiveThreadRuntime.__module__.endswith(".runtime")


def test_textual_harness_records_input_to_active_thread_event_trace() -> None:
    # Rust source contract:
    # codex-tui::bottom_pane::chat_composer -> chatwidget::input_submission
    # -> app::thread_routing submits AppCommand::UserTurn to the active thread.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("inspect project")
            await tui.wait_for_submit_count(1)

            assert tui.runtime.submitted_thread_ids == ["primary"]
            op = tui.runtime.submitted_ops[0]
            assert op.kind == "UserTurn"
            assert user_turn_prompt(op) == "inspect project"

            tui.send(turn_started())
            tui.send(agent_delta("done"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "inspect project")
            assert_text_present(text, "done")
            _assert_idle_footer(text)

    asyncio.run(scenario())


def test_textual_harness_streaming_visible_before_turn_completed() -> None:
    # Rust integration contract:
    # vt100_live_commit keeps live output visible before TurnCompleted commits
    # the final turn.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("stream now")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(agent_delta("partial "))
            before_completion = await tui.wait_for_text("partial", timeout=1.0)

            assert "Working" in before_completion
            assert "status: Ready" not in before_completion

            tui.send(agent_delta("answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "partial answer")
            assert_no_duplicate(text, "partial answer")
            _assert_idle_footer(text)

    asyncio.run(scenario())


def test_textual_harness_active_status_uses_rust_interrupt_hint() -> None:
    # Rust source/snapshot contract:
    # - codex-tui::status_indicator_widget renders active turns as
    #   "Working (Ns • esc to interrupt)".
    # - keymap::primary_binding supplies the displayed interrupt binding.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("wait")
            await tui.wait_for_submit_count(1)
            status = tui.status()
            assert "Working (0s" in status
            assert "esc to interrupt" in status
            assert "waiting for model" not in status

            tui.send(turn_started())
            tui.send(agent_delta("done"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

    asyncio.run(scenario())


def test_textual_harness_active_status_uses_remapped_interrupt_binding() -> None:
    # Rust source/test contract:
    # status_indicator_widget::tests::renders_remapped_interrupt_hint proves a
    # remapped chat.interrupt_turn binding appears in the active status row.
    runtime = ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(tui_keymap={"chat": {"interrupt_turn": ["f12"]}})

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("wait with f12")
            await tui.wait_for_submit_count(1)
            status = tui.status()
            assert "Working (0s" in status
            assert "f12 to interrupt" in status
            assert "esc to interrupt" not in status

            tui.send(turn_started())
            tui.send(agent_delta("done"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

    asyncio.run(scenario())


def test_textual_harness_active_status_hides_unbound_interrupt_hint() -> None:
    # Rust source/test contract:
    # keymap::tests proves chat.interrupt_turn = [] is valid. When the primary
    # binding is absent, StatusIndicatorWidget renders only elapsed time.
    runtime = ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(tui_keymap={"chat": {"interrupt_turn": []}})

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("wait without interrupt")
            await tui.wait_for_submit_count(1)
            status = tui.status()
            assert "Working (0s)" in status
            assert "to interrupt" not in status

            tui.send(turn_started())
            tui.send(agent_delta("done"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

    asyncio.run(scenario())


def test_textual_harness_turn_completed_restores_passive_footer() -> None:
    # Rust source/test contract:
    # - codex-tui::status_indicator_widget owns the active
    #   "Working (Ns ... interrupt)" row while a task is running.
    # - codex-tui::bottom_pane::footer owns the passive model/directory footer
    #   once chatwidget::turn_runtime::on_task_complete restores idle state.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("finish and return to footer")
            await tui.wait_for_submit_count(1)
            active_status = tui.status()
            assert "Working (0s" in active_status
            assert "esc to interrupt" in active_status

            tui.send(turn_started())
            tui.send(agent_delta("done"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            idle_status = tui.status()
            assert "Working" not in idle_status
            assert "to interrupt" not in idle_status
            assert "status: Ready" not in idle_status
            _assert_idle_footer(idle_status)

            text = tui.text()
            assert_text_present(text, "done")
            assert_no_duplicate(text, "done")

    asyncio.run(scenario())


def test_textual_harness_live_delta_overflow_remains_in_transcript() -> None:
    # Rust integration/source contract:
    # - codex-tui/tests/suite/vt100_live_commit.rs::live_001_commit_on_overflow
    #   keeps early live rows visible/committed when the live area overflows.
    # - chatwidget::streaming handles AgentMessageDelta before TurnCompleted
    #   without losing earlier fragments.
    async def scenario() -> None:
        async with start_textual_scenario(size=(60, 10)) as tui:
            await tui.submit("overflow live")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            for index in range(1, 10):
                tui.send(agent_delta(f"live overflow line {index:02d}\n"))

            before_completion = await tui.wait_for_text("live overflow line 09", timeout=1.0)
            assert_text_present(before_completion, "live overflow line 01")
            assert_text_present(before_completion, "live overflow line 09")
            assert "Working" in before_completion

            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "live overflow line 01")
            assert_text_present(text, "live overflow line 09")
            assert text.count("live overflow line") == 9

    asyncio.run(scenario())


def test_textual_harness_long_reply_commits_without_screen_height_clipping() -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::streaming and history insertion retain the full
    #   assistant message; viewport height affects rendering/scrolling, not the
    #   committed transcript content.
    # - Textual owns the scrollable transcript pane, so the product shell should
    #   keep the complete message in transcript state even on a short terminal.
    long_reply = "\n".join(f"answer line {index:02d}" for index in range(1, 41))

    async def scenario() -> None:
        async with start_textual_scenario(size=(60, 8)) as tui:
            await tui.submit("long reply")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(agent_delta(long_reply))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            blocks = tui.blocks()
            assert ("codex", long_reply) in blocks
            text = tui.text()
            assert_text_present(text, "answer line 01")
            assert_text_present(text, "answer line 40")
            assert text.count("answer line") == 40

    asyncio.run(scenario())


def test_textual_harness_keeps_progress_status_out_of_agent_text() -> None:
    # Rust source contract:
    # codex-tui redraws status/progress and streaming assistant text as separate
    # surfaces. Once AgentMessageDelta starts, progress/status text must not be
    # appended to the assistant transcript block.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("stream cleanly")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**reasoning**"))
            await tui.wait_for_text("reasoning", timeout=1.0)

            tui.send(agent_delta("clean"))
            after_first_delta = await tui.wait_for_text("clean", timeout=1.0)
            codex_segment = after_first_delta.rsplit("codex", 1)[-1]
            assert "elapsed;" not in codex_segment
            assert "Working" not in codex_segment

            tui.send(agent_delta(" stream"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            blocks = tui.blocks()
            assert ("codex", "clean stream") in blocks
            assert_no_duplicate(tui.text(), "clean stream")

    asyncio.run(scenario())


def test_textual_harness_submits_queued_followup_after_turn_completed() -> None:
    # Rust source/test contract:
    # - codex-tui::bottom_pane::chat_composer returns InputResult::Submitted
    #   for committed composer input.
    # - codex-tui::app keeps accepting input while turns complete.
    # - codex-tui::input_queue sends the queued follow-up after TurnCompleted.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("first turn")
            await tui.wait_for_submit_count(1)
            first_op = tui.runtime.submitted_ops[0]
            assert first_op.kind == "UserTurn"
            assert user_turn_prompt(first_op) == "first turn"

            await tui.submit("second turn")
            assert_text_present(tui.text(), "Queued follow-up inputs")

            tui.send(turn_started(turn_id="turn-1"))
            tui.send(agent_delta("first answer", turn_id="turn-1"))
            tui.send(turn_completed(turn_id="turn-1"))

            await tui.wait_for_submit_count(2)
            second_op = tui.runtime.submitted_ops[1]
            assert second_op.kind == "UserTurn"
            assert user_turn_prompt(second_op) == "second turn"

            tui.send(turn_started(turn_id="turn-2"))
            tui.send(agent_delta("second answer", turn_id="turn-2"))
            tui.send(turn_completed(turn_id="turn-2"))
            await tui.wait_for_idle()

            assert tui.runtime.submitted_thread_ids == ["primary", "primary"]
            text = tui.text()
            assert_text_present(text, "first turn")
            assert_text_present(text, "first answer")
            assert_text_present(text, "Queued follow-up inputs")
            assert_text_present(text, "second turn")
            assert_text_present(text, "second answer")
            assert_no_duplicate(text, "first answer")
            assert_no_duplicate(text, "second answer")
            _assert_idle_footer(text)

    asyncio.run(scenario())


def test_textual_harness_reasoning_summary_enters_transcript_without_raw_reasoning() -> None:
    # Rust source contract:
    # chatwidget::protocol routes ReasoningSummaryTextDelta into live status and
    # chatwidget::streaming finalizes it through history_cell::messages::
    # new_reasoning_summary_block, which uses the first bold span as status
    # header but renders only the post-header summary body in history. Raw
    # reasoning text is hidden unless explicitly enabled.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("reason")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Inspecting** files"))
            await tui.wait_for_text("Inspecting", timeout=1.0)
            tui.send(reasoning_summary_part_added())
            tui.send(reasoning_summary_delta("**Planning** answer"))
            tui.send(reasoning_raw_delta("raw hidden chain"))
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "reasoning")
            assert_text_present(text, "files")
            assert_text_present(text, "answer")
            assert "**Inspecting**" not in text
            assert "raw hidden chain" not in text
            assert_no_duplicate(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_live_reasoning_summary_is_not_rendered_twice_when_item_completes() -> None:
    # Rust source/test contract:
    # codex-tui::chatwidget::tests::history_replay::
    # live_reasoning_summary_is_not_rendered_twice_when_item_completes proves
    # live ReasoningSummaryTextDelta and the final Reasoning item summary
    # consolidate into one reasoning history block, not duplicate transcript
    # text. Raw reasoning content remains hidden by default.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("reason once")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Inspecting** project"))
            await tui.wait_for_text("Inspecting", timeout=1.0)
            tui.send(
                item_completed_reasoning(
                    "**Inspecting** project",
                    content=["raw hidden chain"],
                )
            )
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert "**Inspecting** project" not in text
            assert "raw hidden chain" not in text
            assert_no_duplicate(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_reasoning_projection_trace_classifies_summary_and_raw(
    tmp_path,
    monkeypatch,
) -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::protocol routes ReasoningSummaryTextDelta into
    #   visible reasoning summary state.
    # - ReasoningTextDelta is raw reasoning and is only visible when
    #   show_raw_agent_reasoning is true.
    # - chatwidget::replay records completed Reasoning.summary by default while
    #   keeping Reasoning.content gated. The trace is content-free: it records
    #   event classification and visibility only, never reasoning text.
    trace_path = tmp_path / "reasoning-trace.jsonl"
    monkeypatch.setenv("PYCODEX_TUI_REASONING_TRACE", str(trace_path))

    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("trace reason")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Inspecting** project details"))
            tui.send(reasoning_raw_delta("raw hidden chain"))
            tui.send(
                item_completed_reasoning(
                    "**Inspecting** project details",
                    content=["raw completed reasoning must stay hidden"],
                )
            )
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "project details")
            assert "**Inspecting**" not in text
            assert "raw hidden chain" not in text
            assert "raw completed reasoning must stay hidden" not in text

    asyncio.run(scenario())

    records = _jsonl(trace_path)
    assert {
        "kind": "ReasoningSummaryTextDelta",
        "source": "summary_delta",
        "displayed": True,
    } in [{key: record[key] for key in ("kind", "source", "displayed")} for record in records]
    assert {
        "kind": "ReasoningTextDelta",
        "source": "raw_delta",
        "displayed": False,
    } in [{key: record[key] for key in ("kind", "source", "displayed")} for record in records]
    completed = [record for record in records if record.get("source") == "completed_reasoning"]
    assert completed
    assert completed[-1]["displayed"] is True
    assert completed[-1]["summary_present"] is True
    assert completed[-1]["content_present"] is True
    serialized = trace_path.read_text(encoding="utf-8")
    assert "raw hidden chain" not in serialized
    assert "raw completed reasoning must stay hidden" not in serialized
    assert "**Inspecting** project" not in serialized


def test_textual_harness_completed_reasoning_content_only_is_hidden_by_default() -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::replay::handle_thread_item only replays
    #   ThreadItem::Reasoning.content when show_raw_agent_reasoning is true.
    # - codex-tui::chatwidget::protocol gates live ReasoningTextDelta the same
    #   way. A completed reasoning item with raw content but no summary must not
    #   create a visible reasoning block in the default product path.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("content only")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(
                item_completed_reasoning(
                    [],
                    content=["raw completed reasoning must stay hidden"],
                )
            )
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert "raw completed reasoning must stay hidden" not in text
            assert_text_present(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_reasoning_summary_event_displays_even_when_request_summary_none() -> None:
    # Rust source/test contract:
    # - codex-core config accepts model_reasoning_summary = "none" and uses it
    #   while constructing model requests.
    # - codex-tui::chatwidget::protocol does not re-check that request config
    #   when a ReasoningSummaryTextDelta has already arrived; server-provided
    #   summary events are rendered, while raw reasoning remains gated.
    runtime = ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(model_reasoning_summary="none", show_raw_agent_reasoning=False)

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("reason disabled")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Inspecting** files"))
            tui.send(reasoning_summary_part_added())
            tui.send(reasoning_summary_delta("**Planning** answer"))
            tui.send(reasoning_raw_delta("raw hidden chain"))
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "reasoning")
            assert_text_present(text, "files")
            assert_text_present(text, "answer")
            assert "**Inspecting**" not in text
            assert "raw hidden chain" not in text
            assert_text_present(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_hide_agent_reasoning_does_not_filter_summary_events() -> None:
    # Rust source contract:
    # - codex-core/src/config/mod.rs loads hide_agent_reasoning from Config.
    # - codex-tui keeps reasoning summary and raw reasoning as distinct events;
    #   chatwidget::protocol always routes ReasoningSummaryTextDelta, while
    #   ReasoningTextDelta is still gated by show_raw_agent_reasoning.
    runtime = ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(
        hide_agent_reasoning=True,
        model_reasoning_summary="auto",
        show_raw_agent_reasoning=False,
    )

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("reason hidden")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Inspecting** files"))
            tui.send(reasoning_raw_delta("raw hidden chain"))
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "reasoning")
            assert_text_present(text, "files")
            assert "**Inspecting**" not in text
            assert "raw hidden chain" not in text
            assert_text_present(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_raw_reasoning_config_can_show_raw_without_summary() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::protocol only routes ReasoningTextDelta when
    # show_raw_agent_reasoning is enabled. Server-provided summary deltas are
    # still rendered if they arrive.
    runtime = ManualActiveThreadRuntime()
    runtime.session_config = SimpleNamespace(model_reasoning_summary="none", show_raw_agent_reasoning=True)

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("raw enabled")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(reasoning_summary_delta("**Summary hidden**"))
            tui.send(reasoning_raw_delta("raw visible when configured"))
            tui.send(agent_delta("final answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert "**Summary hidden**" not in text
            assert_text_present(text, "raw visible when configured")
            assert_text_present(text, "final answer")

    asyncio.run(scenario())


def test_textual_harness_tool_lifecycle_is_visible_before_final_answer() -> None:
    # Rust source contract:
    # ServerNotification::ItemStarted/ItemCompleted for CommandExecution is
    # routed through chatwidget::protocol and rendered as live work before the
    # assistant final answer.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("use tool")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(item_started_command("Get-ChildItem"))
            before_answer = await tui.wait_for_text("Get-ChildItem", timeout=1.0)
            assert "final answer" not in before_answer
            assert "Running Get-ChildItem" in tui.status()
            assert ("exec", "\u2022 Running Get-ChildItem") in tui.blocks()
            assert ("status", "Running Get-ChildItem") not in tui.blocks()
            tui.send(reasoning_summary_delta("**Inspecting** project files"))
            await tui.pilot.pause(0.05)
            assert "Running Get-ChildItem" in tui.status()
            assert ("exec", "\u2022 Running Get-ChildItem") in tui.blocks()

            tui.send(item_completed_command("Get-ChildItem", aggregated_output="README.md\npycodex"))
            await tui.wait_for_text("Ran Get-ChildItem", timeout=1.0)
            assert ("exec", "\u2022 Ran Get-ChildItem\n  \u2503README.md\n    pycodex") in tui.blocks()
            tui.send(agent_delta("final answer"))
            await tui.wait_for_text("final answer", timeout=1.0)
            assert not [block for block in tui.blocks() if block[0] == "exec"]
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "final answer")
            assert not [
                block
                for block in tui.blocks()
                if block[0] == "status" and ("Running Get-ChildItem" in block[1] or "Completed: Get-ChildItem" in block[1])
            ]
            _assert_idle_footer(text)

    asyncio.run(scenario())


def test_textual_harness_live_exec_block_is_compacted_to_rust_tool_line_limit() -> None:
    # Rust source contract:
    # exec_cell::render caps tool-call display height (`TOOL_CALL_MAX_LINES`) so
    # active command execution remains a bounded live cell rather than pushing
    # the whole TUI downward as more tools start.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("use many tools")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            for index in range(7):
                tui.send(item_started_command(f"tool-{index}", item_id=f"cmd-{index}"))
            await tui.wait_for_text("tool-6", timeout=1.0)

            exec_blocks = [text for label, text in tui.blocks() if label == "exec"]
            assert len(exec_blocks) == 1
            exec_lines = exec_blocks[0].splitlines()
            assert len(exec_lines) == 5
            assert "tool-6" in exec_blocks[0]
            assert "+3 more running" in exec_blocks[0]
            assert "tool-0" not in exec_blocks[0]
            assert "Running tool-6" in tui.status()

    asyncio.run(scenario())


def test_textual_harness_parallel_tool_lifecycle_keeps_ran_and_called_until_answer() -> None:
    # Rust source contract:
    # - codex-core::tools::parallel may have multiple tool calls in flight.
    # - codex-tui::chatwidget renders command execution lifecycle rows before
    #   assistant text takes over the live area.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("use parallel tools")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(item_started_command("Get-ChildItem", item_id="cmd-1"))
            tui.send(item_started_command("git status --short", item_id="cmd-2"))
            await tui.wait_for_text("git status --short", timeout=1.0)

            exec_blocks = [text for label, text in tui.blocks() if label == "exec"]
            assert exec_blocks == ["\u2022 Running Get-ChildItem\n\u2022 Running git status --short"]

            tui.send(item_completed_command("Get-ChildItem", item_id="cmd-1"))
            tui.send(item_completed_command("git status --short", item_id="cmd-2", status="Failed", aggregated_output="fatal: not a repo", exit_code=1))
            await tui.wait_for_text("Ran git status --short", timeout=1.0)

            exec_blocks = [text for label, text in tui.blocks() if label == "exec"]
            assert exec_blocks == [
                "\u2022 Ran Get-ChildItem\n  \u2503(no output)\n\u2022 Ran git status --short\n  \u2503fatal: not a repo"
            ]

            tui.send(agent_delta("answer starts"))
            await tui.wait_for_text("answer starts", timeout=1.0)
            assert not [block for block in tui.blocks() if block[0] == "exec"]
            tui.send(turn_completed())
            await tui.wait_for_idle()

    asyncio.run(scenario())


def test_textual_harness_completed_tool_output_is_truncated_with_transcript_hint() -> None:
    # Rust source contract:
    # - codex-tui::exec_cell::render::command_display_lines renders completed
    #   command output under the Ran row.
    # - exec_cell::render::TOOL_CALL_MAX_LINES caps visible tool output and
    #   includes the transcript shortcut hint for hidden output.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("use verbose tool")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(item_started_command("Get-Content big.log"))
            output = "\n".join(f"line-{index}" for index in range(1, 12))
            tui.send(item_completed_command("Get-Content big.log", aggregated_output=output))
            await tui.wait_for_text("ctrl + t to view transcript", timeout=1.0)

            exec_blocks = [text for label, text in tui.blocks() if label == "exec"]
            assert len(exec_blocks) == 1
            exec_text = exec_blocks[0]
            assert "• Ran Get-Content big.log" in exec_text
            assert "鈥?" not in exec_text
            assert "line-1" in exec_text
            assert "line-11" in exec_text
            assert "...+" in exec_text
            assert "ctrl + t to view transcript" in exec_text

    asyncio.run(scenario())


def test_textual_harness_token_usage_update_refreshes_idle_footer() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::protocol maps ThreadTokenUsageUpdated into
    # ChatWidget token_info, and bottom_pane::footer projects context remaining
    # from that runtime state once the turn returns to Ready.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("usage")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(
                thread_token_usage_updated(
                    total_tokens=100_000,
                    input_tokens=40_000,
                    output_tokens=60_000,
                    model_context_window=200_000,
                )
            )
            tui.send(agent_delta("usage answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()
            await tui.wait_for_text("Context 50% left", timeout=1.0)

            text = tui.text()
            assert_text_present(text, "usage answer")
            assert_text_present(tui.status(), "Context 50% left")

    asyncio.run(scenario())


def test_textual_harness_mcp_startup_warning_is_not_duplicated() -> None:
    # Rust source contract:
    # codex-tui::chatwidget::mcp_startup owns MCP startup headers/warnings.
    # The Textual product projection must not expose two visible warning lanes
    # for the same McpServerStatusUpdated failure.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("mcp")
            await tui.wait_for_submit_count(1)
            tui.app.app_runtime.chat_widget.mcp_startup.set_mcp_startup_expected_servers(["node_repl"])
            tui.send(turn_started())
            tui.send(mcp_server_status_updated("node_repl", "starting"))
            await tui.wait_for_text("Booting MCP server: node_repl", timeout=1.0)
            tui.send(
                mcp_server_status_updated(
                    "node_repl",
                    "failed",
                    error="MCP client for `node_repl` failed to start: unavailable",
                )
            )
            tui.send(agent_delta("mcp answer"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "Booting MCP server: node_repl")
            assert_text_present(text, "MCP client for `node_repl` failed to start: unavailable")
            assert_text_present(text, "MCP startup incomplete (failed: node_repl)")
            assert_text_present(text, "mcp answer")
            assert text.count("MCP client for `node_repl` failed to start: unavailable") == 1
            assert text.count("MCP startup incomplete (failed: node_repl)") == 1

    asyncio.run(scenario())


def test_textual_harness_waits_for_delayed_turn_started() -> None:
    # Rust source contract:
    # codex-tui::app keeps polling the active thread stream; an empty poll is
    # not terminal and must not complete the turn before TurnStarted arrives.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("complex long question")
            await tui.wait_for_submit_count(1)
            await asyncio.sleep(0.15)

            assert tui.app._busy
            assert "delayed response" not in tui.text()

            tui.send(turn_started())
            tui.send(agent_delta("delayed response"))
            tui.send(turn_completed())
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, "delayed response")
            assert_no_duplicate(text, "delayed response")
            _assert_idle_footer(text)

    asyncio.run(scenario())


def test_textual_harness_active_agent_thread_closed_failover_info() -> None:
    # Rust source/test contract:
    # codex-tui::app::thread_routing handles unexpected active non-primary
    # ThreadClosed notifications before chatwidget dispatch, switches back to
    # the primary thread, and reports the failover as info text.
    primary_thread_id = "123e4567-e89b-12d3-a456-426614174000"
    agent_thread_id = "123e4567-e89b-12d3-a456-426614174111"
    runtime = ManualActiveThreadRuntime()
    runtime.thread_id = agent_thread_id
    runtime.primary_thread_id = primary_thread_id

    async def scenario() -> None:
        async with start_textual_scenario(runtime=runtime) as tui:
            await tui.submit("watch agent")
            await tui.wait_for_submit_count(1)
            tui.send(thread_closed(agent_thread_id))
            tui.send(turn_completed(thread_id=agent_thread_id))
            await tui.wait_for_idle()

            text = tui.text()
            assert_text_present(text, f"Agent thread {agent_thread_id} closed. Switched back to main thread.")
            assert "codex\nAgent thread" not in text
            assert tui.app.app_runtime.routing_state.active_thread_id == primary_thread_id
            assert primary_thread_id in tui.app.app_runtime.routing_state.primary_thread_id

    asyncio.run(scenario())


def test_textual_harness_failed_turn_keeps_error_visible_and_records_code() -> None:
    # Rust source contract:
    # codex-tui keeps failed turn output visible and records the terminal app
    # exit status at the TUI boundary.
    async def scenario() -> None:
        async with start_textual_scenario() as tui:
            await tui.submit("fail please")
            await tui.wait_for_submit_count(1)
            tui.send(turn_started())
            tui.send(turn_failed("synthetic failure", exit_code=7))
            await tui.wait_for_idle()

            text = tui.text()
            assert tui.app.exit_code == 7
            assert_text_present(text, "fail please")
            assert_text_present(text, "synthetic failure")

    asyncio.run(scenario())
