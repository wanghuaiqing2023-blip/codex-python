import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from typing import Any
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    ConversationHistory,
    FunctionCallError,
    FunctionToolOutput,
    HookToolName,
    MEMORIES_USAGE_METRIC,
    JsonToolOutput,
    PostToolUsePayload,
    PostToolUseHookOutcome,
    PreToolUsePayload,
    PreToolUseHookResult,
    RegisteredTool,
    Shell,
    ShellType,
    TerminalOutcomeFlag,
    ExecutionStatus,
    ToolCall,
    ToolCallOutcome,
    ToolExposure,
    ToolInvocation,
    ToolPayload,
    ToolRegistry,
    ToolRouter,
    apply_post_tool_use_feedback,
    build_environment_tool_router_from_turn_context,
    build_tool_call,
    dispatch_tool_call,
    dispatch_tool_call_with_terminal_outcome,
)
from pycodex.core.tools.handlers.view_image import ViewImageHandler
from pycodex.protocol import NetworkSandboxPolicy, PermissionProfile, ResponseItem, SearchToolCallParams, ToolName, TruncationPolicyConfig


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


class SpawnAgentPostHookHandler(JsonEchoHandler):
    def __init__(self):
        super().__init__("spawn_agent")


class TelemetryHandler(EchoHandler):
    def telemetry_tags(self, _invocation):
        return (
            ("mcp_server", "codex-apps"),
            ("mcp_server_origin", "plugin"),
            ("custom_tag", "custom-value"),
        )


class TelemetryCustomOnlyHandler(TelemetryHandler):
    def matches_kind(self, payload):
        return payload.type == "custom"


class NamespacedTelemetryHandler(TelemetryHandler):
    def __init__(self):
        super().__init__("lookup")
        self.name = ToolName.namespaced("mcp__server__", "lookup")


class LifecycleRecorder:
    def __init__(self):
        self.started = []
        self.finished = []

    def on_tool_start(self, input):
        self.started.append(input)

    async def on_tool_finish(self, input):
        self.finished.append(input)


class TraceContext:
    def __init__(self):
        self.invocations = []
        self.completed = []
        self.failed = []

    def start_tool_dispatch_trace(self, invocation_factory):
        self.invocations.append(invocation_factory())
        return self

    def record_completed(self, status, result):
        self.completed.append((status, result))

    def record_failed(self, error):
        self.failed.append(error)


def _pre_tool_hook_payload(invocation):
    return PreToolUsePayload(
        tool_name=HookToolName.new("mapped"),
        tool_input={"mapped": True},
    )


def _post_tool_hook_payload(invocation, result):
    return PostToolUsePayload(
        tool_name=HookToolName.new("mapped"),
        tool_use_id=invocation.call_id,
        tool_input={"mapped": True},
        tool_response="mapped-response",
    )


class CounterTelemetry:
    def __init__(self):
        self.calls = []

    def counter(self, metric, inc, tags):
        self.calls.append((metric, inc, tuple(tags)))


class ToolRouterTests(unittest.TestCase):
    def test_build_tool_call_uses_namespace_for_registry_name(self) -> None:
        # Rust parity: codex-core::tools::router
        # router_tests.rs::build_tool_call_uses_namespace_for_registry_name.
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

    def test_dispatch_tool_call_emits_tool_read_memory_metric(self) -> None:
        telemetry = CounterTelemetry()
        router = ToolRouter.from_parts(ToolRegistry.with_handler_for_test(EchoHandler("shell_command")), ())
        call = ToolCall(
            tool_name=ToolName.plain("shell_command"),
            call_id="call-memory",
            payload=ToolPayload.function(json.dumps({"command": "cat /home/me/memories/MEMORY.md"})),
        )

        asyncio.run(
            router.dispatch_tool_call_with_terminal_outcome(
                call,
                session_telemetry=telemetry,
                session_shell=Shell(ShellType.BASH, "/bin/bash"),
            )
        )

        self.assertEqual(
            telemetry.calls,
            [
                (
                    MEMORIES_USAGE_METRIC,
                    1,
                    (("kind", "memory_md"), ("tool", "shell_command"), ("success", "true")),
                )
            ],
        )

    def test_dispatch_tool_call_emits_failed_tool_read_memory_metric(self) -> None:
        telemetry = CounterTelemetry()
        router = ToolRouter.from_parts(ToolRegistry.with_handler_for_test(FailingHandler("shell_command")), ())
        call = ToolCall(
            tool_name=ToolName.plain("shell_command"),
            call_id="call-memory-failed",
            payload=ToolPayload.function(json.dumps({"command": "cat /home/me/memories/MEMORY.md"})),
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(
                router.dispatch_tool_call_with_terminal_outcome(
                    call,
                    session_telemetry=telemetry,
                    session_shell=Shell(ShellType.BASH, "/bin/bash"),
                )
            )

        self.assertEqual(
            telemetry.calls,
            [
                (
                    MEMORIES_USAGE_METRIC,
                    1,
                    (("kind", "memory_md"), ("tool", "shell_command"), ("success", "false")),
                )
            ],
        )

    def test_dispatch_tool_call_emits_tool_read_metric_from_mapping_session(self) -> None:
        telemetry = CounterTelemetry()
        session = {
            "session_telemetry": telemetry,
            "user_shell": lambda: Shell(ShellType.BASH, "/bin/bash"),
        }
        invocation = ToolInvocation(
            call_id="call-memory",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function(json.dumps({"command": "cat /home/me/memories/MEMORY.md"})),
            session=session,
        )

        result = asyncio.run(dispatch_tool_call(ToolRegistry.from_tools([EchoHandler("shell_command")]), invocation))

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(
            telemetry.calls,
            [
                (
                    MEMORIES_USAGE_METRIC,
                    1,
                    (("kind", "memory_md"), ("tool", "shell_command"), ("success", "true")),
                )
            ],
        )

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
        # Rust parity: codex-core::tools::router
        # router.rs::ToolRouter::build_tool_call ToolSearchCall client arm.
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
        # Rust parity: codex-core::tools::router
        # router.rs::ToolRouter::build_tool_call ignores non-client or id-less tool_search calls.
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
        self.assertEqual(caught.exception.kind, "respond_to_model")
        self.assertIn("failed to parse tool_search arguments", str(caught.exception))

    def test_build_tool_call_handles_custom_tool_calls(self) -> None:
        # Rust parity: codex-core::tools::router
        # router.rs::ToolRouter::build_tool_call CustomToolCall arm.
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
        self.assertFalse(
            router.tool_supports_parallel(
                ToolCall(
                    tool_name=ToolName.namespaced("mcp__server__", "exec_command"),
                    call_id="call-namespaced-local-name",
                    payload=ToolPayload.function("{}"),
                )
            )
        )

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

    def test_dispatch_tool_call_records_rollout_trace_completion(self) -> None:
        trace = TraceContext()
        session = SimpleNamespace(conversation_id="thread-1")
        turn = SimpleNamespace(sub_id="turn-1")
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session=session,
            turn=turn,
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([EchoHandler()]),
                invocation,
                tool_dispatch_trace_context=trace,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(trace.invocations[0].thread_id, "thread-1")
        self.assertEqual(trace.invocations[0].codex_turn_id, "turn-1")
        self.assertEqual(trace.invocations[0].tool_call_id, "call-1")
        self.assertEqual(trace.completed[0][0], ExecutionStatus.COMPLETED)
        self.assertEqual(trace.completed[0][1].type, "direct_response")

    def test_dispatch_tool_call_reads_mapping_trace_context_and_ids(self) -> None:
        trace = TraceContext()
        session = {
            "conversation_id": "thread-map",
            "services": {
                "rollout_thread_trace": trace,
            },
        }
        turn = {"sub_id": "turn-map"}
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session=session,
            turn=turn,
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([EchoHandler()]),
                invocation,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(trace.invocations[0].thread_id, "thread-map")
        self.assertEqual(trace.invocations[0].codex_turn_id, "turn-map")
        self.assertEqual(trace.completed[0][0], ExecutionStatus.COMPLETED)

    def test_dispatch_tool_call_supports_mapping_tool_runtimes(self) -> None:
        pre_calls = []

        def handle(invocation):
            return FunctionToolOutput.from_text("ok", True)

        tool = {
            "tool_name": ToolName.plain("mapped"),
            "handle": handle,
            "pre_tool_use_payload": _pre_tool_hook_payload,
            "post_tool_use_payload": _post_tool_hook_payload,
        }
        invocation = ToolInvocation(
            call_id="mapped-call",
            tool_name=ToolName.plain("mapped"),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([tool]),
                invocation,
                pre_tool_use_hook=lambda payload: (
                    pre_calls.append(payload),
                    PreToolUseHookResult.continue_(payload.tool_input),
                )[1],
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(len(pre_calls), 1)
        self.assertEqual(pre_calls[0].tool_name, HookToolName.new("mapped"))

    def test_dispatch_tool_call_supports_mapping_keyword_only_tool_handle(self) -> None:
        invocation = ToolInvocation(
            call_id="mapped-kw",
            tool_name=ToolName.plain("mapped_kw"),
            payload=ToolPayload.function("{}"),
        )

        def handle(*, invocation: ToolInvocation) -> FunctionToolOutput:
            return FunctionToolOutput.from_text(f"{invocation.call_id}", True)

        result = asyncio.run(
            dispatch_tool_call(ToolRegistry.from_tools([{"tool_name": ToolName.plain("mapped_kw"), "handle": handle}]), invocation)
        )

        self.assertEqual(result.to_response_item().output.to_text(), "mapped-kw")

    def test_dispatch_tool_call_increments_active_turn_tool_calls_before_lookup(self) -> None:
        session = SimpleNamespace(
            active_turn=SimpleNamespace(
                turn_state=SimpleNamespace(tool_calls=3)
            )
        )
        invocation = ToolInvocation(
            call_id="call-missing",
            tool_name=ToolName.plain("missing"),
            payload=ToolPayload.function("{}"),
            session=session,
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(dispatch_tool_call(ToolRegistry.empty(), invocation))

        self.assertEqual(session.active_turn.turn_state.tool_calls, 4)

    def test_dispatch_tool_call_records_missing_tool_telemetry_failure(self) -> None:
        telemetry_events = []
        invocation = ToolInvocation(
            call_id="call-missing",
            tool_name=ToolName.namespaced("mcp__missing__", "lookup"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.empty(),
                    invocation,
                    tool_result_telemetry_recorder=telemetry_events.append,
                )
            )

        self.assertEqual(len(telemetry_events), 1)
        self.assertEqual(telemetry_events[0]["tool_name"], "mcp__missing__lookup")
        self.assertEqual(telemetry_events[0]["duration_seconds"], 0.0)
        self.assertFalse(telemetry_events[0]["success"])
        self.assertEqual(telemetry_events[0]["telemetry_tags"], ())
        self.assertEqual(telemetry_events[0]["extra_trace_fields"], ())
        self.assertIsInstance(telemetry_events[0]["error"], FunctionCallError)
        self.assertIn("unsupported call", telemetry_events[0]["error_message"])

    def test_dispatch_tool_call_saturates_active_turn_tool_calls(self) -> None:
        max_u64 = (1 << 64) - 1
        session = {
            "active_turn": {
                "turn_state": {
                    "tool_calls": max_u64,
                },
            },
        }
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session=session,
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([EchoHandler()]),
                invocation,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(session["active_turn"]["turn_state"]["tool_calls"], max_u64)

    def test_dispatch_tool_call_records_rollout_trace_failure(self) -> None:
        trace = TraceContext()
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
                    tool_dispatch_trace_context=trace,
                )
            )

        self.assertEqual(trace.completed, [])
        self.assertEqual(len(trace.failed), 1)
        self.assertIsInstance(trace.failed[0], FunctionCallError)

    def test_dispatch_tool_call_records_split_telemetry_tags(self) -> None:
        telemetry_events = []
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry"),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([TelemetryHandler("telemetry")]),
                invocation,
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(
                    feedback_message="post hook feedback",
                ),
                tool_result_telemetry_recorder=telemetry_events.append,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "post hook feedback")
        self.assertEqual(telemetry_events[0]["tool_name"], "telemetry")
        self.assertEqual(telemetry_events[0]["log_payload"], "{}")
        self.assertEqual(telemetry_events[0]["log_preview"], "ok")
        self.assertGreaterEqual(telemetry_events[0]["duration_seconds"], 0.0)
        self.assertIsNone(telemetry_events[0]["error_message"])
        self.assertTrue(telemetry_events[0]["success"])
        self.assertEqual(
            telemetry_events[0]["output"].to_response_item("call-1", invocation.payload).output.to_text(),
            "ok",
        )
        self.assertEqual(telemetry_events[0]["telemetry_tags"], (("custom_tag", "custom-value"),))
        self.assertEqual(
            telemetry_events[0]["extra_trace_fields"],
            (("mcp_server", "codex-apps"), ("mcp_server_origin", "plugin")),
        )

    def test_dispatch_tool_call_records_base_sandbox_telemetry_tags(self) -> None:
        telemetry_events = []
        turn = SimpleNamespace(permission_profile=PermissionProfile.disabled(), cwd=Path("/tmp/work"), network=None)
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry"),
            payload=ToolPayload.function("{}"),
            turn=turn,
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([TelemetryHandler("telemetry")]),
                invocation,
                tool_result_telemetry_recorder=telemetry_events.append,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(
            telemetry_events[0]["telemetry_tags"],
            (
                ("sandbox", "none"),
                ("sandbox_policy", "danger-full-access"),
                ("custom_tag", "custom-value"),
            ),
        )

    def test_dispatch_tool_call_records_external_sandbox_telemetry_tags(self) -> None:
        telemetry_events = []
        turn = SimpleNamespace(
            permission_profile=PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
            cwd=Path("/tmp/work"),
            network=None,
        )
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry"),
            payload=ToolPayload.function("{}"),
            turn=turn,
        )

        asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([TelemetryHandler("telemetry")]),
                invocation,
                tool_result_telemetry_recorder=telemetry_events.append,
            )
        )

        self.assertEqual(telemetry_events[0]["telemetry_tags"][0:2], (("sandbox", "external"), ("sandbox_policy", "external-sandbox")))

    def test_dispatch_tool_call_records_workspace_write_policy_telemetry_tag(self) -> None:
        telemetry_events = []
        cwd = Path("/tmp/work")
        turn = SimpleNamespace(permission_profile=PermissionProfile.workspace_write((cwd,)), cwd=cwd, network=None)
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry"),
            payload=ToolPayload.function("{}"),
            turn=turn,
        )

        asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([TelemetryHandler("telemetry")]),
                invocation,
                tool_result_telemetry_recorder=telemetry_events.append,
            )
        )

        self.assertEqual(telemetry_events[0]["telemetry_tags"][1], ("sandbox_policy", "workspace-write"))

    def test_dispatch_tool_call_records_telemetry_from_mapping_session(self) -> None:
        telemetry_events = []
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry"),
            payload=ToolPayload.function("{}"),
            session={"tool_result_with_tags": telemetry_events.append},
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([TelemetryHandler("telemetry")]),
                invocation,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertTrue(telemetry_events[0]["success"])
        self.assertEqual(telemetry_events[0]["tool_name"], "telemetry")
        self.assertEqual(telemetry_events[0]["telemetry_tags"], (("custom_tag", "custom-value"),))

    def test_dispatch_tool_call_records_flat_namespaced_telemetry_tool_name(self) -> None:
        telemetry_events = []
        handler = NamespacedTelemetryHandler()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=handler.tool_name(),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([handler]),
                invocation,
                tool_result_telemetry_recorder=telemetry_events.append,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(telemetry_events[0]["tool_name"], "mcp__server__lookup")

    def test_dispatch_tool_call_records_incompatible_telemetry_failure(self) -> None:
        telemetry_events = []
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("telemetry_custom_only"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([TelemetryCustomOnlyHandler("telemetry_custom_only")]),
                    invocation,
                    tool_result_telemetry_recorder=telemetry_events.append,
                )
            )

        self.assertFalse(telemetry_events[0]["success"])
        self.assertIsInstance(telemetry_events[0]["error"], FunctionCallError)
        self.assertEqual(telemetry_events[0]["error_message"], "tool telemetry_custom_only invoked with incompatible payload")
        self.assertEqual(telemetry_events[0]["extra_trace_fields"][0], ("mcp_server", "codex-apps"))

    def test_dispatch_tool_call_skips_memory_metric_for_incompatible_payload(self) -> None:
        telemetry = CounterTelemetry()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function(json.dumps({"command": "cat /home/me/memories/MEMORY.md"})),
        )

        with self.assertRaises(FunctionCallError):
            asyncio.run(
                dispatch_tool_call(
                    ToolRegistry.from_tools([TelemetryCustomOnlyHandler("shell_command")]),
                    invocation,
                    session_telemetry=telemetry,
                    session_shell=Shell(ShellType.BASH, "/bin/bash"),
                )
            )

        self.assertEqual(telemetry.calls, [])

    def test_router_dispatch_records_post_hook_contexts_from_invocation_session(self) -> None:
        class ContextSession:
            def __init__(self):
                self.recorded = []

            def record_additional_context_messages(self, messages):
                self.recorded.extend(messages)

        session = ContextSession()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([JsonEchoHandler("json_echo")]), ())
        call = ToolCall(
            tool_name=ToolName.plain("json_echo"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            router.dispatch_tool_call_with_terminal_outcome(
                call,
                session=session,
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(
                    feedback_message="post hook feedback",
                    additional_contexts=("context from high-level router",),
                ),
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "post hook feedback")
        self.assertEqual(
            [message.content[0].text for message in session.recorded],
            ["context from high-level router"],
        )

    def test_router_dispatch_records_post_hook_contexts_from_mapping_session(self) -> None:
        recorded = []
        router = ToolRouter.from_parts(ToolRegistry.from_tools([JsonEchoHandler("json_echo")]), ())
        call = ToolCall(
            tool_name=ToolName.plain("json_echo"),
            call_id="call-1",
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            router.dispatch_tool_call_with_terminal_outcome(
                call,
                session={"record_additional_context_messages": recorded.extend},
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(
                    feedback_message="post hook feedback",
                    additional_contexts=("context from mapping session",),
                ),
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "post hook feedback")
        self.assertEqual([message.content[0].text for message in recorded], ["context from mapping session"])

    def test_dispatch_tool_call_applies_tool_completed_goal_runtime_after_finish(self) -> None:
        class GoalSession:
            def __init__(self):
                self.events = []

            async def goal_runtime_apply(self, event):
                self.events.append(event)

        session = GoalSession()
        turn = SimpleNamespace(turn_id="turn-1")
        recorder = LifecycleRecorder()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session=session,
            turn=turn,
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([EchoHandler()]),
                invocation,
                lifecycle_contributors=[recorder],
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.completed(True))
        self.assertEqual(
            session.events,
            [{"type": "tool_completed", "turn_context": turn, "tool_name": "echo"}],
        )

    def test_dispatch_tool_call_skips_goal_runtime_when_finish_is_claimed(self) -> None:
        session = SimpleNamespace(events=[])

        async def goal_runtime_apply(event):
            session.events.append(event)

        session.goal_runtime_apply = goal_runtime_apply
        flag = TerminalOutcomeFlag(True)
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session=session,
            turn=SimpleNamespace(turn_id="turn-1"),
        )

        result = asyncio.run(
            dispatch_tool_call_with_terminal_outcome(
                ToolRegistry.from_tools([EchoHandler()]),
                invocation,
                terminal_outcome_reached=flag,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(session.events, [])

    def test_dispatch_tool_call_applies_goal_runtime_from_mapping_session(self) -> None:
        events = []
        turn = SimpleNamespace(turn_id="turn-1")
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{}"),
            session={"goal_runtime_apply": events.append},
            turn=turn,
        )

        result = asyncio.run(dispatch_tool_call(ToolRegistry.from_tools([EchoHandler()]), invocation))

        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(events, [{"type": "tool_completed", "turn_context": turn, "tool_name": "echo"}])

    def test_environment_tool_router_dispatches_exec_command(self) -> None:
        if sys.platform == "win32":
            shell = Shell(ShellType.POWERSHELL, shutil.which("powershell") or "powershell.exe")
            command = "(Get-Location).Path"
        else:
            shell = Shell(ShellType.SH, shutil.which("sh") or "/bin/sh")
            command = "pwd"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            turn = SimpleNamespace(
                environments=(SimpleNamespace(environment_id="local", cwd=root),),
                truncation_policy=TruncationPolicyConfig.tokens(10_000),
            )
            router = build_environment_tool_router_from_turn_context(turn)
            call = ToolCall(
                tool_name=ToolName.plain("exec_command"),
                call_id="call-routed-exec",
                payload=ToolPayload.function(json.dumps({"cmd": command})),
            )

            result = asyncio.run(
                router.dispatch_tool_call_with_terminal_outcome(
                    call,
                    session=SimpleNamespace(user_shell=lambda: shell),
                    turn=turn,
                )
            )

            self.assertEqual(result.result.exit_code, 0)
            self.assertIn(str(root), result.result.raw_output.decode("utf-8", errors="replace"))

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

    def test_dispatch_tool_call_rejects_view_image_tool_search_payload(self) -> None:
        invocation = ToolInvocation(
            call_id="call-image-search",
            tool_name=ToolName.plain("view_image"),
            payload=ToolPayload.tool_search(SearchToolCallParams("image")),
        )

        with self.assertRaises(FunctionCallError) as caught:
            asyncio.run(dispatch_tool_call(ToolRegistry.from_tools([ViewImageHandler()]), invocation))

        self.assertEqual(caught.exception.kind, "fatal")
        self.assertEqual(
            str(caught.exception),
            "Fatal error: tool view_image invoked with incompatible payload",
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

    def test_dispatch_skips_post_tool_use_hook_for_unsuccessful_tool_output(self) -> None:
        class UnsuccessfulHandler(EchoHandler):
            def handle(self, invocation):
                self.invocations.append(invocation)
                return FunctionToolOutput.from_text("not ok", False)

        hook_called = False

        def post_hook(_payload, _result):
            nonlocal hook_called
            hook_called = True
            return PostToolUseHookOutcome(feedback_message="should not appear")

        recorder = LifecycleRecorder()
        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([UnsuccessfulHandler()]),
                ToolInvocation(
                    call_id="call-1",
                    tool_name=ToolName.plain("echo"),
                    payload=ToolPayload.function("{}"),
                ),
                lifecycle_contributors=[recorder],
                post_tool_use_hook=post_hook,
            )
        )

        self.assertFalse(hook_called)
        self.assertEqual(result.to_response_item().output.to_text(), "not ok")
        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.completed(False))

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

    def test_dispatch_pre_tool_use_hook_supports_keyword_only_signature(self) -> None:
        handler = EchoHandler()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function('{"before":true}'),
        )
        observed: dict[str, bool] = {}

        def pre_tool_use_hook(*, payload: PreToolUsePayload, invocation: ToolInvocation) -> dict[str, Any]:
            observed["called"] = True
            self.assertEqual(payload.tool_input, {"before": True})
            return {"type": "continue"}

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([handler]),
                invocation,
                pre_tool_use_hook=pre_tool_use_hook,
            )
        )

        self.assertTrue(observed.get("called", False))
        self.assertEqual(result.to_response_item().output.to_text(), "ok")
        self.assertEqual(handler.invocations, [invocation])

    def test_dispatch_post_tool_use_hook_supports_keyword_only_signature(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("json_echo"),
            payload=ToolPayload.function("{}"),
        )
        observed = {}

        def post_tool_use_hook(
            *, payload: PostToolUsePayload, result: Any
        ) -> PostToolUseHookOutcome:
            observed["called"] = True
            self.assertEqual(payload.tool_name.name, "json_echo")
            self.assertIn("ok", payload.tool_response)
            self.assertEqual(result.to_response_item().output.to_text(), "{" + '"ok":true' + "}")
            return PostToolUseHookOutcome(
                should_stop=True,
                feedback_message="keyword-only post hook",
            )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([JsonEchoHandler("json_echo")]),
                invocation,
                post_tool_use_hook=post_tool_use_hook,
            )
        )

        self.assertTrue(observed.get("called", False))
        self.assertEqual(result.to_response_item().output.to_text(), "keyword-only post hook")

    def test_dispatch_pre_tool_use_hook_uses_handler_specific_input_rewrite(self) -> None:
        class CustomRewriteHandler(EchoHandler):
            def with_updated_hook_input(self, invocation, updated_input):
                return ToolInvocation(
                    call_id=invocation.call_id,
                    tool_name=invocation.tool_name,
                    payload=ToolPayload.function(json.dumps({"custom": updated_input["after"]}, separators=(",", ":"))),
                    source=invocation.source,
                    session=invocation.session,
                    turn=invocation.turn,
                )

        handler = CustomRewriteHandler()
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

        self.assertEqual(handler.invocations[0].payload, ToolPayload.function('{"custom":true}'))

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

    def test_dispatch_post_tool_use_hook_uses_default_stop_feedback(self) -> None:
        recorder = LifecycleRecorder()
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("json_echo"),
            payload=ToolPayload.function("{}"),
        )

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([JsonEchoHandler("json_echo")]),
                invocation,
                lifecycle_contributors=[recorder],
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(should_stop=True),
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "PostToolUse hook stopped execution")
        self.assertEqual(result.code_mode_result(), {"ok": True})
        self.assertEqual(recorder.finished[0].outcome, ToolCallOutcome.completed(True))

    def test_dispatch_post_tool_use_hook_receives_matcher_aliases(self) -> None:
        observed = []
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("spawn_agent"),
            payload=ToolPayload.function("{}"),
        )

        def post_tool_use_hook(payload, _result):
            observed.append((payload.tool_name.name, payload.tool_name.matcher_aliases))
            return PostToolUseHookOutcome()

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([SpawnAgentPostHookHandler()]),
                invocation,
                post_tool_use_hook=post_tool_use_hook,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), '{"ok":true}')
        self.assertEqual(observed, [("spawn_agent", ("Agent",))])

    def test_dispatch_post_tool_use_hook_records_additional_contexts_before_feedback(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("json_echo"),
            payload=ToolPayload.function("{}"),
        )
        recorded = []

        def additional_context_recorder(messages):
            recorded.extend(messages)

        result = asyncio.run(
            dispatch_tool_call(
                ToolRegistry.from_tools([JsonEchoHandler("json_echo")]),
                invocation,
                post_tool_use_hook=lambda _payload, _result: PostToolUseHookOutcome(
                    feedback_message="post hook feedback",
                    additional_contexts=("first tide note", "second tide note"),
                ),
                additional_context_recorder=additional_context_recorder,
            )
        )

        self.assertEqual(result.to_response_item().output.to_text(), "post hook feedback")
        self.assertEqual([message.role for message in recorded], ["developer", "developer"])
        self.assertEqual(
            [message.content[0].text for message in recorded],
            ["first tide note", "second tide note"],
        )


if __name__ == "__main__":
    unittest.main()
