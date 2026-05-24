import unittest

from pycodex.core import (
    ApplyPatchToolOutput,
    ExecutionStatus,
    FunctionToolOutput,
    ToolCallSource,
    ToolDispatchPayload,
    ToolDispatchRequester,
    ToolDispatchResult,
    ToolInvocation,
    ToolPayload,
    execution_status_for_result,
    tool_dispatch_invocation,
    tool_dispatch_payload,
    tool_dispatch_result,
)
from pycodex.protocol import SearchToolCallParams, ToolName


class ToolDispatchTraceTests(unittest.TestCase):
    def test_dispatch_invocation_records_direct_model_requester(self) -> None:
        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.namespaced("mcp__server__", "query"),
            payload=ToolPayload.function("{}"),
        )

        trace = tool_dispatch_invocation(
            invocation,
            thread_id="thread-1",
            codex_turn_id="turn-1",
        )

        self.assertEqual(trace.thread_id, "thread-1")
        self.assertEqual(trace.codex_turn_id, "turn-1")
        self.assertEqual(trace.tool_call_id, "direct-call")
        self.assertEqual(trace.tool_name, "query")
        self.assertEqual(trace.tool_namespace, "mcp__server__")
        self.assertEqual(trace.requester, ToolDispatchRequester.model("direct-call"))
        self.assertEqual(trace.payload, ToolDispatchPayload(type="function", arguments="{}"))

    def test_dispatch_invocation_records_code_mode_requester(self) -> None:
        invocation = ToolInvocation(
            call_id="code-mode-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
            source=ToolCallSource.code_mode("cell-1", "tool-1"),
        )

        trace = tool_dispatch_invocation(
            invocation,
            thread_id="thread-1",
            codex_turn_id="turn-1",
        )

        self.assertEqual(
            trace.requester,
            ToolDispatchRequester.code_cell("cell-1", "tool-1"),
        )

    def test_dispatch_payload_maps_function_tool_search_and_custom_shapes(self) -> None:
        search_args = SearchToolCallParams("calendar", limit=2)

        self.assertEqual(
            tool_dispatch_payload(ToolPayload.function('{"ok":true}')),
            ToolDispatchPayload(type="function", arguments='{"ok":true}'),
        )
        self.assertEqual(
            tool_dispatch_payload(ToolPayload.tool_search(search_args)),
            ToolDispatchPayload(type="tool_search", arguments=search_args),
        )
        self.assertEqual(
            tool_dispatch_payload(ToolPayload.custom("raw input")),
            ToolDispatchPayload(type="custom", input="raw input"),
        )
        self.assertEqual(
            tool_dispatch_payload(ToolPayload.tool_search(search_args)).to_mapping(),
            {
                "type": "tool_search",
                "arguments": {"query": "calendar", "limit": 2},
            },
        )

    def test_dispatch_result_records_direct_response_item(self) -> None:
        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
        )
        output = FunctionToolOutput.from_text("ok", True)

        result = tool_dispatch_result(invocation, invocation.call_id, invocation.payload, output)

        self.assertEqual(result.type, "direct_response")
        self.assertEqual(result.response_item.type, "function_call_output")
        self.assertEqual(result.response_item.output.to_text(), "ok")

    def test_dispatch_result_records_code_mode_result_value(self) -> None:
        invocation = ToolInvocation(
            call_id="code-call",
            tool_name=ToolName.plain("apply_patch"),
            payload=ToolPayload.function("{}"),
            source=ToolCallSource.code_mode("cell-1", "tool-1"),
        )
        output = ApplyPatchToolOutput.from_text("Done!")

        self.assertEqual(
            tool_dispatch_result(invocation, invocation.call_id, invocation.payload, output),
            ToolDispatchResult.code_mode_response({}),
        )

    def test_execution_status_follows_result_logging_success(self) -> None:
        self.assertEqual(
            execution_status_for_result(FunctionToolOutput.from_text("ok", True)),
            ExecutionStatus.COMPLETED,
        )
        self.assertEqual(
            execution_status_for_result(FunctionToolOutput.from_text("nope", False)),
            ExecutionStatus.FAILED,
        )


if __name__ == "__main__":
    unittest.main()
