import unittest

from pycodex.core import (
    FunctionToolOutput,
    McpToolOutput,
    McpHandler,
    PlannedTools,
    ToolExposure,
    ToolPayload,
    ToolPlanOptions,
    ToolInfo,
    add_mcp_tools,
    build_mcp_search_text,
    build_model_visible_specs_and_registry,
    create_mcp_tool_spec,
    mcp_tool_to_responses_api_tool,
)
from pycodex.protocol import CallToolResult, Tool, ToolName


def tool_info(
    *,
    connector_name: str | None = "Calendar",
    namespace_description: str | None = "Plan events.",
    supports_parallel: bool = False,
    annotations=None,
) -> ToolInfo:
    return ToolInfo(
        server_name="codex-apps",
        supports_parallel_tool_calls=supports_parallel,
        server_origin="plugin",
        callable_name="_create_event",
        callable_namespace="mcp__calendar__",
        namespace_description=namespace_description,
        tool=Tool(
            name="createEvent",
            title="Create event",
            description="Create a calendar event.",
            input_schema={
                "type": "object",
                "properties": {
                    "start_time": {"type": "string"},
                    "attendees": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            annotations=annotations,
        ),
        connector_name=connector_name,
        plugin_display_names=(" Calendar plugin ", " "),
    )


class McpToolHandlerTests(unittest.TestCase):
    def test_mcp_tool_to_responses_api_tool_renames_to_callable_name(self) -> None:
        info = tool_info()

        self.assertEqual(
            mcp_tool_to_responses_api_tool(info),
            {
                "type": "function",
                "name": "_create_event",
                "description": "Create a calendar event.",
                "strict": False,
                "parameters": info.tool.input_schema,
                "output_schema": {"type": "object"},
            },
        )

    def test_create_mcp_tool_spec_prefers_namespace_description(self) -> None:
        self.assertEqual(
            create_mcp_tool_spec(tool_info())["description"],
            "Plan events.",
        )

    def test_create_mcp_tool_spec_uses_connector_description_fallback(self) -> None:
        spec = create_mcp_tool_spec(tool_info(namespace_description=None))

        self.assertEqual(spec["description"], "Tools for working with Calendar.")
        self.assertEqual(spec["type"], "namespace")
        self.assertEqual(spec["name"], "mcp__calendar__")
        self.assertEqual(spec["tools"][0]["name"], "_create_event")

    def test_search_info_uses_mcp_metadata_and_parameter_names(self) -> None:
        handler = McpHandler.new(tool_info())
        search_info = handler.search_info()

        self.assertEqual(
            search_info.entry.search_text,
            "mcp__calendar___create_event _create_event createEvent codex-apps Create event Create a calendar event. Calendar Plan events. Calendar plugin attendees start_time",
        )
        self.assertEqual(search_info.source_info.name, "Calendar")
        self.assertEqual(search_info.source_info.description, "Plan events.")
        self.assertEqual(search_info.entry.output["description"], "Plan events.")

    def test_search_info_uses_connector_name_for_output_namespace_description(self) -> None:
        handler = McpHandler.new(tool_info(namespace_description=None))
        search_info = handler.search_info()

        self.assertEqual(
            search_info.entry.output["description"],
            "Tools for working with Calendar.",
        )
        self.assertEqual(search_info.source_info.name, "Calendar")
        self.assertIsNone(search_info.source_info.description)

    def test_build_mcp_search_text_uses_server_as_source_when_connector_blank(self) -> None:
        info = tool_info(connector_name=" ", namespace_description=" ")

        self.assertIn("codex-apps", build_mcp_search_text(info))
        self.assertEqual(McpHandler.new(info).search_info().source_info.name, "codex-apps")
        self.assertIsNone(McpHandler.new(info).search_info().source_info.description)

    def test_parallel_support_uses_server_opt_in_or_read_only_hint(self) -> None:
        self.assertFalse(McpHandler.new(tool_info()).supports_parallel_tool_calls())
        self.assertTrue(McpHandler.new(tool_info(supports_parallel=True)).supports_parallel_tool_calls())
        self.assertTrue(
            McpHandler.new(tool_info(annotations={"readOnlyHint": True})).supports_parallel_tool_calls()
        )
        self.assertFalse(
            McpHandler.new(tool_info(annotations={"readOnlyHint": False})).supports_parallel_tool_calls()
        )

    def test_handler_metadata_and_telemetry(self) -> None:
        handler = McpHandler.new(tool_info())

        self.assertEqual(handler.tool_name(), ToolName.namespaced("mcp__calendar__", "_create_event"))
        self.assertEqual(handler.exposure(), ToolExposure.DIRECT)
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(
            handler.telemetry_tags(),
            (("mcp_server", "codex-apps"), ("mcp_server_origin", "plugin")),
        )

    def test_handle_calls_request_callback(self) -> None:
        calls = []

        def callback(info, call_id, name, arguments):
            calls.append((info.server_name, call_id, name, arguments))
            return "created"

        handler = McpHandler.new(tool_info(), request_callback=callback)

        self.assertEqual(
            handler.handle(ToolPayload.function('{"summary":"meet"}')),
            FunctionToolOutput.from_text("created", True),
        )
        self.assertEqual(
            calls,
            [
                (
                    "codex-apps",
                    "",
                    ToolName.namespaced("mcp__calendar__", "_create_event"),
                    {"summary": "meet"},
                )
            ],
        )

    def test_handle_mapping_callback_returns_mcp_tool_output(self) -> None:
        handler = McpHandler.new(
            tool_info(),
            request_callback=lambda _info, _call_id, _name, _arguments: {
                "content": [{"type": "text", "text": "created"}],
                "isError": False,
            },
        )

        output = handler.handle(ToolPayload.function('{"summary":"meet"}'))

        self.assertIsInstance(output, McpToolOutput)
        self.assertEqual(
            output.result,
            CallToolResult(content=({"type": "text", "text": "created"},), is_error=False),
        )
        self.assertEqual(output.tool_input, {"summary": "meet"})

    def test_add_mcp_tools_connects_direct_and_deferred_tools_to_spec_plan(self) -> None:
        planned = PlannedTools()
        add_mcp_tools(
            planned,
            mcp_tools=[tool_info()],
            deferred_mcp_tools=[
                ToolInfo(
                    server_name="gmail",
                    callable_name="get_recent_emails",
                    callable_namespace="mcp__gmail__",
                    tool=Tool(
                        name="getRecentEmails",
                        description="Recent email",
                        input_schema={"type": "object", "properties": {}},
                    ),
                    connector_name="Gmail",
                )
            ],
        )

        specs, registry = build_model_visible_specs_and_registry(planned, ToolPlanOptions())

        self.assertEqual([spec["type"] for spec in specs], ["namespace", "tool_search"])
        self.assertIsNotNone(registry.tool(ToolName.namespaced("mcp__calendar__", "_create_event")))
        self.assertEqual(
            registry.tool_exposure(ToolName.namespaced("mcp__gmail__", "get_recent_emails")),
            ToolExposure.DEFERRED,
        )
        self.assertIsNotNone(registry.tool(ToolName.plain("tool_search")))


if __name__ == "__main__":
    unittest.main()
