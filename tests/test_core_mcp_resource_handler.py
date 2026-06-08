import json
import unittest

from pycodex.core.tools.handlers.mcp_resource import (
    InMemoryMcpResourceProvider,
    ListMcpResourceTemplatesHandler,
    ListMcpResourcesHandler,
    ListResourcesPayload,
    ReadMcpResourceHandler,
    ReadResourceResult,
    create_list_mcp_resource_templates_tool,
    create_list_mcp_resources_tool,
    create_read_mcp_resource_tool,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import Resource, ResourceContent, ResourceTemplate, SearchToolCallParams


class CoreMcpResourceHandlerTests(unittest.TestCase):
    def provider(self) -> InMemoryMcpResourceProvider:
        return InMemoryMcpResourceProvider(
            resources={
                "zeta": [Resource(name="Z", uri="file://z")],
                "alpha": [Resource(name="A", uri="file://a", mime_type="text/plain")],
            },
            templates={
                "alpha": [ResourceTemplate(uri_template="file:///{path}", name="files")],
            },
            contents={
                ("alpha", "file://a"): ReadResourceResult(
                    (ResourceContent.text_content("file://a", "hello", "text/plain"),)
                )
            },
        )

    def invocation(self, payload: ToolPayload, session: object) -> ToolInvocation:
        return ToolInvocation(
            call_id="call-1",
            tool_name="list_mcp_resources",
            payload=payload,
            session=session,
            turn="turn-1",
        )

    def test_specs_match_upstream_wire_names_and_required_fields(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/mcp_resource_spec.rs
        # Rust tests: mcp_resource_spec_tests.rs::{list_mcp_resources_tool_matches_expected_spec,
        # list_mcp_resource_templates_tool_matches_expected_spec, read_mcp_resource_tool_matches_expected_spec}
        resources_spec = create_list_mcp_resources_tool()
        self.assertEqual(resources_spec["type"], "function")
        self.assertEqual(resources_spec["name"], "list_mcp_resources")
        self.assertEqual(
            resources_spec["description"],
            "Lists resources provided by MCP servers. Resources allow servers to share data that provides context to language models, such as files, database schemas, or application-specific information. Prefer resources over web search when possible.",
        )
        self.assertFalse(resources_spec["strict"])
        self.assertIsNone(resources_spec.get("defer_loading"))
        self.assertIsNone(resources_spec.get("output_schema"))
        self.assertIsNone(resources_spec["parameters"].get("required"))
        self.assertFalse(resources_spec["parameters"]["additionalProperties"])
        self.assertEqual(
            resources_spec["parameters"]["properties"],
            {
                "server": {
                    "type": "string",
                    "description": "Optional MCP server name. When omitted, lists resources from every configured server.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque cursor returned by a previous list_mcp_resources call for the same server.",
                },
            },
        )

        templates_spec = create_list_mcp_resource_templates_tool()
        self.assertEqual(templates_spec["type"], "function")
        self.assertEqual(templates_spec["name"], "list_mcp_resource_templates")
        self.assertEqual(
            templates_spec["description"],
            "Lists resource templates provided by MCP servers. Parameterized resource templates allow servers to share data that takes parameters and provides context to language models, such as files, database schemas, or application-specific information. Prefer resource templates over web search when possible.",
        )
        self.assertFalse(templates_spec["strict"])
        self.assertIsNone(templates_spec.get("defer_loading"))
        self.assertIsNone(templates_spec.get("output_schema"))
        self.assertIsNone(templates_spec["parameters"].get("required"))
        self.assertFalse(templates_spec["parameters"]["additionalProperties"])
        self.assertEqual(
            templates_spec["parameters"]["properties"],
            {
                "server": {
                    "type": "string",
                    "description": "Optional MCP server name. When omitted, lists resource templates from all configured servers.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque cursor returned by a previous list_mcp_resource_templates call for the same server.",
                },
            },
        )

        read_spec = create_read_mcp_resource_tool()
        self.assertEqual(read_spec["type"], "function")
        self.assertEqual(read_spec["name"], "read_mcp_resource")
        self.assertEqual(
            read_spec["description"],
            "Read a specific resource from an MCP server given the server name and resource URI.",
        )
        self.assertFalse(read_spec["strict"])
        self.assertIsNone(read_spec.get("defer_loading"))
        self.assertIsNone(read_spec.get("output_schema"))
        self.assertEqual(read_spec["parameters"]["required"], ["server", "uri"])
        self.assertFalse(read_spec["parameters"]["additionalProperties"])
        self.assertEqual(
            read_spec["parameters"]["properties"],
            {
                "server": {
                    "type": "string",
                    "description": "MCP server name exactly as configured. Must match the 'server' field returned by list_mcp_resources.",
                },
                "uri": {
                    "type": "string",
                    "description": "Resource URI to read. Must be one of the URIs returned by list_mcp_resources.",
                },
            },
        )

    def test_list_all_resources_sorts_by_server_and_omits_cursor(self) -> None:
        output = ListMcpResourcesHandler(self.provider()).handle(ToolPayload.function("{}"))
        payload = json.loads(output.into_text())
        self.assertNotIn("server", payload)
        self.assertNotIn("nextCursor", payload)
        self.assertEqual(
            [(item["server"], item["uri"]) for item in payload["resources"]],
            [("alpha", "file://a"), ("zeta", "file://z")],
        )

    def test_list_single_server_includes_server_and_cursor(self) -> None:
        output = ListMcpResourcesHandler(self.provider()).handle(
            ToolPayload.function(json.dumps({"server": " alpha ", "cursor": " next "}))
        )
        payload = json.loads(output.into_text())
        self.assertEqual(payload["server"], "alpha")
        self.assertEqual(payload["nextCursor"], "next")
        self.assertEqual(payload["resources"][0]["server"], "alpha")

    def test_list_resources_emits_mcp_tool_call_turn_items(self) -> None:
        class Session:
            def __init__(self) -> None:
                self.started = []
                self.completed = []

            def emit_turn_item_started(self, turn, item):
                self.started.append((turn, item))

            def emit_turn_item_completed(self, turn, item):
                self.completed.append((turn, item))

        session = Session()
        output = ListMcpResourcesHandler(self.provider()).handle(
            self.invocation(
                ToolPayload.function(json.dumps({"server": "alpha"})),
                session,
            )
        )

        self.assertEqual(json.loads(output.into_text())["server"], "alpha")
        self.assertEqual(session.started[0][0], "turn-1")
        started = session.started[0][1].item
        self.assertEqual(started.status, "inProgress")
        self.assertEqual(started.server, "alpha")
        self.assertEqual(started.tool, "list_mcp_resources")
        completed = session.completed[0][1].item
        self.assertEqual(completed.status, "completed")
        self.assertFalse(completed.result.is_error)
        self.assertIn('"server":"alpha"', completed.result.content[0]["text"])

    def test_list_resources_emits_failed_mcp_tool_call_turn_item(self) -> None:
        class Session:
            def __init__(self) -> None:
                self.started = []
                self.completed = []

            def emit_turn_item_started(self, turn, item):
                self.started.append(item)

            def emit_turn_item_completed(self, turn, item):
                self.completed.append(item)

        session = Session()
        with self.assertRaisesRegex(FunctionCallError, "cursor can only be used"):
            ListMcpResourcesHandler(self.provider()).handle(
                self.invocation(
                    ToolPayload.function(json.dumps({"cursor": "next"})),
                    session,
                )
            )

        self.assertEqual(session.started[0].item.status, "inProgress")
        completed = session.completed[0].item
        self.assertEqual(completed.status, "failed")
        self.assertIn("cursor can only be used", completed.error.message)

    def test_cursor_without_server_is_rejected_for_resource_lists(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "cursor can only be used"):
            ListMcpResourcesHandler(self.provider()).handle(ToolPayload.function(json.dumps({"cursor": "next"})))
        with self.assertRaisesRegex(FunctionCallError, "cursor can only be used"):
            ListMcpResourceTemplatesHandler(self.provider()).handle(ToolPayload.function(json.dumps({"cursor": "next"})))

    def test_list_resource_templates_uses_camel_case_payload_key(self) -> None:
        output = ListMcpResourceTemplatesHandler(self.provider()).handle(
            ToolPayload.function(json.dumps({"server": "alpha"}))
        )
        payload = json.loads(output.into_text())
        self.assertEqual(payload["server"], "alpha")
        self.assertEqual(payload["resourceTemplates"][0]["uriTemplate"], "file:///{path}")

    def test_read_resource_normalizes_required_strings_and_flattens_result(self) -> None:
        output = ReadMcpResourceHandler(self.provider()).handle(
            ToolPayload.function(json.dumps({"server": " alpha ", "uri": " file://a "}))
        )
        payload = json.loads(output.into_text())
        self.assertEqual(payload["server"], "alpha")
        self.assertEqual(payload["uri"], "file://a")
        self.assertEqual(payload["contents"][0]["text"], "hello")

    def test_read_resource_rejects_blank_required_fields(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "server must be provided"):
            ReadMcpResourceHandler(self.provider()).handle(
                ToolPayload.function(json.dumps({"server": " ", "uri": "file://a"}))
            )

    def test_empty_function_arguments_default_only_for_list_handlers(self) -> None:
        output = ListMcpResourcesHandler(self.provider()).handle(ToolPayload.function(""))
        self.assertEqual(len(json.loads(output.into_text())["resources"]), 2)
        with self.assertRaisesRegex(FunctionCallError, "expected value"):
            ReadMcpResourceHandler(self.provider()).handle(ToolPayload.function(""))
        with self.assertRaisesRegex(FunctionCallError, "expected value"):
            ReadMcpResourceHandler(self.provider()).handle(ToolPayload.function("null"))
        with self.assertRaisesRegex(FunctionCallError, "expected object"):
            ReadMcpResourceHandler(self.provider()).handle(ToolPayload.function("[]"))

    def test_handlers_reject_non_function_payloads(self) -> None:
        self.assertTrue(
            ListMcpResourcesHandler(self.provider()).matches_kind(
                ToolPayload.tool_search(SearchToolCallParams("resources"))
            )
        )
        self.assertTrue(
            ListMcpResourceTemplatesHandler(self.provider()).matches_kind(
                ToolPayload.tool_search(SearchToolCallParams("templates"))
            )
        )
        self.assertTrue(
            ReadMcpResourceHandler(self.provider()).matches_kind(
                ToolPayload.tool_search(SearchToolCallParams("resource"))
            )
        )
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            ListMcpResourcesHandler(self.provider()).handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            ListMcpResourceTemplatesHandler(self.provider()).handle(ToolPayload.custom("raw"))
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            ReadMcpResourceHandler(self.provider()).handle(ToolPayload.custom("raw"))

    def test_all_server_payload_rejects_non_string_server_names(self) -> None:
        with self.assertRaisesRegex(TypeError, "server names must be strings"):
            ListResourcesPayload.from_all_servers({1: []})


if __name__ == "__main__":
    unittest.main()
