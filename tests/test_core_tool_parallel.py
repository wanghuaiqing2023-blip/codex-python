import asyncio
import unittest

from pycodex.core.network_approval import CancellationToken
from pycodex.core.tool_context import FunctionToolOutput, JsonToolOutput, ToolPayload
from pycodex.core.tool_lifecycle import ToolCallOutcome
from pycodex.core.tool_lifecycle import ExtensionToolCallSource
from pycodex.core.tool_parallel import (
    TerminalOutcomeFlag,
    ToolCallResult,
    ToolCallRuntime,
    abort_message,
    aborted_tool_result,
    failure_response,
    should_return_completed_after_cancellation,
    tool_runtime_decision,
)
from pycodex.core.tool_registry import RegisteredTool, ToolRegistry
from pycodex.core.tool_router import FunctionCallError, ToolCall, ToolRouter
from pycodex.protocol import ToolName


class Recorder:
    def __init__(self):
        self.outcomes = []

    async def on_tool_finish(self, input):
        self.outcomes.append(input.outcome)


class ToolParallelTests(unittest.TestCase):
    def test_abort_message_matches_shell_and_generic_formats(self) -> None:
        shell = ToolCall(
            tool_name=ToolName.plain("unified_exec"),
            call_id="call-shell",
            payload=ToolPayload.function("{}"),
        )
        generic = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-view",
            payload=ToolPayload.function("{}"),
        )

        self.assertEqual(abort_message(shell, 0.01), "Wall time: 0.1 seconds\naborted by user")
        self.assertEqual(abort_message(generic, 1.234), "aborted by user after 1.2s")

    def test_aborted_tool_result_converts_to_model_output(self) -> None:
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = aborted_tool_result(call, 2.0).to_response_item()

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "call-1")
        self.assertIn("aborted by user after 2.0s", response.output.to_text())

    def test_failure_response_preserves_payload_specific_shape(self) -> None:
        function_call = ToolCall(
            tool_name=ToolName.plain("fn"),
            call_id="call-fn",
            payload=ToolPayload.function("{}"),
        )
        custom_call = ToolCall(
            tool_name=ToolName.plain("custom"),
            call_id="call-custom",
            payload=ToolPayload.custom("input"),
        )

        function_response = failure_response(function_call, FunctionCallError.respond_to_model("nope"))
        custom_response = failure_response(custom_call, "custom failed")

        self.assertEqual(function_response.type, "function_call_output")
        self.assertEqual(function_response.output.success, False)
        self.assertEqual(custom_response.type, "custom_tool_call_output")
        self.assertEqual(custom_response.output.success, False)

    def test_router_and_runtime_report_parallel_cancellation_decision(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain(
                    "exec_command",
                    supports_parallel=True,
                    waits_for_cancellation=True,
                )
            ]
        )
        router = ToolRouter.from_parts(registry, ())
        call = ToolCall(
            tool_name=ToolName.plain("exec_command"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        self.assertTrue(router.tool_waits_for_runtime_cancellation(call))
        decision = tool_runtime_decision(router, call)
        self.assertTrue(decision.supports_parallel)
        self.assertTrue(decision.waits_for_runtime_cancellation)

    def test_terminal_outcome_flag_supports_cancellation_race_decision(self) -> None:
        flag = TerminalOutcomeFlag()

        self.assertFalse(should_return_completed_after_cancellation(flag, handle_finished=False))
        self.assertFalse(flag.swap(True))
        self.assertTrue(should_return_completed_after_cancellation(flag, handle_finished=False))
        self.assertTrue(should_return_completed_after_cancellation(False, handle_finished=True))

    def test_pre_cancelled_runtime_returns_aborted_and_notifies_lifecycle(self) -> None:
        recorder = Recorder()
        runtime = ToolCallRuntime(ToolRouter.from_parts(()), lifecycle_contributors=[recorder])
        token = CancellationToken()
        token.cancel()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(runtime.handle_pre_cancelled_tool_call(call, token, turn_id="turn-1"))

        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.to_response_item().type, "function_call_output")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])

    def test_runtime_aborted_notification_preserves_explicit_source_without_invocation(self) -> None:
        class SourceRecorder:
            def __init__(self):
                self.sources = []

            async def on_tool_finish(self, input):
                self.sources.append(input.source)

        recorder = SourceRecorder()
        runtime = ToolCallRuntime(ToolRouter.from_parts(()), lifecycle_contributors=[recorder])
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        asyncio.run(
            runtime.notify_aborted(
                call,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                turn_id="turn-1",
            )
        )

        self.assertEqual(
            recorder.sources,
            [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")],
        )

    def test_runtime_dispatch_requires_tool_call_result(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def dispatch(received_call, source, token):
            self.assertIs(received_call, call)
            return ToolCallResult(
                call_id=received_call.call_id,
                payload=received_call.payload,
                result=FunctionToolOutput.from_text("ok", True),
            )

        result = asyncio.run(runtime.handle_tool_call_with_source(call, dispatch))

        self.assertEqual(result.to_response_item().output.to_text(), "ok")

    def test_handle_tool_call_wraps_router_dispatch_output(self) -> None:
        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(runtime.handle_tool_call(call))

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "ok")

    def test_handle_tool_call_turns_model_visible_error_into_failure_response(self) -> None:
        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                raise FunctionCallError.respond_to_model("no such tool")

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("missing"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(runtime.handle_tool_call(call))

        self.assertEqual(response.type, "function_call_output")
        self.assertFalse(response.output.success)
        self.assertEqual(response.output.to_text(), "no such tool")

    def test_handle_tool_call_raises_fatal_error(self) -> None:
        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                raise FunctionCallError.fatal("bad payload")

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("broken"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "bad payload"):
            asyncio.run(runtime.handle_tool_call(call))

    def test_tool_call_result_exposes_code_mode_result_like_any_tool_result(self) -> None:
        plain = ToolCallResult(
            call_id="call-plain",
            payload=ToolPayload.function("{}"),
            result=FunctionToolOutput.from_text("plain", True),
        )
        json_result = ToolCallResult(
            call_id="call-json",
            payload=ToolPayload.function("{}"),
            result=JsonToolOutput.new({"ok": True}),
        )

        self.assertEqual(plain.code_mode_result(), {})
        self.assertEqual(json_result.code_mode_result(), {"ok": True})

    def test_tool_call_result_rejects_non_trait_post_hook_payload_shape(self) -> None:
        with self.assertRaisesRegex(TypeError, "PostToolUsePayload"):
            ToolCallResult(
                call_id="call-bad",
                payload=ToolPayload.function("{}"),
                result=FunctionToolOutput.from_text("ok", True),
                post_tool_use_payload={"tool_name": "bad"},
            )


if __name__ == "__main__":
    unittest.main()
