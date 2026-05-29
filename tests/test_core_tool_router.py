import asyncio
import unittest

from pycodex.core import (
    ConversationHistory,
    FunctionCallError,
    FunctionToolOutput,
    HookToolName,
    JsonToolOutput,
    PostToolUsePayload,
    PostToolUseHookOutcome,
    PreToolUsePayload,
    PreToolUseHookResult,
    RegisteredTool,
    TerminalOutcomeFlag,
    ToolCall,
    ToolCallOutcome,
    ToolExposure,
    ToolInvocation,
    ToolPayload,
    ToolRegistry,
    ToolRouter,
    apply_post_tool_use_feedback,
    build_tool_call,
    dispatch_tool_call,
)
from pycodex.protocol import ResponseItem, SearchToolCallParams, ToolName, TruncationPolicyConfig


class EchoHandler:
    def __init__(self, name="echo"):
        self.name = ToolName.plain(name)
        self.invocations = []

    def tool_name(self):
        return self.name

    def handle(self, invocation):
        self.invocations.append(invocation)
        return FunctionToolOutput.from_text("ok", True)


class CustomOnlyHandler(EchoHandler):
    def matches_kind(self, payload):
        return payload.type == "custom"


class FailingHandler(EchoHandler):
    def handle(self, invocation):
        raise FunctionCallError.respond_to_model("failed")


class JsonEchoHandler(EchoHandler):
    def handle(self, invocation):
        self.invocations.append(invocation)
        return JsonToolOutput.new({"ok": True})


class LifecycleRecorder:
    def __init__(self):
        self.started = []
        self.finished = []

    def on_tool_start(self, input):
        self.started.append(input)

    async def on_tool_finish(self, input):
        self.finished.append(input)


class ToolRouterTests(unittest.TestCase):
    def test_build_tool_call_uses_namespace_for_registry_name(self) -> None:
        call = ToolRouter.build_tool_call(
            ResponseItem.function_call(
                name="create_event",
                namespace="mcp__codex_apps__calendar",
                arguments="{}",
                call_id="call-namespace",
            )
        )

        self.assertEqual(
            call,
            ToolCall(
                tool_name=ToolName.namespaced("mcp__codex_apps__calendar", "create_event"),
                call_id="call-namespace",
                payload=ToolPayload.function("{}"),
            ),
        )

    def test_build_tool_call_accepts_plain_function_calls(self) -> None:
        call = build_tool_call(
            ResponseItem.from_mapping(
                {
                    "type": "function_call",
                    "name": "shell_command",
                    "arguments": '{"command":"pwd"}',
                    "call_id": "call-shell",
                }
            )
        )

        self.assertEqual(call.tool_name, ToolName.plain("shell_command"))
        self.assertEqual(call.call_id, "call-shell")
        self.assertEqual(call.payload, ToolPayload.function('{"command":"pwd"}'))
        self.assertEqual(call.function_arguments(), '{"command":"pwd"}')

    def test_tool_call_function_arguments_rejects_incompatible_payloads(self) -> None:
        call = ToolCall(
            tool_name=ToolName.plain("tool_search"),
            call_id="search-1",
            payload=ToolPayload.tool_search(SearchToolCallParams("calendar")),
        )

        with self.assertRaises(FunctionCallError) as caught:
            call.function_arguments()

        self.assertEqual(caught.exception.kind, "fatal")
        self.assertEqual(
            str(caught.exception),
            "Fatal error: tool tool_search invoked with incompatible payload",
        )

    def test_tool_call_function_arguments_preserves_empty_argument_string(self) -> None:
        call = ToolCall(
            tool_name=ToolName.plain("empty_args"),
            call_id="call-empty",
            payload=ToolPayload.function(""),
        )

        self.assertEqual(call.function_arguments(), "")

    def test_function_call_error_rejects_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            FunctionCallError.respond_to_model(123)
        with self.assertRaises(TypeError):
            FunctionCallError.fatal(object())
        with self.assertRaises(ValueError):
            FunctionCallError("warning", "message")

    def test_conversation_history_coerces_response_item_mappings(self) -> None:
        history = ConversationHistory(
            (
                ResponseItem.message("user", [], id="msg-1"),
                {"type": "message", "role": "assistant", "content": [], "id": "msg-2"},
            )
        )

        self.assertEqual([item.id for item in history.items], ["msg-1", "msg-2"])

    def test_tool_call_carries_upstream_extension_context_defaults(self) -> None:
        policy = TruncationPolicyConfig.bytes(128)
        history = ConversationHistory((ResponseItem.message("user", [], id="msg-1"),))
        call = ToolCall(
            tool_name=ToolName.plain("shell_command"),
            call_id="call-shell",
            payload=ToolPayload.function("{}"),
            turn_id="turn-1",
            truncation_policy=policy,
            conversation_history=history,
        )

        self.assertEqual(call.turn_id, "turn-1")
        self.assertEqual(call.truncation_policy, policy)
        self.assertEqual(call.conversation_history, history)

    def test_tool_call_rejects_non_rust_field_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ToolCall(
                tool_name="shell_command",
                call_id="call-shell",
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolCall(
                tool_name=ToolName.plain("shell_command"),
                call_id=1,
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            ToolCall(
                tool_name=ToolName.plain("shell_command"),
                call_id="call-shell",
                payload=ToolPayload.function("{}"),
                conversation_history=object(),
            )

    def test_build_tool_call_parses_client_tool_search_calls(self) -> None:
        call = build_tool_call(
            ResponseItem.tool_search_call(
                SearchToolCallParams("calendar", limit=3),
                call_id="search-1",
                execution="client",
            )
        )

        self.assertEqual(call.tool_name, ToolName.plain("tool_search"))
        self.assertEqual(call.call_id, "search-1")
        self.assertEqual(call.payload, ToolPayload.tool_search(SearchToolCallParams("calendar", 3)))

    def test_build_tool_call_ignores_server_or_missing_id_tool_search_calls(self) -> None:
        self.assertIsNone(
            build_tool_call(
                ResponseItem.tool_search_call(
                    {"query": "calendar"},
                    call_id="search-server",
                    execution="server",
                )
            )
        )
        self.assertIsNone(
            build_tool_call(
                ResponseItem.tool_search_call(
                    {"query": "calendar"},
                    call_id=None,
                    execution="client",
                )
            )
        )

    def test_build_tool_call_reports_invalid_tool_search_arguments(self) -> None:
        with self.assertRaises(FunctionCallError) as caught:
            build_tool_call(
                ResponseItem.tool_search_call(
                    {"limit": 3},
                    call_id="search-bad",
                    execution="client",
                )
            )

    def test_build_tool_call_handles_custom_tool_calls(self) -> None:
        call = build_tool_call(
            ResponseItem.from_mapping(
                {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "input": "*** Begin Patch",
                    "call_id": "custom-1",
                }
            )
        )

        self.assertEqual(
            call,
            ToolCall(
                tool_name=ToolName.plain("apply_patch"),
                call_id="custom-1",
                payload=ToolPayload.custom("*** Begin Patch"),
            ),
        )

    def test_build_tool_call_ignores_non_tool_items(self) -> None:
        self.assertIsNone(
            build_tool_call(
                ResponseItem.message("assistant", [], id="msg-1")
            )
        )

        with self.assertRaises(TypeError):
            build_tool_call({"type": "message"})

    def test_router_preserves_model_visible_specs(self) -> None:
        specs = ({"type": "function", "name": "echo"},)
        self.assertEqual(ToolRouter.from_parts(specs).model_visible_specs(), specs)

        with self.assertRaises(TypeError):
            ToolRouter.from_parts("not-a-spec-list")
        with self.assertRaises(TypeError):
            ToolRouter(model_visible_specs=["not", "tuple"])
        with self.assertRaises(TypeError):
            ToolRouter.from_parts(ToolRegistry.empty(), object())

    def test_router_can_query_registry_for_parallel_support_and_exposure(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("exec_command", supports_parallel=True),
                RegisteredTool.plain(
                    "hidden_command",
                    exposure=ToolExposure.HIDDEN,
                    supports_parallel=True,
                ),
            ]
        )
        router = ToolRouter.from_parts(registry, ())

        self.assertEqual(
            router.registered_tool_names_for_test(),
            (ToolName.plain("exec_command"), ToolName.plain("hidden_command")),
        )
        self.assertEqual(
            router.tool_exposure_for_test(ToolName.plain("hidden_command")),
            ToolExposure.HIDDEN,
        )
        self.assertTrue(
            router.tool_supports_parallel(
                ToolCall(
                    tool_name=ToolName.plain("exec_command"),
                    call_id="call-parallel",
                    payload=ToolPayload.function("{}"),
                )
            )
        )
        self.assertFalse(
            router.tool_supports_parallel(
                ToolCall(
                    tool_name=ToolName.plain("hidden_command"),
                    call_id="call-hidden",
                    payload=ToolPayload.function("{}"),
                )
            )
        )
        self.assertFalse(
            router.tool_supports_parallel(
                ToolCall(
                    tool_name=ToolName.plain("missing"),
                    call_id="call-missing",
                    payload=ToolPayload.function("{}"),
                )
            )
        )
        self.assertEqual(caught.exception.kind, "respond_to_model")
        self.assertIn("failed to parse tool_search arguments", str(caught.exception))

    def test_dispatch_tool_call_wraps_handler_output_and_lifecycle(self) -> None:
        handler = EchoHandler()
        recorder = LifecycleRecorder()
        registry = ToolRegistry.from_tools([handler])
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                registry,
                invocation,
                lifecycle_contributors=[recorder],
                turn_id="turn-1",
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(handler.invocations, [invocation])
        self.assertEqual(recorder.started[0].call_id, "call-1")
        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.completed(True))

    def test_dispatch_tool_call_reports_missing_and_incompatible_tools_like_rust(self) -> None:
        missing = ToolInvocation(
            call_id="call-missing",
            tool_name=ToolName.plain("missing"),
            payload=ToolPayload.function("{}"),
        )
        incompatible = ToolInvocation(
            call_id="call-custom",
            tool_name=ToolName.plain("custom_only"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError) as caught:
            asyncio.run(dispatch_tool_call(ToolRegistry.empty(), missing))
        self.assertEqual(caught.exception.kind, "respond_to_model")
        self.assertEqual(str(caught.exception), "unsupported call: missing")

        with self.assertRaises(FunctionCallError) as caught:
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([CustomOnlyHandler("custom_only")]),
                    incompatible,
                )
            )
        self.assertEqual(caught.exception.kind, "fatal")
        self.assertEqual(
            str(caught.exception),
            "Fatal error: tool custom_only invoked with incompatible payload",
        )

    def test_dispatch_tool_call_failure_notifies_failed_executed_outcome(self) -> None:
        recorder = LifecycleRecorder()
        invocation = ToolInvocation(
            call_id="call-fail",
            tool_name=ToolName.plain("fail"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([FailingHandler("fail")]),
                    invocation,
                    lifecycle_contributors=[recorder],
                )
            )

        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.failed(True))

    def test_router_dispatch_respects_terminal_outcome_claim(self) -> None:
        recorder = LifecycleRecorder()
        flag = TerminalOutcomeFlag(True)
        router = ToolRouter.from_parts(ToolRegistry.from_tools([EchoHandler()]), ())
        call = ToolCall(
            tool_name=ToolName.plain("echo"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            router.dispatch_tool_call_with_terminal_outcome(
                call,
                lifecycle_contributors=[recorder],
                terminal_outcome_reached=flag,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(len(recorder.started), 1)
        self.assertEqual(recorder.finished, [])

    def test_apply_post_tool_use_feedback_replaces_model_visible_response_only(self) -> None:
        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([EchoHandler()]),
                ToolInvocation(
                    call_id="call-1",
                    tool_name=ToolName.plain("echo"),
                    payload=ToolPayload.function("{}"),
                ),
            )
        )

        replaced = apply_post_tool_use_feedback(result, "post hook says stop")

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(replaced.to_response_item().output.to_text(), "post hook says stop")
        self.assertTrue(replaced.result.success_for_logging())

    def test_dispatch_pre_tool_use_hook_can_block_before_handler(self) -> None:
        handler = EchoHandler()
        recorder = LifecycleRecorder()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError) as caught:
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([handler]),
                    invocation,
                    lifecycle_contributors=[recorder],
                    pre_tool_use_hook=lambda _payload, _invocation: PreToolUseHookResult.blocked("blocked"),
                )
            )

        self.assertEqual(caught.exception.kind, "respond_to_model")
        self.assertEqual(str(caught.exception), "blocked")
        self.assertEqual(handler.invocations, [])
        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.blocked())

    def test_dispatch_pre_tool_use_hook_can_rewrite_invocation_input(self) -> None:
        handler = EchoHandler()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function('{"before":true}'),
        )

        asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([handler]),
                invocation,
                pre_tool_use_hook=lambda _payload, _invocation: {
                    "type": "continue",
                    "updated_input": {"after": True},
                },
            )
        )

        self.assertEqual(handler.invocations[0].payload, ToolPayload.function('{"after":true}'))

    def test_dispatch_hooks_use_handler_specific_payload_overrides(self) -> None:
        class CustomHookPayloadHandler(EchoHandler):
            def pre_tool_use_payload(self, _invocation):
                return PreToolUsePayload(
                    tool_name=HookToolName.new("custom_pre"),
                    tool_input={"pre": True},
                )

            def post_tool_use_payload(self, _invocation, _output):
                return PostToolUsePayload(
                    tool_name=HookToolName.new("custom_post"),
                    tool_use_id="custom-call",
                    tool_input={"post": True},
                    tool_response={"ok": True},
                )

        seen = {}
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
        )

        def pre_hook(payload, _invocation):
            seen["pre"] = payload
            return PreToolUseHookResult.continue_()

        def post_hook(payload, _result):
            seen["post"] = payload
            return PostToolUseHookOutcome(should_stop=False)

        asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([CustomHookPayloadHandler()]),
                invocation,
                pre_tool_use_hook=pre_hook,
                post_tool_use_hook=post_hook,
            )
        )

        self.assertEqual(seen["pre"].tool_input, {"pre": True})
        self.assertEqual(seen["post"].tool_response, {"ok": True})

    def test_dispatch_rejects_non_trait_hook_payload_shapes(self) -> None:
        class BadPreHookPayloadHandler(EchoHandler):
            def pre_tool_use_payload(self, _invocation):
                return {"tool_name": "bad"}

        class BadPostHookPayloadHandler(EchoHandler):
            def post_tool_use_payload(self, _invocation, _output):
                return {"tool_name": "bad"}

        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaisesRegex(TypeError, "PreToolUsePayload"):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([BadPreHookPayloadHandler()]),
                    invocation,
                    pre_tool_use_hook=lambda _payload, _invocation: PreToolUseHookResult.continue_(),
                )
            )

        with self.assertRaisesRegex(TypeError, "PostToolUsePayload"):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([BadPostHookPayloadHandler()]),
                    invocation,
                    post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(should_stop=False),
                )
            )

    def test_dispatch_post_tool_use_hook_replaces_model_visible_output(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("json_echo"),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([JsonEchoHandler("json_echo")]),
                invocation,
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(
                    should_stop=True,
                    feedback_message="post hook feedback",
                ),
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "post hook feedback")
        self.assertEqual(result.code_mode_result(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
