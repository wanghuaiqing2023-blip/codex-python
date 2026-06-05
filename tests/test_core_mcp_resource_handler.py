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

    def test_specs_match_upstream_wire_names_and_required_fields(self) -> None:
        self.assertEqual(create_list_mcp_resources_tool()["name"], "list_mcp_resources")
        self.assertEqual(create_list_mcp_resource_templates_tool()["name"], "list_mcp_resource_templates")
        read_spec = create_read_mcp_resource_tool()
        self.assertEqual(read_spec["name"], "read_mcp_resource")
        self.assertEqual(read_spec["parameters"]["required"], ["server", "uri"])

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
