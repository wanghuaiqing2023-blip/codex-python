import unittest

from pycodex.core import (
    AnyToolResult,
    CodeModeWaitHandler,
    MULTI_AGENT_V1_NAMESPACE,
    FunctionCallError,
    FunctionCallErrorKind,
    FunctionToolOutput,
    HookToolName,
    JsonToolOutput,
    McpToolOutput,
    PostToolUsePayload,
    PreToolUsePayload,
    RegisteredTool,
    ToolCallSource,
    ToolInvocation,
    ToolExposure,
    ToolPayload,
    ToolRegistry,
    flat_tool_name,
    function_hook_tool_input,
    override_tool_exposure,
    post_tool_use_payload,
    pre_tool_use_payload,
    unsupported_tool_call_message,
    with_updated_hook_input,
)
from pycodex.core.tools.handlers.unified_exec import WriteStdinHandler
from pycodex.core.tools.tool_search_entry import (
    ToolSearchInfo,
)
from pycodex.protocol import CallToolResult, FunctionCallOutputContentItem, ToolName, TruncationPolicyConfig


class ToolRegistryRegistrationTests(unittest.TestCase):
    def test_tool_exposure_directness_matches_upstream_groups(self) -> None:
        self.assertTrue(ToolExposure.DIRECT.is_direct())
        self.assertTrue(ToolExposure.DIRECT_MODEL_ONLY.is_direct())
        self.assertFalse(ToolExposure.DEFERRED.is_direct())
        self.assertFalse(ToolExposure.HIDDEN.is_direct())

    def test_registry_looks_up_namespaced_aliases_explicitly(self) -> None:
        namespace = "mcp__codex_apps__gmail"
        tool_name = "gmail_get_recent_emails"
        plain_name = ToolName.plain(tool_name)
        namespaced_name = ToolName.namespaced(namespace, tool_name)
        plain_handler = RegisteredTool(name=plain_name)
        namespaced_handler = RegisteredTool(name=namespaced_name)
        registry = ToolRegistry.from_tools([plain_handler, namespaced_handler])

        self.assertIs(registry.tool(plain_name), plain_handler)
        self.assertIs(registry.tool(namespaced_name), namespaced_handler)
        self.assertIsNone(
            registry.tool(ToolName.namespaced("mcp__codex_apps__calendar", tool_name))
        )

    def test_registry_rejects_duplicate_tool_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "already registered"):
            ToolRegistry.from_tools(
                [
                    RegisteredTool.plain("echo"),
                    RegisteredTool.plain("echo"),
                ]
            )

    def test_registry_rejects_non_rust_registration_shapes(self) -> None:
        with self.assertRaises(TypeError):
            RegisteredTool(name="echo")
        with self.assertRaises(TypeError):
            RegisteredTool.plain("echo", supports_parallel=1)
        with self.assertRaises(TypeError):
            RegisteredTool.plain("echo", payload_types="function")
        with self.assertRaises(TypeError):
            ToolRegistry("echo")
        with self.assertRaises(TypeError):
            ToolRegistry({ToolName.plain("echo"): object()})
        with self.assertRaises(TypeError):
            ToolRegistry.from_tools("echo")

    def test_registry_normalizes_string_tool_names_through_tool_name_boundary(self) -> None:
        class StringNamedTool:
            def tool_name(self):
                return "echo"

        registry = ToolRegistry.from_tools([StringNamedTool()])

        self.assertEqual(registry.tool_names(), (ToolName.plain("echo"),))

    def test_registry_test_helpers_match_sorted_upstream_names(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("zeta"),
                RegisteredTool.plain("alpha"),
            ]
        )

        self.assertEqual(
            registry.tool_names_for_test(),
            (ToolName.plain("alpha"), ToolName.plain("zeta")),
        )
        self.assertEqual(
            ToolRegistry.with_handler_for_test(RegisteredTool.plain("solo")).tool_names_for_test(),
            (ToolName.plain("solo"),),
        )

    def test_registry_reports_exposure_parallel_support_and_kind_matching(self) -> None:
        shell = RegisteredTool.plain(
            "shell_command",
            exposure=ToolExposure.DIRECT,
            supports_parallel=True,
            waits_for_cancellation=True,
            payload_types=("function",),
        )
        registry = ToolRegistry.from_tools([shell])
        name = ToolName.plain("shell_command")

        self.assertEqual(registry.tool_names(), (name,))
        self.assertEqual(registry.tool_exposure(name), ToolExposure.DIRECT)
        self.assertTrue(registry.supports_parallel_tool_calls(name))
        self.assertTrue(registry.waits_for_runtime_cancellation(name))
        self.assertTrue(registry.matches_kind(name, ToolPayload.function("{}")))
        self.assertFalse(registry.matches_kind(name, ToolPayload.custom("raw")))
        self.assertIsNone(registry.supports_parallel_tool_calls(ToolName.plain("missing")))
        self.assertIsNone(registry.waits_for_runtime_cancellation(ToolName.plain("missing")))
        with self.assertRaises(TypeError):
            registry.tool("shell_command")
        with self.assertRaises(TypeError):
            registry.matches_kind(name, object())

    def test_registry_collects_handler_search_infos(self) -> None:
        search_info = ToolSearchInfo.from_spec(
            "calendar create event",
            {
                "type": "function",
                "name": "create_event",
                "description": "Create an event",
                "strict": False,
                "parameters": {"type": "object"},
            },
        )

        class SearchableTool(RegisteredTool):
            def search_info(self):
                return search_info

        registry = ToolRegistry.from_tools(
            [
                SearchableTool(name=ToolName.plain("create_event")),
                RegisteredTool.plain("plain"),
            ]
        )

        self.assertEqual(registry.search_infos(), (search_info,))

    def test_exposure_override_preserves_handler_and_suppresses_hidden_parallelism(self) -> None:
        handler = RegisteredTool.plain("exec_command", supports_parallel=True)

        self.assertIs(override_tool_exposure(handler, ToolExposure.DIRECT), handler)

        hidden = override_tool_exposure(handler, ToolExposure.HIDDEN)
        self.assertEqual(hidden.tool_name(), ToolName.plain("exec_command"))
        self.assertEqual(hidden.exposure(), ToolExposure.HIDDEN)
        self.assertFalse(hidden.supports_parallel_tool_calls())
        self.assertFalse(hidden.waits_for_runtime_cancellation())
        self.assertTrue(hidden.matches_kind(ToolPayload.function("{}")))

    def test_exposure_override_keeps_runtime_cancellation_wait_when_hidden(self) -> None:
        handler = RegisteredTool.plain(
            "exec_command",
            supports_parallel=True,
            waits_for_cancellation=True,
        )

        hidden = override_tool_exposure(handler, ToolExposure.HIDDEN)

        self.assertFalse(hidden.supports_parallel_tool_calls())
        self.assertTrue(hidden.waits_for_runtime_cancellation())

    def test_exposure_override_delegates_handler_hook_payload_overrides(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function('{"message":"hello"}'),
        )

        class CustomHookTool(RegisteredTool):
            def handle(self, _invocation):
                return "handled"

            def pre_tool_use_payload(self, _invocation):
                return PreToolUsePayload(
                    tool_name=HookToolName.new("custom_pre"),
                    tool_input={"pre": True},
                )

            def post_tool_use_payload(self, _invocation, _result):
                return PostToolUsePayload(
                    tool_name=HookToolName.new("custom_post"),
                    tool_use_id="custom-call",
                    tool_input={"post": True},
                    tool_response={"ok": True},
                )

            def with_updated_hook_input(self, invocation, updated_input):
                return ToolInvocation(
                    call_id=invocation.call_id,
                    tool_name=invocation.tool_name,
                    payload=ToolPayload.function(f'{{"custom":{str(bool(updated_input)).lower()}}}'),
                )

            def telemetry_tags(self, _invocation):
                return (("custom_tag", "custom-value"),)

        overridden = override_tool_exposure(
            CustomHookTool(name=ToolName.plain("echo")),
            ToolExposure.HIDDEN,
        )

        self.assertEqual(
            overridden.pre_tool_use_payload(invocation),
            PreToolUsePayload(
                tool_name=HookToolName.new("custom_pre"),
                tool_input={"pre": True},
            ),
        )
        self.assertEqual(
            overridden.post_tool_use_payload(invocation, FunctionToolOutput.from_text("ignored", True)),
            PostToolUsePayload(
                tool_name=HookToolName.new("custom_post"),
                tool_use_id="custom-call",
                tool_input={"post": True},
                tool_response={"ok": True},
            ),
        )
        self.assertEqual(
            overridden.with_updated_hook_input(invocation, {"custom": True}).payload,
            ToolPayload.function('{"custom":true}'),
        )
        self.assertEqual(
            overridden.telemetry_tags(invocation),
            (("custom_tag", "custom-value"),),
        )
        self.assertEqual(overridden.handle(invocation), "handled")

        class BadParallelTool(RegisteredTool):
            def supports_parallel_tool_calls(self):
                return 1

        bad = BadParallelTool(name=ToolName.plain("bad"))
        bad_registry = ToolRegistry.from_tools([bad])
        with self.assertRaises(TypeError):
            bad_registry.supports_parallel_tool_calls(ToolName.plain("bad"))

        class BadCancellationTool(RegisteredTool):
            def waits_for_runtime_cancellation(self):
                return 1

        bad_cancellation = ToolRegistry.from_tools([BadCancellationTool(name=ToolName.plain("bad_cancel"))])
        with self.assertRaises(TypeError):
            bad_cancellation.waits_for_runtime_cancellation(ToolName.plain("bad_cancel"))

    def test_registry_exposes_waits_for_runtime_cancellation_like_core_runtime(self) -> None:
        registry = ToolRegistry.from_tools(
            [
                RegisteredTool.plain("exec_command", waits_for_cancellation=True),
                RegisteredTool.plain("plan"),
            ]
        )

        self.assertTrue(registry.waits_for_runtime_cancellation(ToolName.plain("exec_command")))
        self.assertFalse(registry.waits_for_runtime_cancellation(ToolName.plain("plan")))

    def test_dispatch_any_runs_matching_handler_and_wraps_result(self) -> None:
        # Rust source: codex-core/src/tools/registry.rs
        # Rust contract: ToolRegistry::dispatch_any + handle_any_tool wrap handler output
        class EchoTool(RegisteredTool):
            def handle(self, invocation):
                return FunctionToolOutput.from_text(f"echo {invocation.call_id}", True)

        registry = ToolRegistry.from_tools([EchoTool(name=ToolName.plain("echo"))])
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function('{"message":"hello"}'),
        )

        result = registry.dispatch_any(invocation)

        self.assertIsInstance(result, AnyToolResult)
        self.assertEqual(result.call_id, "call-1")
        self.assertEqual(result.payload, ToolPayload.function('{"message":"hello"}'))
        self.assertEqual(result.into_response().output.to_text(), "echo call-1")
        self.assertEqual(result.code_mode_result(), "echo call-1")
        self.assertEqual(
            result.post_tool_use_payload,
            PostToolUsePayload(
                tool_name=HookToolName.new("echo"),
                tool_use_id="call-1",
                tool_input={"message": "hello"},
                tool_response="echo call-1",
            ),
        )

    def test_dispatch_any_reports_unsupported_tool_to_model(self) -> None:
        # Rust source: codex-core/src/tools/registry.rs
        # Rust contract: missing tool returns FunctionCallError::RespondToModel
        registry = ToolRegistry.empty()
        invocation = ToolInvocation(
            call_id="missing-call",
            tool_name=ToolName.plain("missing"),
            payload=ToolPayload.function("{}"),
        )

        with self.assertRaises(FunctionCallError) as caught:
            registry.dispatch_any(invocation)

        self.assertEqual(caught.exception.kind, FunctionCallErrorKind.RESPOND_TO_MODEL)
        self.assertEqual(str(caught.exception), "unsupported call: missing")

    def test_dispatch_any_rejects_incompatible_payload_as_fatal(self) -> None:
        # Rust source: codex-core/src/tools/registry.rs
        # Rust contract: existing tool with incompatible payload is fatal
        class FunctionOnlyTool(RegisteredTool):
            def handle(self, _invocation):
                return FunctionToolOutput.from_text("should not run", True)

        registry = ToolRegistry.from_tools(
            [
                FunctionOnlyTool(
                    name=ToolName.plain("function_only"),
                    payload_types=("function",),
                )
            ]
        )
        invocation = ToolInvocation(
            call_id="custom-call",
            tool_name=ToolName.plain("function_only"),
            payload=ToolPayload.custom("raw custom input"),
        )

        with self.assertRaises(FunctionCallError) as caught:
            registry.dispatch_any(invocation)

        self.assertEqual(caught.exception.kind, FunctionCallErrorKind.FATAL)
        self.assertEqual(
            str(caught.exception),
            "Fatal error: tool function_only invoked with incompatible payload",
        )

    def test_unsupported_tool_call_message_distinguishes_custom_tools(self) -> None:
        self.assertEqual(
            unsupported_tool_call_message(
                ToolPayload.custom("*** Begin Patch"),
                ToolName.plain("apply_patch"),
            ),
            "unsupported custom tool call: apply_patch",
        )
        self.assertEqual(
            unsupported_tool_call_message(
                ToolPayload.function("{}"),
                ToolName.plain("shell_command"),
            ),
            "unsupported call: shell_command",
        )
        self.assertEqual(
            unsupported_tool_call_message(
                ToolPayload.custom("raw"),
                ToolName.namespaced("mcp__server__", "lookup"),
            ),
            "unsupported custom tool call: mcp__server__lookup",
        )
        self.assertEqual(
            unsupported_tool_call_message(
                ToolPayload.function("{}"),
                ToolName.namespaced("functions.", "echo"),
            ),
            "unsupported call: functions.echo",
        )
        with self.assertRaises(TypeError):
            unsupported_tool_call_message(object(), ToolName.plain("shell_command"))


class ToolRegistryHookTests(unittest.TestCase):
    def test_flat_tool_name_concatenates_namespace_only_at_legacy_boundary(self) -> None:
        self.assertEqual(flat_tool_name(ToolName.plain("echo")), "echo")
        self.assertEqual(flat_tool_name(ToolName.namespaced("functions.", "echo")), "functions.echo")
        with self.assertRaises(TypeError):
            flat_tool_name("echo")

    def test_function_tools_expose_default_hook_payloads_and_rewrites(self) -> None:
        # Rust parity: codex-core::tools::registry
        # registry_tests.rs::function_tools_expose_default_hook_payloads_and_rewrites.
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.namespaced("functions.", "echo"),
            payload=ToolPayload.function('{"message":"hello"}'),
        )
        output = FunctionToolOutput.from_text("echoed", True)

        self.assertEqual(
            pre_tool_use_payload(invocation),
            PreToolUsePayload(
                tool_name=HookToolName.new("functions.echo"),
                tool_input={"message": "hello"},
            ),
        )
        self.assertEqual(
            post_tool_use_payload(invocation, output),
            PostToolUsePayload(
                tool_name=HookToolName.new("functions.echo"),
                tool_use_id="call-1",
                tool_input={"message": "hello"},
                tool_response="echoed",
            ),
        )

        rewritten = with_updated_hook_input(invocation, {"message": "rewritten"})
        self.assertEqual(rewritten.payload, ToolPayload.function('{"message":"rewritten"}'))

        with self.assertRaises(TypeError):
            pre_tool_use_payload(object())
        with self.assertRaises(TypeError):
            post_tool_use_payload(object(), output)
        with self.assertRaises(TypeError):
            with_updated_hook_input(object(), {})

    def test_function_hook_input_defaults_empty_arguments_to_object(self) -> None:
        # Rust parity: codex-core::tools::registry
        # registry_tests.rs::function_hook_input_defaults_empty_arguments_to_object.
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("  "),
        )

        self.assertEqual(function_hook_tool_input("  "), {})
        self.assertEqual(
            pre_tool_use_payload(invocation),
            PreToolUsePayload(tool_name=HookToolName.new("echo"), tool_input={}),
        )
        self.assertEqual(
            post_tool_use_payload(invocation, FunctionToolOutput.from_text("ok", True)).tool_input,
            {},
        )
        with self.assertRaises(TypeError):
            function_hook_tool_input(1)

    def test_function_hook_input_falls_back_to_string_for_invalid_json(self) -> None:
        invocation = ToolInvocation(
            call_id="call-1",
            tool_name=ToolName.plain("echo"),
            payload=ToolPayload.function("{not json"),
        )

        self.assertEqual(function_hook_tool_input("{not json"), "{not json")
        self.assertEqual(
            post_tool_use_payload(invocation, FunctionToolOutput.from_text("ok", True)).tool_input,
            "{not json",
        )

    def test_spawn_agent_function_tools_use_agent_matcher_alias(self) -> None:
        # Rust parity: codex-core::tools::registry
        # registry_tests.rs::spawn_agent_function_tools_use_agent_matcher_alias.
        output = FunctionToolOutput.from_text("accepted", True)
        hook_payloads = [
            pre_tool_use_payload(
                ToolInvocation(
                    call_id="call-1",
                    tool_name=tool_name,
                    payload=ToolPayload.function('{"message":"inspect this repo"}'),
                )
            )
            for tool_name in (
                ToolName.plain("spawn_agent"),
                ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "spawn_agent"),
            )
        ]
        post_hook_payloads = [
            post_tool_use_payload(
                ToolInvocation(
                    call_id="call-1",
                    tool_name=tool_name,
                    payload=ToolPayload.function('{"message":"inspect this repo"}'),
                ),
                output,
            )
            for tool_name in (
                ToolName.plain("spawn_agent"),
                ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "spawn_agent"),
            )
        ]

        self.assertEqual(
            hook_payloads,
            [
                PreToolUsePayload(
                    tool_name=HookToolName.spawn_agent(),
                    tool_input={"message": "inspect this repo"},
                ),
                PreToolUsePayload(
                    tool_name=HookToolName.spawn_agent(),
                    tool_input={"message": "inspect this repo"},
                ),
            ],
        )
        self.assertEqual(
            [payload.tool_name for payload in post_hook_payloads],
            [HookToolName.spawn_agent(), HookToolName.spawn_agent()],
        )
        self.assertEqual(
            [payload.tool_response for payload in post_hook_payloads],
            ["accepted", "accepted"],
        )

    def test_non_function_payloads_do_not_expose_default_hook_payloads(self) -> None:
        invocation = ToolInvocation(
            call_id="search-1",
            tool_name=ToolName.plain("tool_search"),
            payload=ToolPayload.custom("raw"),
        )
        output = FunctionToolOutput.from_text("ignored", True)

        self.assertIsNone(pre_tool_use_payload(invocation))
        self.assertIsNone(post_tool_use_payload(invocation, output))
        with self.assertRaisesRegex(ValueError, "unsupported function tool payload"):
            with_updated_hook_input(invocation, {"message": "rewritten"})

    def test_runtime_overrides_can_suppress_default_hook_payloads(self) -> None:
        # Rust parity: codex-core::tools::registry
        # registry_tests.rs::code_mode_wait_does_not_expose_default_hook_payloads
        # and write_stdin_does_not_expose_default_pre_tool_use_payload.
        output = FunctionToolOutput.from_text("ok", True)
        wait = CodeModeWaitHandler()
        wait_invocation = ToolInvocation(
            call_id="wait-call",
            tool_name=wait.tool_name(),
            payload=ToolPayload.function("{}"),
        )
        write_stdin = WriteStdinHandler()
        write_invocation = ToolInvocation(
            call_id="write-stdin-call",
            tool_name=write_stdin.tool_name(),
            payload=ToolPayload.function('{"session_id":45}'),
        )

        self.assertIsNone(wait.pre_tool_use_payload(wait_invocation))
        self.assertIsNone(wait.post_tool_use_payload(wait_invocation, output))
        self.assertIsNone(write_stdin.pre_tool_use_payload(write_invocation))

    def test_post_tool_use_payload_prefers_output_overrides(self) -> None:
        class StableHookOutput:
            def post_tool_use_id(self, call_id: str) -> str:
                return f"event-{call_id}"

            def post_tool_use_input(self, _payload: ToolPayload):
                return {"command": "echo hi"}

            def post_tool_use_response(self, _call_id: str, _payload: ToolPayload):
                return "stable hook response"

        invocation = ToolInvocation(
            call_id="call-9",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function('{"command":"echo hi"}'),
        )

        self.assertEqual(
            post_tool_use_payload(invocation, StableHookOutput()),
            PostToolUsePayload(
                tool_name=HookToolName.new("shell_command"),
                tool_use_id="event-call-9",
                tool_input={"command": "echo hi"},
                tool_response="stable hook response",
            ),
        )

    def test_post_tool_use_payload_preserves_json_output_response(self) -> None:
        invocation = ToolInvocation(
            call_id="call-json",
            tool_name=ToolName.plain("json_echo"),
            payload=ToolPayload.function('{"message":"hello"}'),
        )
        output = JsonToolOutput.new({"ok": True, "items": [1, 2]})

        self.assertEqual(
            post_tool_use_payload(invocation, output),
            PostToolUsePayload(
                tool_name=HookToolName.new("json_echo"),
                tool_use_id="call-json",
                tool_input={"message": "hello"},
                tool_response={"ok": True, "items": [1, 2]},
            ),
        )

    def test_post_tool_use_payload_preserves_function_content_items_response(self) -> None:
        invocation = ToolInvocation(
            call_id="call-content",
            tool_name=ToolName.plain("render"),
            payload=ToolPayload.function('{"path":"image.png"}'),
        )
        output = FunctionToolOutput.from_content(
            (
                FunctionCallOutputContentItem.input_text("rendered"),
                {"type": "input_image", "image_url": "file:///tmp/image.png"},
            ),
            True,
        )

        payload = post_tool_use_payload(invocation, output)

        self.assertEqual(payload.tool_input, {"path": "image.png"})
        self.assertEqual(payload.tool_response[0], {"type": "input_text", "text": "rendered"})
        self.assertEqual(payload.tool_response[1], {"type": "input_image", "image_url": "file:///tmp/image.png"})

    def test_post_tool_use_payload_preserves_mcp_input_and_result(self) -> None:
        invocation = ToolInvocation(
            call_id="call-mcp",
            tool_name=ToolName.namespaced("mcp__sample__", "lookup"),
            payload=ToolPayload.function('{"query":"hello"}'),
        )
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "ok"},),
                structured_content={"answer": 42},
                is_error=False,
            ),
            tool_input={"query": "hello", "cursor": None},
            wall_time_seconds=0.25,
            original_image_detail_supported=False,
            truncation_policy=TruncationPolicyConfig.bytes(1024),
        )

        payload = post_tool_use_payload(invocation, output)

        self.assertEqual(payload.tool_name, HookToolName.new("mcp__sample__lookup"))
        self.assertEqual(payload.tool_use_id, "call-mcp")
        self.assertEqual(payload.tool_input, {"query": "hello", "cursor": None})
        self.assertEqual(payload.tool_response["structuredContent"], {"answer": 42})
        self.assertFalse(payload.tool_response["isError"])

    def test_tool_invocation_and_sources_reject_non_rust_shapes(self) -> None:
        with self.assertRaises(ValueError):
            ToolCallSource.direct().__class__("direct", cell_id="cell")
        with self.assertRaises(TypeError):
            ToolCallSource.code_mode(1, "runtime")
        with self.assertRaises(ValueError):
            ToolCallSource("unknown")
        with self.assertRaises(TypeError):
            ToolInvocation(
                call_id=1,
                tool_name=ToolName.plain("echo"),
                payload=ToolPayload.function("{}"),
            )
        with self.assertRaises(TypeError):
            PreToolUsePayload(tool_name="echo", tool_input={})
        with self.assertRaises(TypeError):
            PostToolUsePayload(
                tool_name=HookToolName.new("echo"),
                tool_use_id=1,
                tool_input={},
                tool_response={},
            )


if __name__ == "__main__":
    unittest.main()
