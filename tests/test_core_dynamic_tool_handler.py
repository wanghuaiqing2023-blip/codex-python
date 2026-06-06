import unittest

from pycodex.core import (
    DynamicToolHandler,
    FunctionToolOutput,
    FunctionCallError,
    PlannedTools,
    ToolExposure,
    ToolPayload,
    ToolPlanOptions,
    add_dynamic_tools,
    build_dynamic_search_text,
    build_model_visible_specs_and_registry,
    dynamic_tool_call_request_event,
    dynamic_tool_call_response_event,
    dynamic_tool_to_responses_api_tool,
)
from pycodex.protocol import (
    DynamicToolCallOutputContentItem,
    DynamicToolResponse,
    DynamicToolSpec,
    FunctionCallOutputContentItem,
    SearchToolCallParams,
    ToolName,
)


class Invocation:
    def __init__(self, call_id: str, payload: ToolPayload) -> None:
        self.call_id = call_id
        self.payload = payload


def dynamic_spec(*, defer_loading: bool = True, namespace: str | None = "codex_app") -> DynamicToolSpec:
    return DynamicToolSpec(
        namespace=namespace,
        name="automation_update",
        description="Create or update automations.",
        input_schema={
            "type": "object",
            "properties": {
                "timezone": {"type": "string"},
                "mode": {"type": "string"},
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
        defer_loading=defer_loading,
    )


class DynamicToolHandlerTests(unittest.TestCase):
    def test_dynamic_tool_to_responses_api_tool_preserves_schema_and_defer_loading(self) -> None:
        tool = dynamic_spec(defer_loading=True, namespace=None)

        self.assertEqual(
            dynamic_tool_to_responses_api_tool(tool),
            {
                "type": "function",
                "name": "automation_update",
                "description": "Create or update automations.",
                "strict": False,
                "defer_loading": True,
                "parameters": tool.input_schema,
            },
        )

    def test_handler_uses_namespace_exposure_and_search_metadata(self) -> None:
        # Rust parity: codex-core::tools::handlers::dynamic
        # dynamic_tests.rs::search_info_uses_dynamic_tool_metadata_and_parameter_names.
        handler = DynamicToolHandler.new(dynamic_spec())

        self.assertIsNotNone(handler)
        self.assertEqual(handler.tool_name(), ToolName.namespaced("codex_app", "automation_update"))
        self.assertEqual(handler.exposure(), ToolExposure.DEFERRED)
        self.assertFalse(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertTrue(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("automation"))))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(
            handler.spec(),
            {
                "type": "namespace",
                "name": "codex_app",
                "description": "Tools in the codex_app namespace.",
                "tools": [
                    {
                        "type": "function",
                        "name": "automation_update",
                        "description": "Create or update automations.",
                        "strict": False,
                        "defer_loading": True,
                        "parameters": dynamic_spec().input_schema,
                    }
                ],
            },
        )

        search_info = handler.search_info()
        self.assertEqual(
            search_info.entry.search_text,
            "automation_update automation update Create or update automations. codex_app mode timezone",
        )
        self.assertEqual(search_info.source_info.name, "Dynamic tools")
        self.assertEqual(
            search_info.source_info.description,
            "Tools provided by the current Codex thread.",
        )

    def test_direct_dynamic_tools_are_model_visible_without_tool_search(self) -> None:
        handler = DynamicToolHandler.new(dynamic_spec(defer_loading=False, namespace=None))

        self.assertEqual(handler.exposure(), ToolExposure.DIRECT)
        self.assertEqual(handler.tool_name(), ToolName.plain("automation_update"))
        self.assertEqual(handler.spec()["type"], "function")

    def test_build_dynamic_search_text_handles_missing_schema_properties(self) -> None:
        tool = DynamicToolSpec(
            name="lookup_order",
            description="Look up orders.",
            input_schema={"type": "object"},
            namespace=None,
            defer_loading=True,
        )

        self.assertEqual(
            build_dynamic_search_text(tool),
            "lookup_order lookup order Look up orders.",
        )

    def test_new_returns_none_for_invalid_input_schema(self) -> None:
        self.assertIsNone(
            DynamicToolHandler.new(
                DynamicToolSpec(
                    name="bad",
                    description="Bad schema",
                    input_schema="not a mapping",
                    namespace=None,
                    defer_loading=False,
                )
            )
        )

    def test_handle_calls_request_callback_and_returns_function_output(self) -> None:
        calls = []

        def callback(call_id, tool_name, arguments):
            calls.append((call_id, tool_name, arguments))
            return DynamicToolResponse(
                (
                    DynamicToolCallOutputContentItem.input_text("done"),
                    DynamicToolCallOutputContentItem.input_image("data:image/png;base64,abc"),
                ),
                True,
            )

        handler = DynamicToolHandler.new(dynamic_spec(namespace=None), request_callback=callback)

        output = handler.handle(
            Invocation("call-dynamic", ToolPayload.function('{"mode":"create"}'))
        )

        self.assertEqual(
            calls,
            [("call-dynamic", ToolName.plain("automation_update"), {"mode": "create"})],
        )
        self.assertEqual(
            output,
            FunctionToolOutput.from_content(
                (
                    FunctionCallOutputContentItem.input_text("done"),
                    FunctionCallOutputContentItem.input_image("data:image/png;base64,abc"),
                ),
                True,
            ),
        )

    def test_handle_accepts_mapping_response_and_rejects_bad_payloads(self) -> None:
        handler = DynamicToolHandler.new(
            dynamic_spec(namespace=None),
            request_callback=lambda _call_id, _tool_name, _arguments: {
                "contentItems": [{"type": "inputText", "text": "ok"}],
                "success": False,
            },
        )

        self.assertFalse(handler.handle(ToolPayload.function("{}")).success_for_logging())
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            handler.handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(FunctionCallError, "failed to parse function arguments"):
            handler.handle(ToolPayload.function("{not json"))
        with self.assertRaisesRegex(FunctionCallError, "cancelled before receiving a response"):
            DynamicToolHandler.new(dynamic_spec(namespace=None)).handle(ToolPayload.function("{}"))

    def test_dynamic_tool_call_request_event_uses_tool_name_parts(self) -> None:
        event = dynamic_tool_call_request_event(
            "call-dynamic",
            "turn-1",
            ToolName.namespaced("codex_app", "automation_update"),
            {"mode": "create"},
            started_at_ms=123,
        )

        self.assertEqual(
            event.to_mapping(),
            {
                "callId": "call-dynamic",
                "turnId": "turn-1",
                "startedAtMs": 123,
                "namespace": "codex_app",
                "tool": "automation_update",
                "arguments": {"mode": "create"},
            },
        )

    def test_dynamic_tool_call_response_event_success_and_cancelled_shapes(self) -> None:
        response = DynamicToolResponse(
            (DynamicToolCallOutputContentItem.input_text("done"),),
            True,
        )
        success = dynamic_tool_call_response_event(
            "call-dynamic",
            "turn-1",
            ToolName.namespaced("codex_app", "automation_update"),
            {"mode": "create"},
            response,
            completed_at_ms=456,
            duration={"secs": 0, "nanos": 5},
        )
        cancelled = dynamic_tool_call_response_event(
            "call-dynamic",
            "turn-1",
            ToolName.plain("automation_update"),
            {},
            None,
        )

        self.assertEqual(success.to_mapping()["content_items"], [{"type": "inputText", "text": "done"}])
        self.assertTrue(success.success)
        self.assertIsNone(success.error)
        self.assertFalse(cancelled.success)
        self.assertEqual(cancelled.error, "dynamic tool call was cancelled before receiving a response")
        self.assertEqual(cancelled.content_items, ())

    def test_add_dynamic_tools_connects_to_spec_plan_and_tool_search(self) -> None:
        planned = PlannedTools()
        add_dynamic_tools(planned, [dynamic_spec(defer_loading=True)])

        specs, registry = build_model_visible_specs_and_registry(planned, ToolPlanOptions())

        self.assertEqual([spec["type"] for spec in specs], ["tool_search"])
        self.assertIsNotNone(registry.tool(ToolName.namespaced("codex_app", "automation_update")))
        self.assertIsNotNone(registry.tool(ToolName.plain("tool_search")))


if __name__ == "__main__":
    unittest.main()
