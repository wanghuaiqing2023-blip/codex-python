import unittest

from pycodex.protocol import (
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_MCP_TOOL_CALL,
    CallToolResult,
    DynamicToolCallOutputContentItem,
    DynamicToolCallRequest,
    DynamicToolResponse,
    DynamicToolSpec,
    ElicitationRequest,
    ElicitationRequestEvent,
    RequestId,
    Resource,
    ResourceContent,
    ResourceTemplate,
    Tool,
)


class ProtocolMcpDynamicToolsTests(unittest.TestCase):
    def test_request_id_accepts_string_or_integer(self):
        self.assertEqual(str(RequestId.string("abc")), "abc")
        self.assertEqual(str(RequestId.integer(42)), "42")
        self.assertEqual(RequestId.from_value(RequestId.integer(5)).to_json(), 5)

        with self.assertRaises(TypeError):
            RequestId.from_value(True)

    def test_elicitation_request_event_wraps_request_id(self):
        event = ElicitationRequestEvent("server", 7, ElicitationRequest.form("fill", {"type": "object"}))

        self.assertEqual(event.id, RequestId.integer(7))

    def test_tool_from_mcp_value_accepts_schema_aliases(self):
        tool = Tool.from_mcp_value(
            {
                "name": "lookup",
                "title": "Lookup",
                "description": "Fetch a record",
                "input_schema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "icons": [{"src": "icon.png"}],
                "_meta": {"server": "demo"},
            }
        )

        self.assertEqual(tool.input_schema, {"type": "object"})
        self.assertEqual(tool.output_schema, {"type": "object"})
        self.assertEqual(tool.icons, ({"src": "icon.png"},))
        self.assertEqual(
            tool.to_mapping(),
            {
                "name": "lookup",
                "inputSchema": {"type": "object"},
                "title": "Lookup",
                "description": "Fetch a record",
                "outputSchema": {"type": "object"},
                "icons": [{"src": "icon.png"}],
                "_meta": {"server": "demo"},
            },
        )

    def test_resource_size_deserializes_lossily_like_upstream(self):
        self.assertEqual(Resource.from_mcp_value({"name": "big", "uri": "file:///tmp/big", "size": 5_000_000_000}).size, 5_000_000_000)
        self.assertEqual(Resource.from_mcp_value({"name": "negative", "uri": "file:///tmp/negative", "size": -1}).size, -1)
        self.assertIsNone(
            Resource.from_mcp_value(
                {
                    "name": "too_big_for_i64",
                    "uri": "file:///tmp/too_big_for_i64",
                    "size": 18_446_744_073_709_551_615,
                }
            ).size
        )
        self.assertIsNone(Resource.from_mcp_value({"name": "float", "uri": "file:///tmp/float", "size": 1.2}).size)

    def test_resource_and_template_aliases_serialize_to_camel_case(self):
        resource = Resource.from_mcp_value(
            {
                "name": "doc",
                "uri": "file:///tmp/doc",
                "mime_type": "text/plain",
                "title": "Doc",
                "_meta": {"id": 1},
            }
        )
        template = ResourceTemplate.from_mcp_value(
            {
                "uri_template": "file:///{path}",
                "name": "files",
                "mime_type": "text/plain",
            }
        )

        self.assertEqual(resource.mime_type, "text/plain")
        self.assertEqual(resource.to_mapping()["mimeType"], "text/plain")
        self.assertEqual(template.uri_template, "file:///{path}")
        self.assertEqual(template.to_mapping()["uriTemplate"], "file:///{path}")

    def test_resource_content_text_and_blob_variants(self):
        text = ResourceContent.from_mcp_value({"uri": "file:///a", "mimeType": "text/plain", "text": "hello"})
        blob = ResourceContent.from_mcp_value({"uri": "file:///b", "blob": "YmFzZTY0", "_meta": {"x": 1}})

        self.assertEqual(text, ResourceContent.text_content("file:///a", "hello", mime_type="text/plain"))
        self.assertEqual(blob.to_mapping(), {"uri": "file:///b", "blob": "YmFzZTY0", "_meta": {"x": 1}})

    def test_call_tool_result_serializes_optional_fields(self):
        result = CallToolResult.from_mapping(
            {
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {"ok": True},
                "isError": False,
                "_meta": {"trace": "1"},
            }
        )

        self.assertEqual(result.content, ({"type": "text", "text": "ok"},))
        self.assertEqual(result.to_mapping()["structuredContent"], {"ok": True})
        self.assertFalse(result.to_mapping()["isError"])

    def test_dynamic_tool_spec_deserializes_defer_loading(self):
        spec = DynamicToolSpec.from_mapping(
            {
                "name": "lookup_ticket",
                "description": "Fetch a ticket",
                "inputSchema": {"type": "object"},
                "deferLoading": True,
            }
        )

        self.assertEqual(
            spec,
            DynamicToolSpec(
                namespace=None,
                name="lookup_ticket",
                description="Fetch a ticket",
                input_schema={"type": "object"},
                defer_loading=True,
            ),
        )
        self.assertEqual(
            spec.to_mapping(),
            {
                "name": "lookup_ticket",
                "description": "Fetch a ticket",
                "inputSchema": {"type": "object"},
                "deferLoading": True,
            },
        )

    def test_dynamic_tool_spec_legacy_expose_to_context_inverts_to_defer_loading(self):
        spec = DynamicToolSpec.from_mapping(
            {
                "name": "lookup_ticket",
                "description": "Fetch a ticket",
                "inputSchema": {"type": "object", "properties": {}},
                "exposeToContext": False,
            }
        )

        self.assertTrue(spec.defer_loading)

    def test_dynamic_tool_call_request_defaults_and_serialization(self):
        request = DynamicToolCallRequest.from_mapping(
            {
                "callId": "call-1",
                "turnId": "turn-1",
                "tool": "lookup",
                "arguments": {"id": "T1"},
            }
        )

        self.assertEqual(request.started_at_ms, 0)
        self.assertEqual(
            request.to_mapping(),
            {
                "callId": "call-1",
                "turnId": "turn-1",
                "startedAtMs": 0,
                "namespace": None,
                "tool": "lookup",
                "arguments": {"id": "T1"},
            },
        )

    def test_dynamic_tool_response_content_items_use_camel_case_tags(self):
        response = DynamicToolResponse.from_mapping(
            {
                "contentItems": [
                    {"type": "inputText", "text": "hello"},
                    {"type": "inputImage", "imageUrl": "data:image/png;base64,abc"},
                ],
                "success": True,
            }
        )

        self.assertEqual(
            response.content_items,
            (
                DynamicToolCallOutputContentItem.input_text("hello"),
                DynamicToolCallOutputContentItem.input_image("data:image/png;base64,abc"),
            ),
        )
        self.assertEqual(response.to_mapping()["contentItems"][1]["imageUrl"], "data:image/png;base64,abc")

    def test_mcp_approval_meta_constants_match_upstream(self):
        self.assertEqual(APPROVAL_KIND_KEY, "codex_approval_kind")
        self.assertEqual(APPROVAL_KIND_MCP_TOOL_CALL, "mcp_tool_call")


if __name__ == "__main__":
    unittest.main()
