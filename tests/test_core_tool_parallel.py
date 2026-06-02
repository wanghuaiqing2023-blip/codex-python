import asyncio
import unittest

from pycodex.core import tool_parallel as tool_parallel_module
from pycodex.core.network_approval import CancellationToken
from pycodex.core.hook_names import HookToolName
from pycodex.core.hook_runtime import PostToolUseHookOutcome, PreToolUseHookResult
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
from pycodex.core.tool_registry import PostToolUsePayload, RegisteredTool, ToolCallSource, ToolInvocation, ToolRegistry
from pycodex.core.tool_router import FunctionCallError, ToolCall, ToolRouter
from pycodex.protocol import SearchToolCallParams, ToolName


class Recorder:
    def __init__(self):
        self.starts = []
        self.outcomes = []
        self.sources = []
        self.call_ids = []
        self.tool_names = []
        self.turn_ids = []
        self.session_stores = []
        self.thread_stores = []
        self.turn_stores = []

    async def on_tool_start(self, input):
        self.starts.append(input)

    async def on_tool_finish(self, input):
        self.outcomes.append(input.outcome)
        self.sources.append(input.source)
        self.call_ids.append(input.call_id)
        self.tool_names.append(input.tool_name)
        self.turn_ids.append(input.turn_id)
        self.session_stores.append(input.session_store)
        self.thread_stores.append(input.thread_store)
        self.turn_stores.append(input.turn_store)


class ToolParallelTests(unittest.TestCase):
    def test_abort_message_matches_shell_and_generic_formats(self) -> None:
        shell = ToolCall(
            tool_name=ToolName.plain("unified_exec"),
            call_id="call-shell",
            payload=ToolPayload.function("{}"),
        )
        shell_command = ToolCall(
            tool_name=ToolName.plain("shell_command"),
            call_id="call-shell-command",
            payload=ToolPayload.function("{}"),
        )
        generic = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-view",
            payload=ToolPayload.function("{}"),
        )
        namespaced_shell = ToolCall(
            tool_name=ToolName.namespaced("functions.", "shell_command"),
            call_id="call-namespaced-shell",
            payload=ToolPayload.function("{}"),
        )
        namespaced_unified_exec = ToolCall(
            tool_name=ToolName.namespaced("functions.", "unified_exec"),
            call_id="call-namespaced-unified-exec",
            payload=ToolPayload.function("{}"),
        )

        self.assertEqual(abort_message(shell, 0.01), "Wall time: 0.0 seconds\naborted by user")
        self.assertEqual(abort_message(shell_command, 1.234), "Wall time: 1.2 seconds\naborted by user")
        self.assertEqual(abort_message(generic, 1.234), "aborted by user after 1.2s")
        self.assertEqual(abort_message(namespaced_shell, 1.234), "aborted by user after 1.2s")
        self.assertEqual(abort_message(namespaced_unified_exec, 1.234), "aborted by user after 1.2s")

    def test_aborted_tool_result_converts_to_model_output(self) -> None:
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = aborted_tool_result(call, 2.0)
        response = result.to_response_item()

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "call-1")
        self.assertIn("aborted by user after 2.0s", response.output.to_text())
        self.assertIsNone(result.post_tool_use_payload)
        self.assertEqual(result.code_mode_result(), "aborted by user after 2.0s")

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
        search_call = ToolCall(
            tool_name=ToolName.plain("tool_search"),
            call_id="call-search",
            payload=ToolPayload.tool_search(SearchToolCallParams("query")),
        )

        function_response = failure_response(function_call, FunctionCallError.respond_to_model("nope"))
        custom_response = failure_response(custom_call, "custom failed")
        search_response = failure_response(search_call, "search failed")

        self.assertEqual(function_response.type, "function_call_output")
        self.assertEqual(function_response.call_id, "call-fn")
        self.assertEqual(function_response.output.success, False)
        self.assertEqual(function_response.output.to_text(), "nope")
        self.assertEqual(custom_response.type, "custom_tool_call_output")
        self.assertEqual(custom_response.call_id, "call-custom")
        self.assertIsNone(custom_response.name)
        self.assertEqual(custom_response.output.success, False)
        self.assertEqual(custom_response.output.to_text(), "custom failed")
        self.assertEqual(search_response.type, "tool_search_output")
        self.assertEqual(search_response.call_id, "call-search")
        self.assertEqual(search_response.status, "completed")
        self.assertEqual(search_response.execution, "client")
        self.assertEqual(search_response.tools, ())

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

        result = asyncio.run(
            runtime.handle_pre_cancelled_tool_call(
                call,
                token,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.to_response_item().type, "function_call_output")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.tool_names, [ToolName.plain("view_image")])
        self.assertEqual(recorder.turn_ids, ["turn-1"])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])
        self.assertEqual(
            recorder.sources,
            [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")],
        )

    def test_pre_cancelled_runtime_defaults_lifecycle_source_to_direct(self) -> None:
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
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.direct()])

    def test_pre_cancelled_runtime_clamps_abort_elapsed_seconds(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        token = CancellationToken()
        token.cancel()
        call = ToolCall(
            tool_name=ToolName.plain("unified_exec"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            runtime.handle_pre_cancelled_tool_call(
                call,
                token,
                elapsed_seconds=0.01,
            )
        )

        self.assertIsInstance(result, ToolCallResult)
        self.assertEqual(result.to_response_item().output.to_text(), "Wall time: 0.1 seconds\naborted by user")

    def test_pre_cancelled_handle_tool_call_with_source_defaults_abort_elapsed_seconds(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        token = CancellationToken()
        token.cancel()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def dispatch(received_call, source, received_token):
            raise AssertionError("pre-cancelled calls should not dispatch")

        result = asyncio.run(
            runtime.handle_tool_call_with_source(
                call,
                dispatch,
                cancellation_token=token,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "aborted by user after 0.1s")

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
        observed = {}
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )
        token = CancellationToken()

        async def dispatch(received_call, source, token):
            self.assertIs(received_call, call)
            observed["source"] = source
            observed["cancellation_token"] = token
            return ToolCallResult(
                call_id=received_call.call_id,
                payload=received_call.payload,
                result=FunctionToolOutput.from_text("ok", True),
            )

        result = asyncio.run(
            runtime.handle_tool_call_with_source(
                call,
                dispatch,
                cancellation_token=token,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(observed["source"], ToolCallSource.code_mode("cell-1", "runtime-tool-1"))
        self.assertIs(observed["cancellation_token"], token)

    def test_runtime_dispatch_preserves_existing_tool_call_result(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )
        expected = ToolCallResult(
            call_id="call-1",
            payload=call.payload,
            result=FunctionToolOutput.from_text("ok", True),
            post_tool_use_payload=PostToolUsePayload(
                tool_name=HookToolName.new("view_image"),
                tool_use_id="call-1",
                tool_input={},
                tool_response="ok",
            ),
        )

        async def dispatch(received_call, source, token):
            return expected

        result = asyncio.run(runtime.handle_tool_call_with_source(call, dispatch))

        self.assertIs(result, expected)
        self.assertEqual(result.post_tool_use_payload, expected.post_tool_use_payload)

    def test_runtime_dispatch_defaults_to_direct_source(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        observed = {}
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def dispatch(received_call, source, token):
            observed["call"] = received_call
            observed["source"] = source
            observed["cancellation_token"] = token
            return ToolCallResult(
                call_id=received_call.call_id,
                payload=received_call.payload,
                result=FunctionToolOutput.from_text("ok", True),
            )

        result = asyncio.run(runtime.handle_tool_call_with_source(call, dispatch))

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertIs(observed["call"], call)
        self.assertEqual(observed["source"], ToolCallSource.direct())
        self.assertIsInstance(observed["cancellation_token"], CancellationToken)

    def test_runtime_dispatch_rejects_non_tool_call_result(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def dispatch(received_call, source, token):
            return FunctionToolOutput.from_text("ok", True)

        with self.assertRaisesRegex(TypeError, "dispatch must return ToolCallResult"):
            asyncio.run(runtime.handle_tool_call_with_source(call, dispatch))

    def test_parallel_dispatches_share_execution_gate(self) -> None:
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("parallel_tool", supports_parallel=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        first_call = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-1",
            payload=ToolPayload.function("{}"),
        )
        second_call = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-2",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            first_started = asyncio.Event()
            release_first = asyncio.Event()
            second_entered = asyncio.Event()

            async def dispatch(received_call, source, token):
                if received_call.call_id == "call-parallel-1":
                    first_started.set()
                    await release_first.wait()
                else:
                    second_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            first_task = asyncio.create_task(runtime.handle_tool_call_with_source(first_call, dispatch))
            await first_started.wait()
            second_task = asyncio.create_task(runtime.handle_tool_call_with_source(second_call, dispatch))
            await second_entered.wait()
            release_first.set()
            return await asyncio.gather(first_task, second_task)

        first_result, second_result = asyncio.run(scenario())

        self.assertEqual(first_result.to_response_item().output.to_text(), "call-parallel-1")
        self.assertEqual(second_result.to_response_item().output.to_text(), "call-parallel-2")

    def test_non_parallel_dispatch_waits_for_active_parallel_dispatch(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("parallel_tool", supports_parallel=True),
                RegisteredTool.plain("exclusive_tool", supports_parallel=False),
            ]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        parallel_call = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel",
            payload=ToolPayload.function("{}"),
        )
        exclusive_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            parallel_started = asyncio.Event()
            release_parallel = asyncio.Event()
            exclusive_entered = asyncio.Event()

            async def dispatch(received_call, source, token):
                if received_call.call_id == "call-parallel":
                    parallel_started.set()
                    await release_parallel.wait()
                else:
                    exclusive_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            parallel_task = asyncio.create_task(runtime.handle_tool_call_with_source(parallel_call, dispatch))
            await parallel_started.wait()
            exclusive_task = asyncio.create_task(runtime.handle_tool_call_with_source(exclusive_call, dispatch))
            await asyncio.sleep(0)
            self.assertFalse(exclusive_entered.is_set())
            release_parallel.set()
            parallel_result = await parallel_task
            exclusive_result = await exclusive_task
            return parallel_result, exclusive_result

        parallel_result, exclusive_result = asyncio.run(scenario())

        self.assertEqual(parallel_result.to_response_item().output.to_text(), "call-parallel")
        self.assertEqual(exclusive_result.to_response_item().output.to_text(), "call-exclusive")

    def test_non_parallel_dispatches_are_mutually_exclusive(self) -> None:
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("exclusive_tool", supports_parallel=False)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        first_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive-1",
            payload=ToolPayload.function("{}"),
        )
        second_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive-2",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            first_entered = asyncio.Event()
            release_first = asyncio.Event()
            second_entered = asyncio.Event()

            async def dispatch(received_call, source, token):
                if received_call.call_id == "call-exclusive-1":
                    first_entered.set()
                    await release_first.wait()
                else:
                    second_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            first_task = asyncio.create_task(runtime.handle_tool_call_with_source(first_call, dispatch))
            await first_entered.wait()
            second_task = asyncio.create_task(runtime.handle_tool_call_with_source(second_call, dispatch))
            await asyncio.sleep(0)
            self.assertFalse(second_entered.is_set())
            release_first.set()
            first_result = await first_task
            second_result = await second_task
            return first_result, second_result

        first_result, second_result = asyncio.run(scenario())

        self.assertEqual(first_result.to_response_item().output.to_text(), "call-exclusive-1")
        self.assertEqual(second_result.to_response_item().output.to_text(), "call-exclusive-2")

    def test_waiting_non_parallel_dispatch_blocks_later_parallel_dispatch(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("parallel_tool", supports_parallel=True),
                RegisteredTool.plain("exclusive_tool", supports_parallel=False),
            ]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        first_parallel = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-1",
            payload=ToolPayload.function("{}"),
        )
        exclusive_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive",
            payload=ToolPayload.function("{}"),
        )
        later_parallel = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-2",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            first_parallel_started = asyncio.Event()
            release_first_parallel = asyncio.Event()
            exclusive_entered = asyncio.Event()
            release_exclusive = asyncio.Event()
            later_parallel_entered = asyncio.Event()

            async def dispatch(received_call, source, token):
                if received_call.call_id == "call-parallel-1":
                    first_parallel_started.set()
                    await release_first_parallel.wait()
                elif received_call.call_id == "call-exclusive":
                    exclusive_entered.set()
                    await release_exclusive.wait()
                else:
                    later_parallel_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            first_task = asyncio.create_task(runtime.handle_tool_call_with_source(first_parallel, dispatch))
            await first_parallel_started.wait()
            exclusive_task = asyncio.create_task(runtime.handle_tool_call_with_source(exclusive_call, dispatch))
            await asyncio.sleep(0)
            later_task = asyncio.create_task(runtime.handle_tool_call_with_source(later_parallel, dispatch))
            await asyncio.sleep(0)
            self.assertFalse(exclusive_entered.is_set())
            self.assertFalse(later_parallel_entered.is_set())
            release_first_parallel.set()
            await exclusive_entered.wait()
            self.assertFalse(later_parallel_entered.is_set())
            release_exclusive.set()
            results = await asyncio.gather(first_task, exclusive_task, later_task)
            return results

        first_result, exclusive_result, later_result = asyncio.run(scenario())

        self.assertEqual(first_result.to_response_item().output.to_text(), "call-parallel-1")
        self.assertEqual(exclusive_result.to_response_item().output.to_text(), "call-exclusive")
        self.assertEqual(later_result.to_response_item().output.to_text(), "call-parallel-2")

    def test_cancellation_aborts_tool_waiting_for_execution_gate(self) -> None:
        recorder = Recorder()
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("parallel_tool", supports_parallel=True),
                RegisteredTool.plain("exclusive_tool", supports_parallel=False),
            ]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry), lifecycle_contributors=[recorder])
        parallel_call = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel",
            payload=ToolPayload.function("{}"),
        )
        exclusive_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive",
            payload=ToolPayload.function("{}"),
        )
        token = CancellationToken()

        async def scenario():
            parallel_started = asyncio.Event()
            exclusive_entered = asyncio.Event()
            release_parallel = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                if received_call.call_id == "call-parallel":
                    parallel_started.set()
                    await release_parallel.wait()
                else:
                    exclusive_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            parallel_task = asyncio.create_task(runtime.handle_tool_call_with_source(parallel_call, dispatch))
            await parallel_started.wait()
            exclusive_task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    exclusive_call,
                    dispatch,
                    cancellation_token=token,
                    elapsed_seconds=0.01,
                    turn_id="turn-1",
                )
            )
            await asyncio.sleep(0)
            token.cancel()
            result = await exclusive_task
            self.assertFalse(exclusive_entered.is_set())
            release_parallel.set()
            await parallel_task
            return result

        result = asyncio.run(scenario())

        self.assertEqual(result.to_response_item().output.to_text(), "aborted by user after 0.1s")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.call_ids, ["call-exclusive"])

    def test_cancelled_exclusive_waiter_wakes_later_parallel_dispatch(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("parallel_tool", supports_parallel=True),
                RegisteredTool.plain("exclusive_tool", supports_parallel=False),
            ]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        first_parallel = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-1",
            payload=ToolPayload.function("{}"),
        )
        exclusive_call = ToolCall(
            tool_name=ToolName.plain("exclusive_tool"),
            call_id="call-exclusive",
            payload=ToolPayload.function("{}"),
        )
        later_parallel = ToolCall(
            tool_name=ToolName.plain("parallel_tool"),
            call_id="call-parallel-2",
            payload=ToolPayload.function("{}"),
        )
        token = CancellationToken()

        async def scenario():
            first_parallel_started = asyncio.Event()
            release_first_parallel = asyncio.Event()
            exclusive_entered = asyncio.Event()
            later_parallel_entered = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                if received_call.call_id == "call-parallel-1":
                    first_parallel_started.set()
                    await release_first_parallel.wait()
                elif received_call.call_id == "call-exclusive":
                    exclusive_entered.set()
                else:
                    later_parallel_entered.set()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text(received_call.call_id, True),
                )

            first_task = asyncio.create_task(runtime.handle_tool_call_with_source(first_parallel, dispatch))
            await first_parallel_started.wait()
            exclusive_task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    exclusive_call,
                    dispatch,
                    cancellation_token=token,
                    elapsed_seconds=0.01,
                )
            )
            await asyncio.sleep(0)
            later_task = asyncio.create_task(runtime.handle_tool_call_with_source(later_parallel, dispatch))
            await asyncio.sleep(0)
            self.assertFalse(exclusive_entered.is_set())
            self.assertFalse(later_parallel_entered.is_set())
            token.cancel()
            aborted_result = await exclusive_task
            release_first_parallel.set()
            later_result = await later_task
            await first_task
            return aborted_result, later_result

        aborted_result, later_result = asyncio.run(scenario())

        self.assertEqual(aborted_result.to_response_item().output.to_text(), "aborted by user after 0.1s")
        self.assertEqual(later_result.to_response_item().output.to_text(), "call-parallel-2")

    def test_inflight_cancellation_aborts_non_waiting_tool(self) -> None:
        recorder = Recorder()
        runtime = ToolCallRuntime(ToolRouter.from_parts(()), lifecycle_contributors=[recorder])
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await asyncio.sleep(10)

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )
            await started.wait()
            token.cancel()
            return await task

        result = asyncio.run(scenario())

        self.assertIn("aborted by user", result.to_response_item().output.to_text())
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.tool_names, [ToolName.plain("view_image")])
        self.assertEqual(recorder.turn_ids, ["turn-1"])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])
        self.assertEqual(
            recorder.sources,
            [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")],
        )

    def test_inflight_cancellation_defaults_lifecycle_source_to_direct(self) -> None:
        recorder = Recorder()
        runtime = ToolCallRuntime(ToolRouter.from_parts(()), lifecycle_contributors=[recorder])
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await asyncio.sleep(10)

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(call, dispatch, cancellation_token=token, turn_id="turn-1")
            )
            await started.wait()
            token.cancel()
            return await task

        result = asyncio.run(scenario())

        self.assertIn("aborted by user", result.to_response_item().output.to_text())
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.direct()])

    def test_inflight_cancellation_clamps_abort_elapsed_seconds(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await asyncio.sleep(10)

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    elapsed_seconds=0.01,
                )
            )
            await started.wait()
            token.cancel()
            return await task

        result = asyncio.run(scenario())

        self.assertEqual(result.to_response_item().output.to_text(), "aborted by user after 0.1s")

    def test_inflight_cancellation_uses_runtime_measured_elapsed_seconds(self) -> None:
        runtime = ToolCallRuntime(ToolRouter.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await asyncio.sleep(10)

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(call, dispatch, cancellation_token=token)
            )
            await started.wait()
            token.cancel()
            return await task

        monotonic_values = iter([10.0, 11.234])
        original_monotonic = tool_parallel_module._monotonic
        try:
            tool_parallel_module._monotonic = lambda: next(monotonic_values)
            result = asyncio.run(scenario())
        finally:
            tool_parallel_module._monotonic = original_monotonic

        self.assertEqual(result.to_response_item().output.to_text(), "aborted by user after 1.2s")

    def test_inflight_cancellation_waits_for_runtime_cleanup_then_aborts(self) -> None:
        recorder = Recorder()
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("view_image", waits_for_cancellation=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry), lifecycle_contributors=[recorder])
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()
            cleanup_started = asyncio.Event()
            allow_cleanup = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await received_token.cancelled()
                cleanup_started.set()
                await allow_cleanup.wait()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text("cleanup complete", True),
                )

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )
            await started.wait()
            token.cancel()
            await cleanup_started.wait()
            allow_cleanup.set()
            return await task

        result = asyncio.run(scenario())

        self.assertIn("aborted by user", result.to_response_item().output.to_text())
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.tool_names, [ToolName.plain("view_image")])
        self.assertEqual(recorder.turn_ids, ["turn-1"])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])
        self.assertEqual(
            recorder.sources,
            [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")],
        )

    def test_waiting_runtime_cancellation_defaults_lifecycle_source_to_direct(self) -> None:
        recorder = Recorder()
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("view_image", waits_for_cancellation=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry), lifecycle_contributors=[recorder])
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()
            cleanup_started = asyncio.Event()
            allow_cleanup = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await received_token.cancelled()
                cleanup_started.set()
                await allow_cleanup.wait()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text("cleanup complete", True),
                )

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(call, dispatch, cancellation_token=token, turn_id="turn-1")
            )
            await started.wait()
            token.cancel()
            await cleanup_started.wait()
            allow_cleanup.set()
            return await task

        result = asyncio.run(scenario())

        self.assertIn("aborted by user", result.to_response_item().output.to_text())
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.direct()])

    def test_waiting_runtime_cancellation_ignores_cleanup_tool_error_after_abort_claim(self) -> None:
        recorder = Recorder()
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("view_image", waits_for_cancellation=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry), lifecycle_contributors=[recorder])
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()
            cleanup_started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await received_token.cancelled()
                cleanup_started.set()
                raise FunctionCallError.respond_to_model("cleanup failed")

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    elapsed_seconds=0.01,
                    turn_id="turn-1",
                )
            )
            await started.wait()
            token.cancel()
            await cleanup_started.wait()
            return await task

        result = asyncio.run(scenario())

        self.assertEqual(result.to_response_item().output.to_text(), "aborted by user after 0.1s")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.aborted()])
        self.assertEqual(recorder.call_ids, ["call-1"])

    def test_waiting_runtime_cancellation_propagates_cleanup_runtime_error(self) -> None:
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("view_image", waits_for_cancellation=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            started = asyncio.Event()
            cleanup_started = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                started.set()
                await received_token.cancelled()
                cleanup_started.set()
                raise RuntimeError("cleanup exploded")

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    elapsed_seconds=0.01,
                    turn_id="turn-1",
                )
            )
            await started.wait()
            token.cancel()
            await cleanup_started.wait()
            return await task

        with self.assertRaisesRegex(RuntimeError, "cleanup exploded"):
            asyncio.run(scenario())

    def test_cancellation_after_router_dispatch_finishes_preserves_completed_lifecycle(self) -> None:
        recorder = Recorder()
        finish_started = asyncio.Event()
        allow_finish = asyncio.Event()

        class BlockingFinishContributor:
            async def on_tool_finish(self, input):
                finish_started.set()
                await allow_finish.wait()
                await recorder.on_tool_finish(input)

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                from pycodex.core.tool_lifecycle import ToolCallOutcome, notify_tool_finish

                await notify_tool_finish(
                    [BlockingFinishContributor()],
                    ToolInvocation(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        payload=call.payload,
                        source=kwargs.get("source", ToolCallSource.direct()),
                    ),
                    ToolCallOutcome.completed(True),
                    turn_id=kwargs.get("turn_id", ""),
                )
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            task = asyncio.create_task(
                runtime.handle_tool_call(
                    call,
                    cancellation_token=token,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )
            await finish_started.wait()
            token.cancel()
            allow_finish.set()
            return await task

        response = asyncio.run(scenario())

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.tool_names, [ToolName.plain("view_image")])
        self.assertEqual(recorder.turn_ids, ["turn-1"])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])
        self.assertEqual(
            recorder.sources,
            [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")],
        )

    def test_completed_after_cancellation_defaults_lifecycle_source_to_direct(self) -> None:
        recorder = Recorder()
        finish_started = asyncio.Event()
        allow_finish = asyncio.Event()

        class BlockingFinishContributor:
            async def on_tool_finish(self, input):
                finish_started.set()
                await allow_finish.wait()
                await recorder.on_tool_finish(input)

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                from pycodex.core.tool_lifecycle import ToolCallOutcome, notify_tool_finish

                await notify_tool_finish(
                    [BlockingFinishContributor()],
                    ToolInvocation(
                        call_id=call.call_id,
                        tool_name=call.tool_name,
                        payload=call.payload,
                        source=kwargs.get("source", ToolCallSource.direct()),
                    ),
                    ToolCallOutcome.completed(True),
                    turn_id=kwargs.get("turn_id", ""),
                )
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            task = asyncio.create_task(
                runtime.handle_tool_call(
                    call,
                    cancellation_token=token,
                    turn_id="turn-1",
                )
            )
            await finish_started.wait()
            token.cancel()
            allow_finish.set()
            return await task

        response = asyncio.run(scenario())

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.direct()])

    def test_cancellation_after_terminal_outcome_reached_preserves_completed_result(self) -> None:
        terminal_reached = asyncio.Event()
        allow_finish = asyncio.Event()

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                terminal_outcome_reached = kwargs["terminal_outcome_reached"]
                terminal_outcome_reached.swap(True)
                terminal_reached.set()
                await allow_finish.wait()
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            task = asyncio.create_task(runtime.handle_tool_call(call, cancellation_token=token))
            await terminal_reached.wait()
            token.cancel()
            await asyncio.sleep(0)
            allow_finish.set()
            return await task

        response = asyncio.run(scenario())

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "ok")

    def test_waiting_runtime_cancellation_preserves_reached_terminal_outcome(self) -> None:
        recorder = Recorder()
        registry = ToolRegistry.from_tools(
            [RegisteredTool.plain("view_image", waits_for_cancellation=True)]
        )
        runtime = ToolCallRuntime(ToolRouter.from_parts(registry), lifecycle_contributors=[recorder])
        token = CancellationToken()
        terminal_outcome_reached = TerminalOutcomeFlag()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        async def scenario():
            terminal_reached = asyncio.Event()
            allow_finish = asyncio.Event()

            async def dispatch(received_call, source, received_token):
                terminal_outcome_reached.swap(True)
                terminal_reached.set()
                await allow_finish.wait()
                return ToolCallResult(
                    call_id=received_call.call_id,
                    payload=received_call.payload,
                    result=FunctionToolOutput.from_text("ok", True),
                )

            task = asyncio.create_task(
                runtime.handle_tool_call_with_source(
                    call,
                    dispatch,
                    cancellation_token=token,
                    terminal_outcome_reached=terminal_outcome_reached,
                    turn_id="turn-1",
                )
            )
            await terminal_reached.wait()
            token.cancel()
            await asyncio.sleep(0)
            allow_finish.set()
            return await task

        result = asyncio.run(scenario())

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(recorder.outcomes, [])

    def test_handle_tool_call_wraps_router_dispatch_output(self) -> None:
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["source"] = kwargs.get("source")
                observed["cancellation_token"] = kwargs.get("cancellation_token")
                observed["session_store"] = kwargs.get("session_store")
                observed["thread_store"] = kwargs.get("thread_store")
                observed["turn_store"] = kwargs.get("turn_store")
                observed["turn_id"] = kwargs.get("turn_id")
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                cancellation_token=token,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "call-1")
        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(observed["source"], ToolCallSource.code_mode("cell-1", "runtime-tool-1"))
        self.assertIs(observed["cancellation_token"], token)
        self.assertEqual(observed["session_store"], {"session": True})
        self.assertEqual(observed["thread_store"], {"thread": True})
        self.assertEqual(observed["turn_store"], {"turn": True})
        self.assertEqual(observed["turn_id"], "turn-1")

    def test_handle_tool_call_defaults_router_dispatch_to_direct_source(self) -> None:
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["source"] = kwargs.get("source")
                observed["cancellation_token"] = kwargs.get("cancellation_token")
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(runtime.handle_tool_call(call))

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.call_id, "call-1")
        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(observed["source"], ToolCallSource.direct())
        self.assertIsInstance(observed["cancellation_token"], CancellationToken)

    def test_handle_tool_call_passes_runtime_lifecycle_contributors_to_router(self) -> None:
        recorder = Recorder()
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["lifecycle_contributors"] = kwargs.get("lifecycle_contributors")
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()), lifecycle_contributors=[recorder])
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(runtime.handle_tool_call(call))

        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(observed["lifecycle_contributors"], [recorder])

    def test_handle_tool_call_runtime_lifecycle_contributors_override_store_key(self) -> None:
        recorder = Recorder()
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["lifecycle_contributors"] = kwargs.get("lifecycle_contributors")
                return FunctionToolOutput.from_text("ok", True)

        runtime = ToolCallRuntime(Router.from_parts(()), lifecycle_contributors=[recorder])
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                lifecycle_contributors=["store-value"],
            )
        )

        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(observed["lifecycle_contributors"], [recorder])

    def test_handle_tool_call_runtime_lifecycle_contributors_receive_registered_tool_events(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "ok")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.starts[0].source, ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1"))
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_runtime_lifecycle_contributors_receive_registered_tool_failure_events(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                raise FunctionCallError.respond_to_model("boom")

            def matches_kind(self, payload):
                return payload.type == "function"

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "boom")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_runtime_lifecycle_contributors_receive_registered_tool_fatal_events(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                raise ValueError("bad tool")

            def matches_kind(self, payload):
                return payload.type == "function"

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "bad tool"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_runtime_lifecycle_contributors_receive_registered_tool_blocked_events(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return PreToolUseHookResult.blocked("blocked by policy")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(handler_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "blocked by policy")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.blocked()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_pre_hook_blocked_emits_blocked_lifecycle(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            return PreToolUseHookResult.blocked("async blocked by policy")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(handler_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "async blocked by policy")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.blocked()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_pre_hook_blocked_emits_blocked_lifecycle(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "blocked", "message": "mapping blocked by policy"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(handler_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "mapping blocked by policy")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.blocked()])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_pre_hook_invalid_blocked_message_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "blocked", "message": 7}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "blocked result requires message"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_pre_hook_continue_without_rewrite_preserves_input_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        received_arguments = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                received_arguments.append(invocation.payload.arguments)
                return FunctionToolOutput.from_text("ok without rewrite", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return PreToolUseHookResult.continue_()

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function('{"path":"original.txt"}'),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(response.output.to_text(), "ok without rewrite")
        self.assertEqual(received_arguments, ['{"path":"original.txt"}'])
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_pre_hook_continue_without_rewrite_preserves_input_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        received_arguments = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                received_arguments.append(invocation.payload.arguments)
                return FunctionToolOutput.from_text("ok mapping without rewrite", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "continue"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function('{"path":"original.txt"}'),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(response.output.to_text(), "ok mapping without rewrite")
        self.assertEqual(received_arguments, ['{"path":"original.txt"}'])
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_pre_hook_continue_rewrites_input_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        received_arguments = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                received_arguments.append(invocation.payload.arguments)
                return FunctionToolOutput.from_text("ok after async rewrite", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            return PreToolUseHookResult.continue_({"path": "async-rewritten.txt"})

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function('{"path":"original.txt"}'),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(response.output.to_text(), "ok after async rewrite")
        self.assertEqual(received_arguments, ['{"path":"async-rewritten.txt"}'])
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_pre_hook_continue_rewrites_input_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        received_arguments = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                received_arguments.append(invocation.payload.arguments)
                return FunctionToolOutput.from_text("ok after rewrite", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "continue", "updated_input": {"path": "rewritten.txt"}}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function('{"path":"original.txt"}'),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(response.output.to_text(), "ok after rewrite")
        self.assertEqual(received_arguments, ['{"path":"rewritten.txt"}'])
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_runtime_lifecycle_contributors_receive_pre_hook_rewrite_failure_events(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return PreToolUseHookResult.continue_({"bad": object()})

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "failed to serialize rewritten view_image arguments"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_pre_hook_rewrite_failure_emits_failed_lifecycle(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "continue", "updated_input": {"bad": object()}}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "failed to serialize rewritten view_image arguments"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_invalid_pre_hook_result_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            return {"type": "unexpected"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "pre_tool_use_hook must return PreToolUseHookResult"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_invalid_pre_hook_result_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            return object()

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "pre_tool_use_hook must return PreToolUseHookResult"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_pre_hook_runtime_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            raise ValueError("pre hook exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "pre hook exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_pre_hook_runtime_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            raise ValueError("async pre hook exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async pre hook exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_pre_hook_model_visible_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            raise FunctionCallError.respond_to_model("pre hook visible failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(handler_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "pre hook visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_pre_hook_model_visible_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            raise FunctionCallError.respond_to_model("async pre hook visible failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                pre_tool_use_hook=pre_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(handler_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "async pre hook visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_pre_hook_fatal_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def pre_tool_use_hook(payload, invocation):
            raise FunctionCallError.fatal("pre hook fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "pre hook fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_pre_hook_fatal_error_emits_failed_lifecycle_before_handler(self) -> None:
        recorder = Recorder()
        handler_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                nonlocal handler_called
                handler_called = True
                return FunctionToolOutput.from_text("ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def pre_tool_use_hook(payload, invocation):
            await asyncio.sleep(0)
            raise FunctionCallError.fatal("async pre hook fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async pre hook fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    pre_tool_use_hook=pre_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertFalse(handler_called)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_skips_post_hook_for_failed_registered_tool_output(self) -> None:
        recorder = Recorder()
        post_hook_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler failed", False)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            nonlocal post_hook_called
            post_hook_called = True
            raise AssertionError("failed tool output should not run post hook")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(post_hook_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "handler failed")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(False)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_skips_post_hook_when_successful_tool_returns_no_post_payload(self) -> None:
        recorder = Recorder()
        post_hook_called = False

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

            def post_tool_use_payload(self, invocation, result):
                return None

        def post_tool_use_hook(payload, result):
            nonlocal post_hook_called
            post_hook_called = True
            raise AssertionError("tools without post payload should not run post hook")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertFalse(post_hook_called)
        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(response.output.to_text(), "handler ok")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_invalid_post_tool_use_payload_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

            def post_tool_use_payload(self, invocation, result):
                return {"tool_name": "bad"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post_tool_use_payload must return PostToolUsePayload or None"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_tool_use_payload_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

            def post_tool_use_payload(self, invocation, result):
                raise ValueError("post payload exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post payload exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_tool_use_payload_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

            def post_tool_use_payload(self, invocation, result):
                raise FunctionCallError.respond_to_model("post payload visible failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "post payload visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_tool_use_payload_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("handler ok", True)

            def matches_kind(self, payload):
                return payload.type == "function"

            def post_tool_use_payload(self, invocation, result):
                raise FunctionCallError.fatal("post payload fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post payload fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_feedback_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(feedback_message="hook replacement")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_post_hook_feedback_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def post_tool_use_hook(payload, result):
            await asyncio.sleep(0)
            return PostToolUseHookOutcome(feedback_message="async hook replacement")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "async hook replacement")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_feedback_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"feedback_message": "mapping hook replacement"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "mapping hook replacement")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_noop_keeps_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome()

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "original output")
        self.assertEqual(response.output.success, True)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_invalid_post_hook_outcome_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return object()

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post_tool_use_hook must return PostToolUseHookOutcome"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_invalid_post_hook_outcome_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def post_tool_use_hook(payload, result):
            await asyncio.sleep(0)
            return object()

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post_tool_use_hook must return PostToolUseHookOutcome"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            raise FunctionCallError.respond_to_model("post hook failed")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "post hook failed")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_post_hook_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def post_tool_use_hook(payload, result):
            await asyncio.sleep(0)
            raise FunctionCallError.respond_to_model("async post hook failed")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "async post hook failed")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            raise FunctionCallError.fatal("post hook fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post hook fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_post_hook_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def post_tool_use_hook(payload, result):
            await asyncio.sleep(0)
            raise FunctionCallError.fatal("async post hook fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async post hook fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            raise ValueError("post hook exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "post hook exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_async_post_hook_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        async def post_tool_use_hook(payload, result):
            await asyncio.sleep(0)
            raise ValueError("async post hook exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async post hook exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_additional_context_recorder_failure_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before recorder failure",),
            )

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "additional_context_recorder must be callable"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder="not callable",
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before runtime recorder failure",),
            )

        def additional_context_recorder(messages):
            raise ValueError("recorder exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=additional_context_recorder,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_async_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before async runtime recorder failure",),
            )

        async def additional_context_recorder(messages):
            raise ValueError("async recorder exploded")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=additional_context_recorder,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before visible recorder failure",),
            )

        def additional_context_recorder(messages):
            raise FunctionCallError.respond_to_model("recorder visible failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                additional_context_recorder=additional_context_recorder,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_async_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before async visible recorder failure",),
            )

        async def additional_context_recorder(messages):
            raise FunctionCallError.respond_to_model("async recorder visible failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                additional_context_recorder=additional_context_recorder,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "async recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before fatal recorder failure",),
            )

        def additional_context_recorder(messages):
            raise FunctionCallError.fatal("recorder fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=additional_context_recorder,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_async_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context before async fatal recorder failure",),
            )

        async def additional_context_recorder(messages):
            raise FunctionCallError.fatal("async recorder fatal failure")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "async recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=additional_context_recorder,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_stop_reason_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"should_stop": True, "stop_reason": "mapping stop reason"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "mapping stop reason")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_stop_default_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"should_stop": True}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "PostToolUse hook stopped execution")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_invalid_should_stop_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"should_stop": "false", "feedback_message": "hook replacement"}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "should_stop must be a bool"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_invalid_feedback_message_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"feedback_message": 7}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "feedback_message must be a string or None"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_invalid_stop_reason_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {"should_stop": True, "stop_reason": 7}

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "stop_reason must be a string or None"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_stop_feedback_takes_precedence_over_stop_reason(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {
                "should_stop": True,
                "feedback_message": "mapping feedback wins",
                "stop_reason": "mapping stop reason loses",
            }

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "mapping feedback wins")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_stop_default_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(should_stop=True)

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "PostToolUse hook stopped execution")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_stop_reason_replaces_registered_tool_output_and_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(should_stop=True, stop_reason="stop because policy")

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "stop because policy")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_stop_feedback_takes_precedence_over_stop_reason(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                should_stop=True,
                feedback_message="feedback wins",
                stop_reason="stop reason loses",
            )

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "feedback wins")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_records_additional_contexts_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        additional_context_batches = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {
                "feedback_message": "mapping hook replacement",
                "additional_contexts": ("mapping outcome context",),
            }

        async def additional_context_recorder(messages):
            additional_context_batches.append(messages)

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                additional_context_recorder=additional_context_recorder,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.to_text(), "mapping hook replacement")
        self.assertEqual(response.output.success, None)
        self.assertEqual(len(additional_context_batches), 1)
        self.assertEqual(len(additional_context_batches[0]), 1)
        self.assertEqual(additional_context_batches[0][0].role, "developer")
        self.assertIn("mapping outcome context", additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_records_additional_contexts_and_completes_lifecycle(self) -> None:
        recorder = Recorder()
        additional_context_batches = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("extra developer context",),
            )

        async def additional_context_recorder(messages):
            additional_context_batches.append(messages)

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                additional_context_recorder=additional_context_recorder,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(additional_context_batches), 1)
        self.assertEqual(len(additional_context_batches[0]), 1)
        self.assertEqual(additional_context_batches[0][0].role, "developer")
        self.assertIn("extra developer context", additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_additional_contexts_without_recorder_still_completes_lifecycle(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("context without recorder",),
            )

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertIsNone(response.output.success)
        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_invalid_additional_contexts_emit_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("valid context", 7),
            )

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "additional_contexts must contain only strings"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=lambda messages: None,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_string_additional_contexts_emit_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts="not a context sequence",
            )

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "additional_contexts must be a tuple or list of strings"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=lambda messages: None,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_string_additional_contexts_emit_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {
                "feedback_message": "hook replacement",
                "additional_contexts": "not a context sequence",
            }

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "additional_contexts must be a tuple or list of strings"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=lambda messages: None,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_mapping_post_hook_invalid_additional_contexts_emit_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return {
                "feedback_message": "hook replacement",
                "additional_contexts": ["valid context", 7],
            }

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "additional_contexts must contain only strings"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    additional_context_recorder=lambda messages: None,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_records_additional_contexts_with_sync_recorder(self) -> None:
        recorder = Recorder()
        additional_context_batches = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("sync recorder context",),
            )

        def additional_context_recorder(messages):
            additional_context_batches.append(messages)

        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                additional_context_recorder=additional_context_recorder,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertIsNone(response.output.success)
        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(additional_context_batches), 1)
        self.assertEqual(len(additional_context_batches[0]), 1)
        self.assertEqual(additional_context_batches[0][0].role, "developer")
        self.assertIn("sync recorder context", additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_session_fallback(self) -> None:
        recorder = Recorder()

        class Session:
            def __init__(self):
                self.additional_context_batches = []

            async def record_additional_contexts(self, messages):
                self.additional_context_batches.append(messages)

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session fallback context",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(session.additional_context_batches), 1)
        self.assertEqual(len(session.additional_context_batches[0]), 1)
        self.assertEqual(session.additional_context_batches[0][0].role, "developer")
        self.assertIn("session fallback context", session.additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_session_fallback_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_contexts(self, messages):
                raise ValueError("session recorder exploded")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session fallback context before failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_fallback_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_contexts(self, messages):
                raise FunctionCallError.respond_to_model("session recorder visible failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session fallback context before visible failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "session recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_fallback_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_contexts(self, messages):
                raise FunctionCallError.fatal("session recorder fatal failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session fallback context before fatal failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_session_messages_alias(self) -> None:
        recorder = Recorder()

        class Session:
            def __init__(self):
                self.additional_context_batches = []

            async def record_additional_context_messages(self, messages):
                self.additional_context_batches.append(messages)

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session messages alias context",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(session.additional_context_batches), 1)
        self.assertEqual(len(session.additional_context_batches[0]), 1)
        self.assertEqual(session.additional_context_batches[0][0].role, "developer")
        self.assertIn("session messages alias context", session.additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_session_add_alias(self) -> None:
        recorder = Recorder()

        class Session:
            def __init__(self):
                self.additional_context_batches = []

            async def add_additional_context_messages(self, messages):
                self.additional_context_batches.append(messages)

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session add alias context",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(session.additional_context_batches), 1)
        self.assertEqual(len(session.additional_context_batches[0]), 1)
        self.assertEqual(session.additional_context_batches[0][0].role, "developer")
        self.assertIn("session add alias context", session.additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_session_messages_alias_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_context_messages(self, messages):
                raise ValueError("session messages alias recorder exploded")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session messages alias context before failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session messages alias recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_messages_alias_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_context_messages(self, messages):
                raise FunctionCallError.respond_to_model("session messages alias recorder visible failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session messages alias context before visible failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "session messages alias recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_messages_alias_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def record_additional_context_messages(self, messages):
                raise FunctionCallError.fatal("session messages alias recorder fatal failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session messages alias context before fatal failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session messages alias recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_add_alias_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def add_additional_context_messages(self, messages):
                raise ValueError("session add alias recorder exploded")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session add alias context before failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session add alias recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_add_alias_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def add_additional_context_messages(self, messages):
                raise FunctionCallError.respond_to_model("session add alias recorder visible failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session add alias context before visible failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "session add alias recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_session_add_alias_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Session:
            async def add_additional_context_messages(self, messages):
                raise FunctionCallError.fatal("session add alias recorder fatal failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("session add alias context before fatal failure",),
            )

        session = Session()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "session add alias recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_turn_fallback(self) -> None:
        recorder = Recorder()

        class Turn:
            def __init__(self):
                self.additional_context_batches = []

            async def record_additional_contexts(self, messages):
                self.additional_context_batches.append(messages)

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("turn fallback context",),
            )

        turn = Turn()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                turn=turn,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(turn.additional_context_batches), 1)
        self.assertEqual(len(turn.additional_context_batches[0]), 1)
        self.assertEqual(turn.additional_context_batches[0][0].role, "developer")
        self.assertIn("turn fallback context", turn.additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_turn_fallback_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Turn:
            async def record_additional_contexts(self, messages):
                raise ValueError("turn recorder exploded")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("turn fallback context before failure",),
            )

        turn = Turn()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "turn recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    turn=turn,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_turn_fallback_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Turn:
            async def record_additional_contexts(self, messages):
                raise FunctionCallError.respond_to_model("turn recorder visible failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("turn fallback context before visible failure",),
            )

        turn = Turn()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                turn=turn,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "turn recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_turn_fallback_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Turn:
            async def record_additional_contexts(self, messages):
                raise FunctionCallError.fatal("turn recorder fatal failure")

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("turn fallback context before fatal failure",),
            )

        turn = Turn()
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "turn recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    turn=turn,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_mapping_session_fallback(self) -> None:
        recorder = Recorder()
        additional_context_batches = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping session context",),
            )

        async def record_additional_contexts(messages):
            additional_context_batches.append(messages)

        session = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(additional_context_batches), 1)
        self.assertEqual(len(additional_context_batches[0]), 1)
        self.assertEqual(additional_context_batches[0][0].role, "developer")
        self.assertIn("mapping session context", additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_mapping_session_fallback_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping session context before failure",),
            )

        async def record_additional_contexts(messages):
            raise ValueError("mapping session recorder exploded")

        session = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "mapping session recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_mapping_session_fallback_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping session context before visible failure",),
            )

        async def record_additional_contexts(messages):
            raise FunctionCallError.respond_to_model("mapping session recorder visible failure")

        session = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                session=session,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "mapping session recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_mapping_session_fallback_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping session context before fatal failure",),
            )

        async def record_additional_contexts(messages):
            raise FunctionCallError.fatal("mapping session recorder fatal failure")

        session = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "mapping session recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    session=session,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_records_additional_contexts_through_mapping_turn_fallback(self) -> None:
        recorder = Recorder()
        additional_context_batches = []

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping turn context",),
            )

        async def record_additional_contexts(messages):
            additional_context_batches.append(messages)

        turn = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                turn=turn,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.output.to_text(), "hook replacement")
        self.assertEqual(len(additional_context_batches), 1)
        self.assertEqual(len(additional_context_batches[0]), 1)
        self.assertEqual(additional_context_batches[0][0].role, "developer")
        self.assertIn("mapping turn context", additional_context_batches[0][0].content[0].text)
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.completed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])

    def test_handle_tool_call_post_hook_mapping_turn_fallback_additional_context_recorder_runtime_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping turn context before failure",),
            )

        async def record_additional_contexts(messages):
            raise ValueError("mapping turn recorder exploded")

        turn = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "mapping turn recorder exploded"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    turn=turn,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_mapping_turn_fallback_additional_context_recorder_model_visible_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping turn context before visible failure",),
            )

        async def record_additional_contexts(messages):
            raise FunctionCallError.respond_to_model("mapping turn recorder visible failure")

        turn = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                post_tool_use_hook=post_tool_use_hook,
                turn=turn,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertEqual(response.output.success, False)
        self.assertEqual(response.output.to_text(), "mapping turn recorder visible failure")
        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_post_hook_mapping_turn_fallback_additional_context_recorder_fatal_error_emits_failed_lifecycle_after_handler(self) -> None:
        recorder = Recorder()

        class Tool:
            def tool_name(self):
                return ToolName.plain("view_image")

            async def handle(self, invocation):
                return FunctionToolOutput.from_text("original output", True)

            def matches_kind(self, payload):
                return payload.type == "function"

        def post_tool_use_hook(payload, result):
            return PostToolUseHookOutcome(
                feedback_message="hook replacement",
                additional_contexts=("mapping turn context before fatal failure",),
            )

        async def record_additional_contexts(messages):
            raise FunctionCallError.fatal("mapping turn recorder fatal failure")

        turn = {"record_additional_contexts": record_additional_contexts}
        registry = ToolRegistry.from_tools([Tool()])
        runtime = ToolCallRuntime(
            ToolRouter.from_parts(registry, ()),
            lifecycle_contributors=[recorder],
        )
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "mapping turn recorder fatal failure"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    post_tool_use_hook=post_tool_use_hook,
                    turn=turn,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )

        self.assertEqual(len(recorder.starts), 1)
        self.assertEqual(recorder.starts[0].call_id, "call-1")
        self.assertEqual(recorder.outcomes, [ToolCallOutcome.failed(True)])
        self.assertEqual(recorder.call_ids, ["call-1"])
        self.assertEqual(recorder.sources, [ExtensionToolCallSource.code_mode("cell-1", "runtime-tool-1")])
        self.assertEqual(recorder.session_stores, [{"session": True}])
        self.assertEqual(recorder.thread_stores, [{"thread": True}])
        self.assertEqual(recorder.turn_stores, [{"turn": True}])

    def test_handle_tool_call_preserves_router_into_response_item(self) -> None:
        expected = FunctionToolOutput.from_text("direct response", True).to_response_item(
            "call-router",
            ToolPayload.function("{}"),
        )

        class RouterResult:
            def into_response(self):
                return expected

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                return RouterResult()

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(runtime.handle_tool_call(call))

        self.assertIs(response, expected)

    def test_handle_tool_call_rejects_invalid_router_into_response_item(self) -> None:
        class RouterResult:
            def into_response(self):
                return {"type": "function_call_output"}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                return RouterResult()

        runtime = ToolCallRuntime(Router.from_parts(()))
        call = ToolCall(
            tool_name=ToolName.plain("view_image"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(TypeError, "router dispatch must return ToolCallResult or tool output"):
            asyncio.run(runtime.handle_tool_call(call))

    def test_handle_tool_call_turns_model_visible_error_into_failure_response(self) -> None:
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["source"] = kwargs.get("source")
                observed["cancellation_token"] = kwargs.get("cancellation_token")
                observed["session_store"] = kwargs.get("session_store")
                observed["thread_store"] = kwargs.get("thread_store")
                observed["turn_store"] = kwargs.get("turn_store")
                observed["turn_id"] = kwargs.get("turn_id")
                raise FunctionCallError.respond_to_model("no such tool")

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("missing"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        response = asyncio.run(
            runtime.handle_tool_call(
                call,
                cancellation_token=token,
                source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                session_store={"session": True},
                thread_store={"thread": True},
                turn_store={"turn": True},
                turn_id="turn-1",
            )
        )

        self.assertEqual(response.type, "function_call_output")
        self.assertFalse(response.output.success)
        self.assertEqual(response.output.to_text(), "no such tool")
        self.assertEqual(observed["source"], ToolCallSource.code_mode("cell-1", "runtime-tool-1"))
        self.assertIs(observed["cancellation_token"], token)
        self.assertEqual(observed["session_store"], {"session": True})
        self.assertEqual(observed["thread_store"], {"thread": True})
        self.assertEqual(observed["turn_store"], {"turn": True})
        self.assertEqual(observed["turn_id"], "turn-1")

    def test_handle_tool_call_raises_fatal_error(self) -> None:
        observed = {}

        class Router(ToolRouter):
            async def dispatch_tool_call_with_terminal_outcome(self, call, **kwargs):
                observed["source"] = kwargs.get("source")
                observed["cancellation_token"] = kwargs.get("cancellation_token")
                observed["session_store"] = kwargs.get("session_store")
                observed["thread_store"] = kwargs.get("thread_store")
                observed["turn_store"] = kwargs.get("turn_store")
                observed["turn_id"] = kwargs.get("turn_id")
                raise FunctionCallError.fatal("bad payload")

        runtime = ToolCallRuntime(Router.from_parts(()))
        token = CancellationToken()
        call = ToolCall(
            tool_name=ToolName.plain("broken"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(RuntimeError, "bad payload"):
            asyncio.run(
                runtime.handle_tool_call(
                    call,
                    cancellation_token=token,
                    source=ToolCallSource.code_mode("cell-1", "runtime-tool-1"),
                    session_store={"session": True},
                    thread_store={"thread": True},
                    turn_store={"turn": True},
                    turn_id="turn-1",
                )
            )
        self.assertEqual(observed["source"], ToolCallSource.code_mode("cell-1", "runtime-tool-1"))
        self.assertIs(observed["cancellation_token"], token)
        self.assertEqual(observed["session_store"], {"session": True})
        self.assertEqual(observed["thread_store"], {"thread": True})
        self.assertEqual(observed["turn_store"], {"turn": True})
        self.assertEqual(observed["turn_id"], "turn-1")

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

        self.assertEqual(plain.code_mode_result(), "plain")
        self.assertEqual(json_result.code_mode_result(), {"ok": True})

    def test_tool_call_result_passes_call_id_and_payload_to_output(self) -> None:
        class RecordingOutput:
            def __init__(self):
                self.calls = []

            def to_response_item(self, call_id, payload):
                self.calls.append((call_id, payload))
                return FunctionToolOutput.from_text("ok", True).to_response_item(call_id, payload)

        payload = ToolPayload.function('{"message":"hello"}')
        output = RecordingOutput()
        result = ToolCallResult(
            call_id="call-1",
            payload=payload,
            result=output,
        )

        response = result.to_response_item()

        self.assertEqual(response.call_id, "call-1")
        self.assertEqual(output.calls, [("call-1", payload)])

    def test_tool_call_result_rejects_non_response_item_output(self) -> None:
        class BadOutput:
            def to_response_item(self, call_id, payload):
                return {"call_id": call_id}

        result = ToolCallResult(
            call_id="call-1",
            payload=ToolPayload.function("{}"),
            result=BadOutput(),
        )

        with self.assertRaisesRegex(TypeError, "ResponseInputItem"):
            result.to_response_item()

    def test_tool_call_result_rejects_missing_response_output_method(self) -> None:
        result = ToolCallResult(
            call_id="call-1",
            payload=ToolPayload.function("{}"),
            result=object(),
        )

        with self.assertRaisesRegex(TypeError, "to_response_item"):
            result.to_response_item()

    def test_tool_call_result_passes_payload_to_code_mode_output(self) -> None:
        class RecordingOutput:
            def __init__(self):
                self.payloads = []

            def to_response_item(self, call_id, payload):
                return FunctionToolOutput.from_text("ok", True).to_response_item(call_id, payload)

            def code_mode_result(self, payload):
                self.payloads.append(payload)
                return {"ok": True}

        payload = ToolPayload.function('{"message":"hello"}')
        output = RecordingOutput()
        result = ToolCallResult(
            call_id="call-1",
            payload=payload,
            result=output,
        )

        self.assertEqual(result.code_mode_result(), {"ok": True})
        self.assertEqual(output.payloads, [payload])

    def test_tool_call_result_rejects_non_trait_post_hook_payload_shape(self) -> None:
        with self.assertRaises(TypeError):
            ToolCallResult(
                call_id=1,
                payload=ToolPayload.function("{}"),
                result=FunctionToolOutput.from_text("ok", True),
            )
        with self.assertRaises(TypeError):
            ToolCallResult(
                call_id="call-bad",
                payload=object(),
                result=FunctionToolOutput.from_text("ok", True),
            )
        with self.assertRaisesRegex(TypeError, "PostToolUsePayload"):
            ToolCallResult(
                call_id="call-bad",
                payload=ToolPayload.function("{}"),
                result=FunctionToolOutput.from_text("ok", True),
                post_tool_use_payload={"tool_name": "bad"},
            )


if __name__ == "__main__":
    unittest.main()
