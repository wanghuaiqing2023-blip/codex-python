from pycodex.core.tools.context import AbortedToolOutput, ToolPayload
from pycodex.core.tools.parallel import (
    TerminalOutcomeFlag,
    abort_message,
    aborted_tool_result,
    failure_response,
    should_return_completed_after_cancellation,
)
from pycodex.core.tools.router import FunctionCallError, ToolCall
from pycodex.protocol import SearchToolCallParams, ToolName


def _call(name: str = "demo_tool", payload: ToolPayload | None = None) -> ToolCall:
    return ToolCall(
        tool_name=ToolName.plain(name),
        call_id="call-1",
        payload=payload or ToolPayload.function("{}"),
    )


def test_abort_message_matches_rust_shell_and_generic_shapes():
    # Rust source: codex-rs/core/src/tools/parallel.rs::abort_message.
    assert abort_message(_call("shell_command"), 2.25) == (
        "Wall time: 2.2 seconds\naborted by user"
    )
    assert abort_message(_call("unified_exec"), 0.04) == (
        "Wall time: 0.0 seconds\naborted by user"
    )
    assert abort_message(_call("other_tool"), 1.26) == "aborted by user after 1.3s"


def test_aborted_tool_result_preserves_call_and_payload():
    call = _call("demo_tool")

    result = aborted_tool_result(call, 0.1)

    assert result.call_id == "call-1"
    assert result.payload is call.payload
    assert isinstance(result.result, AbortedToolOutput)
    assert result.result.message == "aborted by user after 0.1s"
    assert result.post_tool_use_payload is None


def test_should_return_completed_after_cancellation_matches_terminal_or_finished():
    flag = TerminalOutcomeFlag(False)

    assert should_return_completed_after_cancellation(flag, handle_finished=False) is False
    assert should_return_completed_after_cancellation(flag, handle_finished=True) is True

    flag.store(True)

    assert should_return_completed_after_cancellation(flag, handle_finished=False) is True
    assert should_return_completed_after_cancellation(True, handle_finished=False) is True


def test_failure_response_shapes_function_and_tool_search_outputs():
    function_response = failure_response(
        _call("demo_tool"),
        FunctionCallError.respond_to_model("bad input"),
    )

    assert function_response.type == "function_call_output"
    assert function_response.call_id == "call-1"
    assert function_response.output.to_text() == "bad input"
    assert function_response.output.success is False

    tool_search_response = failure_response(
        _call("tool_search", ToolPayload.tool_search(SearchToolCallParams("demo"))),
        "ignored for tool_search",
    )

    assert tool_search_response.type == "tool_search_output"
    assert tool_search_response.call_id == "call-1"
    assert tool_search_response.status == "completed"
    assert tool_search_response.tools == ()
