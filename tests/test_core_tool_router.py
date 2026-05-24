import unittest

from pycodex.core import (
    RegisteredTool,
    ToolCall,
    ToolExposure,
    ToolPayload,
    ToolRegistry,
    ToolRouter,
    build_tool_call,
)
from pycodex.protocol import ResponseItem, SearchToolCallParams, ToolName


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
        with self.assertRaisesRegex(ValueError, "failed to parse tool_search arguments"):
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

    def test_router_preserves_model_visible_specs(self) -> None:
        specs = ({"type": "function", "name": "echo"},)
        self.assertEqual(ToolRouter.from_parts(specs).model_visible_specs(), specs)

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


if __name__ == "__main__":
    unittest.main()
