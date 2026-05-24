import unittest

from pycodex.core import (
    MULTI_AGENT_V1_NAMESPACE,
    FunctionToolOutput,
    HookToolName,
    PostToolUsePayload,
    PreToolUsePayload,
    RegisteredTool,
    ToolInvocation,
    ToolExposure,
    ToolPayload,
    ToolRegistry,
    ToolSearchInfo,
    flat_tool_name,
    function_hook_tool_input,
    override_tool_exposure,
    post_tool_use_payload,
    pre_tool_use_payload,
    unsupported_tool_call_message,
    with_updated_hook_input,
)
from pycodex.protocol import ToolName


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

    def test_registry_reports_exposure_parallel_support_and_kind_matching(self) -> None:
        shell = RegisteredTool.plain(
            "shell_command",
            exposure=ToolExposure.DIRECT,
            supports_parallel=True,
            payload_types=("function",),
        )
        registry = ToolRegistry.from_tools([shell])
        name = ToolName.plain("shell_command")

        self.assertEqual(registry.tool_names(), (name,))
        self.assertEqual(registry.tool_exposure(name), ToolExposure.DIRECT)
        self.assertTrue(registry.supports_parallel_tool_calls(name))
        self.assertTrue(registry.matches_kind(name, ToolPayload.function("{}")))
        self.assertFalse(registry.matches_kind(name, ToolPayload.custom("raw")))
        self.assertIsNone(registry.supports_parallel_tool_calls(ToolName.plain("missing")))

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
        self.assertTrue(hidden.matches_kind(ToolPayload.function("{}")))

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


class ToolRegistryHookTests(unittest.TestCase):
    def test_flat_tool_name_concatenates_namespace_only_at_legacy_boundary(self) -> None:
        self.assertEqual(flat_tool_name(ToolName.plain("echo")), "echo")
        self.assertEqual(flat_tool_name(ToolName.namespaced("functions.", "echo")), "functions.echo")

    def test_function_tools_expose_default_hook_payloads_and_rewrites(self) -> None:
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

    def test_function_hook_input_defaults_empty_arguments_to_object(self) -> None:
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

    def test_function_hook_input_falls_back_to_string_for_invalid_json(self) -> None:
        self.assertEqual(function_hook_tool_input("{not json"), "{not json")

    def test_spawn_agent_function_tools_use_agent_matcher_alias(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
