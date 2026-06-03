import unittest

from pycodex.core import (
    ApplyPatchToolOutput,
    ExecutionStatus,
    FunctionToolOutput,
    ToolCallSource,
    ToolDispatchPayload,
    ToolDispatchRequester,
    ToolDispatchResult,
    ToolDispatchTrace,
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


    def test_dispatch_trace_variants_reject_invalid_shapes(self) -> None:
        with self.assertRaises(ValueError):
            ToolDispatchRequester(type="other")
        with self.assertRaises(TypeError):
            ToolDispatchRequester.model(123)
        with self.assertRaises(TypeError):
            ToolDispatchRequester.code_cell("cell-1", 123)
        with self.assertRaises(TypeError):
            ToolDispatchPayload(type="function", arguments={})
        with self.assertRaises(TypeError):
            ToolDispatchPayload(type="tool_search", arguments="calendar")
        with self.assertRaises(TypeError):
            ToolDispatchPayload(type="custom", input=123)
        with self.assertRaises(ValueError):
            ToolDispatchPayload(type="local_shell")
        with self.assertRaises(TypeError):
            ToolDispatchResult.direct_response({})
        with self.assertRaises(TypeError):
            ToolDispatchResult.code_mode_response(object())

    def test_dispatch_invocation_rejects_invalid_boundary_fields(self) -> None:
        requester = ToolDispatchRequester.model("call-1")
        payload = ToolDispatchPayload(type="function", arguments="{}")
        with self.assertRaises(TypeError):
            from pycodex.core import ToolDispatchInvocation
            ToolDispatchInvocation(
                thread_id=123,
                codex_turn_id="turn-1",
                tool_call_id="call-1",
                tool_name="tool",
                tool_namespace=None,
                requester=requester,
                payload=payload,
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

    def test_trace_facade_starts_and_records_completed_or_failed(self) -> None:
        class TraceService:
            def __init__(self):
                self.invocations = []
                self.completed = []
                self.failed = []

            def start_tool_dispatch_trace(self, invocation_factory):
                self.invocations.append(invocation_factory())
                return self

            def is_enabled(self):
                return True

            def record_completed(self, status, result):
                self.completed.append((status, result))

            def record_failed(self, error):
                self.failed.append(error)

        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
        )
        service = TraceService()

        trace = ToolDispatchTrace.start(
            invocation,
            service,
            thread_id="thread-1",
            codex_turn_id="turn-1",
        )
        trace.record_completed(
            invocation,
            invocation.call_id,
            invocation.payload,
            FunctionToolOutput.from_text("ok", True),
        )
        trace.record_failed(RuntimeError("boom"))

        self.assertEqual(service.invocations[0].tool_call_id, "direct-call")
        self.assertEqual(service.completed[0][0], ExecutionStatus.COMPLETED)
        self.assertEqual(service.completed[0][1].type, "direct_response")
        self.assertEqual(str(service.failed[0]), "boom")

    def test_trace_facade_supports_mapping_trace_context(self) -> None:
        state = {
            "invocations": [],
            "completed": [],
            "failed": [],
            "is_enabled": True,
        }

        def start_tool_dispatch_trace(invocation_factory):
            state["invocations"].append(invocation_factory())
            return state

        state["start_tool_dispatch_trace"] = start_tool_dispatch_trace

        def record_completed(status, result):
            state["completed"].append((status, result))

        def record_failed(error):
            state["failed"].append(error)

        state["record_completed"] = record_completed
        state["record_failed"] = record_failed

        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
        )

        trace = ToolDispatchTrace.start(
            invocation,
            state,
            thread_id="thread-1",
            codex_turn_id="turn-1",
        )
        trace.record_completed(
            invocation,
            invocation.call_id,
            invocation.payload,
            FunctionToolOutput.from_text("ok", True),
        )
        trace.record_failed(RuntimeError("boom"))

        self.assertEqual(state["invocations"][0].tool_call_id, "direct-call")
        self.assertEqual(state["completed"][0][0], ExecutionStatus.COMPLETED)
        self.assertEqual(state["completed"][0][1].type, "direct_response")
        self.assertEqual(str(state["failed"][0]), "boom")

    def test_trace_facade_mapping_context_respects_disabled_flag(self) -> None:
        state = {
            "invocations": [],
            "completed": [],
            "failed": [],
            "is_enabled": False,
        }

        def start_tool_dispatch_trace(invocation_factory):
            state["invocations"].append(invocation_factory())
            return state

        state["start_tool_dispatch_trace"] = start_tool_dispatch_trace

        def record_completed(status, result):
            state["completed"].append((status, result))

        state["record_completed"] = record_completed

        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
        )

        trace = ToolDispatchTrace.start(
            invocation,
            state,
            thread_id="thread-1",
            codex_turn_id="turn-1",
        )
        trace.record_completed(
            invocation,
            invocation.call_id,
            invocation.payload,
            FunctionToolOutput.from_text("ok", True),
        )

        self.assertEqual(len(state["completed"]), 0)

    def test_trace_facade_skips_completed_record_when_disabled_or_unmappable(self) -> None:
        class DisabledTraceContext:
            def __init__(self):
                self.completed = []

            def is_enabled(self):
                return False

            def record_completed(self, status, result):
                self.completed.append((status, result))

        invocation = ToolInvocation(
            call_id="direct-call",
            tool_name=ToolName.plain("test_tool"),
            payload=ToolPayload.function("{}"),
        )
        context = DisabledTraceContext()

        ToolDispatchTrace(context).record_completed(
            invocation,
            invocation.call_id,
            invocation.payload,
            object(),
        )

        self.assertEqual(context.completed, [])


if __name__ == "__main__":
    unittest.main()
