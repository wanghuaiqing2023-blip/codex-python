# Parity source: codex-rs/tui/src/multi_agents.rs

import uuid

from pycodex.tui.multi_agents import (
    AgentMetadata,
    CollabAgentState,
    SpawnRequestSummary,
    agent_picker_status_dot_spans,
    cell_to_text,
    first_agent_state,
    format_agent_picker_item_name,
    next_agent_shortcut_matches,
    previous_agent_shortcut_matches,
    prompt_line,
    spawn_request_spans,
    spawn_request_summary,
    status_summary_line,
    tool_call_history_cell,
    wait_complete_lines,
)


def metadata_for(robie_id, bob_id):
    def inner(thread_id):
        if thread_id == robie_id:
            return AgentMetadata("Robie", "explorer")
        if thread_id == bob_id:
            return AgentMetadata("Bob", "worker")
        return AgentMetadata()
    return inner


def item(tool, status, receivers, prompt=None, model=None, effort=None, states=None):
    return {
        "type": "CollabAgentToolCall",
        "tool": tool,
        "status": status,
        "receiver_thread_ids": receivers,
        "prompt": prompt,
        "model": model,
        "reasoning_effort": effort,
        "agents_states": states or {},
    }


def test_format_agent_picker_item_name_matches_rust_cases():
    assert format_agent_picker_item_name("Nick", "worker", False) == "Nick [worker]"
    assert format_agent_picker_item_name("Nick", None, False) == "Nick"
    assert format_agent_picker_item_name(None, "worker", False) == "[worker]"
    assert format_agent_picker_item_name("  ", "  ", False) == "Agent"
    assert format_agent_picker_item_name("Nick", "worker", True) == "Main [default]"


def test_agent_picker_status_dot_spans_mark_open_agent_green_and_closed_plain():
    open_spans = agent_picker_status_dot_spans(False)
    closed_spans = agent_picker_status_dot_spans(True)

    assert [span.content for span in open_spans] == ["•", " "]
    assert open_spans[0].fg == "green"
    assert [span.content for span in closed_spans] == ["•", " "]
    assert closed_spans[0].fg is None


def test_agent_shortcut_matches_option_arrows_only_on_non_macos():
    assert previous_agent_shortcut_matches(("alt", "left"), False) is True
    assert next_agent_shortcut_matches(("alt", "right"), False) is True
    assert previous_agent_shortcut_matches(("alt", "b"), False) is False
    assert next_agent_shortcut_matches(("alt", "f"), False) is False


def test_spawn_request_summary_only_for_spawn_with_model_and_effort():
    summary = spawn_request_summary(item("SpawnAgent", "Completed", [], model="gpt-5", effort="high"))

    assert summary == SpawnRequestSummary("gpt-5", "high")
    assert spawn_request_summary(item("SpawnAgent", "Completed", [], model="gpt-5")) is None
    assert spawn_request_summary(item("Wait", "Completed", [], model="gpt-5", effort="high")) is None


def test_spawn_request_spans_hide_default_empty_details():
    assert spawn_request_spans(None) == []
    assert spawn_request_spans(SpawnRequestSummary("", "medium")) == []
    assert "(high)" in "".join(span.content for span in spawn_request_spans(SpawnRequestSummary("", "high")))
    assert "(gpt-5 high)" in "".join(span.content for span in spawn_request_spans(SpawnRequestSummary("gpt-5", "high")))


def test_prompt_line_trims_and_truncates_empty_prompt():
    assert prompt_line("   ") is None
    assert prompt_line("  hello  ").text == "hello"


def test_tool_call_history_cell_spawn_send_wait_and_close_text():
    robie_id = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    bob_id = str(uuid.UUID("00000000-0000-0000-0000-000000000003"))
    metadata = metadata_for(robie_id, bob_id)

    spawn = tool_call_history_cell(
        item("SpawnAgent", "Completed", [robie_id], "Compute 11!", "gpt-5", "high"),
        None,
        metadata,
    )
    send = tool_call_history_cell(item("SendInput", "Completed", [robie_id], "Please continue"), None, metadata)
    wait = tool_call_history_cell(item("Wait", "InProgress", [robie_id]), None, metadata)
    finished = tool_call_history_cell(
        item(
            "Wait",
            "Completed",
            [robie_id, bob_id],
            states={robie_id: CollabAgentState("Completed", "39916800"), bob_id: CollabAgentState("Errored", "tool timeout")},
        ),
        None,
        metadata,
    )
    close = tool_call_history_cell(item("CloseAgent", "Completed", [robie_id]), None, metadata)

    text = "\n\n".join(cell_to_text(cell) for cell in [spawn, send, wait, finished, close])
    assert "Spawned Robie [explorer] (gpt-5 high)" in text
    assert "Sent input to Robie [explorer]" in text
    assert "Waiting for Robie [explorer]" in text
    assert "Finished waiting" in text
    assert "Bob [worker]: Error - tool timeout" in text
    assert "Closed Robie [explorer]" in text


def test_in_progress_spawn_send_close_do_not_render():
    tid = str(uuid.uuid4())
    metadata = lambda _tid: AgentMetadata()

    assert tool_call_history_cell(item("SpawnAgent", "InProgress", [tid]), None, metadata) is None
    assert tool_call_history_cell(item("SendInput", "InProgress", [tid]), None, metadata) is None
    assert tool_call_history_cell(item("CloseAgent", "InProgress", [tid]), None, metadata) is None


def test_resume_begin_and_end_uses_first_agent_state_or_fallback_error():
    tid = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    metadata = lambda _tid: AgentMetadata("Robie", "explorer")

    begin = tool_call_history_cell(item("ResumeAgent", "InProgress", [tid]), None, metadata)
    end = tool_call_history_cell(item("ResumeAgent", "Completed", [tid], states={tid: CollabAgentState("Interrupted")}), None, metadata)
    failed = tool_call_history_cell(item("ResumeAgent", "Completed", [tid], states={}), None, metadata)

    assert "Resuming Robie [explorer]" in cell_to_text(begin)
    assert "Interrupted" in cell_to_text(end)
    assert "Error - Agent resume failed" in cell_to_text(failed)


def test_wait_complete_lines_orders_requested_then_extra_sorted():
    robie_id = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    bob_id = str(uuid.UUID("00000000-0000-0000-0000-000000000003"))
    metadata = metadata_for(robie_id, bob_id)

    lines = wait_complete_lines(
        [bob_id],
        {robie_id: CollabAgentState("Completed", "ok"), bob_id: CollabAgentState("Running")},
        metadata,
    )

    assert [line.text.split(":", 1)[0] for line in lines] == ["Bob [worker]", "Robie [explorer]"]


def test_first_agent_state_uses_receivers_then_sorted_extras():
    a = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    b = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
    states = {b: CollabAgentState("Running"), a: CollabAgentState("Completed")}

    assert first_agent_state([b], states).status == "Running"
    assert first_agent_state([], states).status == "Completed"


def test_status_summary_line_completed_and_error_preview():
    assert "Completed - hello world" == status_summary_line(CollabAgentState("Completed", "hello   world"), "fallback").text
    assert "Error - boom" == status_summary_line(CollabAgentState("Errored", "boom"), "fallback").text
    assert "Error - fallback" == status_summary_line(None, "fallback").text
