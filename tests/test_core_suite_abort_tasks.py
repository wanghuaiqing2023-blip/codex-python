import re

from pycodex.core.context import TurnAborted
from pycodex.core.context_manager.normalize import ensure_call_outputs_present
from pycodex.protocol import ContentItem, FunctionCallOutputPayload, ResponseItem


def test_interrupt_long_running_tool_emits_turn_aborted_marker():
    # Rust source: codex/codex-rs/core/tests/suite/abort_tasks.rs
    # Rust test: interrupt_long_running_tool_emits_turn_aborted.
    marker = TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE).render()

    assert marker.startswith("<turn_aborted>")
    assert marker.endswith("</turn_aborted>")
    assert "The user interrupted the previous turn on purpose" in marker
    assert "tools/commands were aborted" in marker


def test_interrupt_tool_records_history_entries():
    # Rust source: codex/codex-rs/core/tests/suite/abort_tasks.rs
    # Rust test: interrupt_tool_records_history_entries.
    call = ResponseItem.function_call(
        name="shell_command",
        arguments='{"command":"sleep 60","timeout_ms":60000}',
        call_id="call-history",
    )

    normalized = ensure_call_outputs_present((call,))

    assert [item.type for item in normalized] == ["function_call", "function_call_output"]
    assert normalized[1].call_id == "call-history"
    assert isinstance(normalized[1].output, FunctionCallOutputPayload)
    assert normalized[1].output.to_text() == "aborted"

    elapsed_output = "Wall time: 0.1 seconds\naborted by user"
    assert re.match(r"^Wall time: ([0-9]+(?:\.[0-9])?) seconds\naborted by user$", elapsed_output)


def test_interrupt_persists_turn_aborted_marker_in_next_request():
    # Rust source: codex/codex-rs/core/tests/suite/abort_tasks.rs
    # Rust test: interrupt_persists_turn_aborted_marker_in_next_request.
    marker = TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE).render()
    follow_up_history = (
        ResponseItem.message("user", (ContentItem.input_text("start interrupt marker"),)),
        ResponseItem.function_call(
            name="shell_command",
            arguments='{"command":"sleep 60","timeout_ms":60000}',
            call_id="call-turn-aborted-marker",
        ),
        ResponseItem(type="function_call_output", call_id="call-turn-aborted-marker", output="aborted"),
        ResponseItem.message("user", (ContentItem.input_text(marker),)),
    )

    user_texts = [
        content.text
        for item in follow_up_history
        if item.type == "message" and item.role == "user"
        for content in item.content
        if content.type == "input_text"
    ]

    assert any("<turn_aborted>" in text for text in user_texts)
    assert any("</turn_aborted>" in text for text in user_texts)
