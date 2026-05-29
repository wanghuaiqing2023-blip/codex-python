import unittest

from pycodex.core import (
    FunctionCallError,
    FunctionToolOutput,
    HookToolName,
    McpToolOutput,
    McpHandler,
    PlannedTools,
    ToolExposure,
    ToolInvocation,
    ToolPayload,
    ToolPlanOptions,
    ToolInfo,
    add_mcp_tools,
    build_mcp_search_text,
    build_model_visible_specs_and_registry,
    create_mcp_tool_spec,
    ensure_mcp_prefix,
    join_tool_name,
    mcp_hook_tool_input,
    mcp_tool_to_responses_api_tool,
)
from pycodex.protocol import CallToolResult, SearchToolCallParams, Tool, ToolName, TruncationPolicyConfig


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
        self.assertEqual(handler.hook_tool_name(), HookToolName.new("mcp__calendar__create_event"))
        self.assertEqual(handler.exposure(), ToolExposure.DIRECT)
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertTrue(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("calendar"))))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertEqual(
            handler.telemetry_tags(),
            (("mcp_server", "codex-apps"), ("mcp_server_origin", "plugin")),
        )

    def test_mcp_hook_name_helpers_match_rust_prefix_rules(self) -> None:
        self.assertEqual(join_tool_name(ToolName.namespaced("memory", "create_entities")), "memory__create_entities")
        self.assertEqual(join_tool_name(ToolName.namespaced("mcp__foo__", "_exec_command")), "mcp__foo__exec_command")
        self.assertEqual(ensure_mcp_prefix("memory__create_entities"), "mcp__memory__create_entities")
        self.assertEqual(ensure_mcp_prefix("mcp__foo__exec_command"), "mcp__foo__exec_command")

    def test_mcp_hook_tool_input_parses_json_or_preserves_raw_string(self) -> None:
        self.assertEqual(mcp_hook_tool_input(""), {})
        self.assertEqual(mcp_hook_tool_input('{"path":"/tmp"}'), {"path": "/tmp"})
        self.assertEqual(mcp_hook_tool_input("{not json"), "{not json")

    def test_pre_tool_use_payload_uses_prefixed_name_and_args(self) -> None:
        handler = McpHandler.new(tool_info())
        invocation = ToolInvocation(
            call_id="call-mcp-pre",
            tool_name=handler.tool_name(),
            payload=ToolPayload.function('{"summary":"meet"}'),
        )

        payload = handler.pre_tool_use_payload(invocation)

        self.assertEqual(payload.tool_name, HookToolName.new("mcp__calendar__create_event"))
        self.assertEqual(payload.tool_input, {"summary": "meet"})

    def test_with_updated_hook_input_rewrites_function_arguments(self) -> None:
        handler = McpHandler.new(tool_info())
        invocation = ToolInvocation(
            call_id="call-mcp-rewrite",
            tool_name=handler.tool_name(),
            payload=ToolPayload.function('{"summary":"meet"}'),
        )

        updated = handler.with_updated_hook_input(invocation, {"summary": "rewritten"})

        self.assertEqual(updated.payload, ToolPayload.function('{"summary":"rewritten"}'))

    def test_with_updated_hook_input_uses_model_visible_errors(self) -> None:
        handler = McpHandler.new(tool_info())
        with self.assertRaisesRegex(FunctionCallError, "does not support hook input rewriting") as unsupported:
            handler.with_updated_hook_input(
                ToolInvocation(
                    call_id="call-mcp-rewrite",
                    tool_name=handler.tool_name(),
                    payload=ToolPayload.custom("raw"),
                ),
                {"summary": "rewritten"},
            )
        self.assertTrue(unsupported.exception.is_model_response)

        with self.assertRaisesRegex(FunctionCallError, "failed to serialize rewritten MCP arguments") as unserializable:
            handler.with_updated_hook_input(
                ToolInvocation(
                    call_id="call-mcp-rewrite",
                    tool_name=handler.tool_name(),
                    payload=ToolPayload.function("{}"),
                ),
                {"bad": object()},
            )
        self.assertTrue(unserializable.exception.is_model_response)

    def test_post_tool_use_payload_uses_mcp_output_input_and_result(self) -> None:
        handler = McpHandler.new(tool_info())
        invocation = ToolInvocation(
            call_id="call-mcp-post",
            tool_name=handler.tool_name(),
            payload=ToolPayload.function('{"summary":"meet"}'),
        )
        output = McpToolOutput(
            result=CallToolResult(
                content=({"type": "text", "text": "created"},),
                structured_content={"event_id": "evt_1"},
            ),
            tool_input={"summary": "meet", "calendar_id": "cal_1"},
            wall_time_seconds=0.042,
            original_image_detail_supported=True,
            truncation_policy=TruncationPolicyConfig.tokens(10_000),
        )

        payload = handler.post_tool_use_payload(invocation, output)

        self.assertEqual(payload.tool_name, HookToolName.new("mcp__calendar__create_event"))
        self.assertEqual(payload.tool_use_id, "call-mcp-post")
        self.assertEqual(payload.tool_input, {"summary": "meet", "calendar_id": "cal_1"})
        self.assertEqual(
            payload.tool_response,
            {
                "content": [{"type": "text", "text": "created"}],
                "structuredContent": {"event_id": "evt_1"},
            },
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

    def test_handle_uses_model_visible_errors(self) -> None:
        handler = McpHandler.new(tool_info())

        with self.assertRaisesRegex(FunctionCallError, "unsupported payload") as unsupported:
            handler.handle(ToolPayload.custom("raw"))
        self.assertTrue(unsupported.exception.is_model_response)

        with self.assertRaisesRegex(FunctionCallError, "failed to parse function arguments") as bad_json:
            handler.handle(ToolPayload.function("{not json"))
        self.assertTrue(bad_json.exception.is_model_response)

        with self.assertRaisesRegex(FunctionCallError, "requires a request callback") as no_callback:
            handler.handle(ToolPayload.function("{}"))
        self.assertTrue(no_callback.exception.is_model_response)

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
