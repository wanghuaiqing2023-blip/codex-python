import unittest

import pycodex.protocol as protocol
from pycodex.protocol import (
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_MCP_TOOL_CALL,
    APPROVAL_KIND_TOOL_SUGGESTION,
    APPROVALS_REVIEWER_KEY,
    CallToolResult,
    CONNECTOR_DESCRIPTION_KEY,
    CONNECTOR_ID_KEY,
    CONNECTOR_NAME_KEY,
    DynamicToolCallOutputContentItem,
    DynamicToolCallRequest,
    DynamicToolResponse,
    DynamicToolSpec,
    ElicitationRequest,
    ElicitationRequestEvent,
    PERSIST_ALWAYS,
    PERSIST_KEY,
    PERSIST_SESSION,
    REQUEST_TYPE_APPROVAL_REQUEST,
    REQUEST_TYPE_KEY,
    RequestId,
    Resource,
    ResourceContent,
    ResourceTemplate,
    SOURCE_CONNECTOR,
    SOURCE_KEY,
    Tool,
    TOOL_DESCRIPTION_KEY,
    TOOL_NAME_KEY,
    TOOL_PARAMS_DISPLAY_KEY,
    TOOL_PARAMS_KEY,
    TOOL_TITLE_KEY,
)


class ProtocolMcpDynamicToolsTests(unittest.TestCase):
    def test_request_id_accepts_string_or_integer(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # RequestId is an untagged string-or-i64 enum whose Display prints the
        # raw string or integer value.
        self.assertEqual(str(RequestId.string("abc")), "abc")
        self.assertEqual(str(RequestId.integer(42)), "42")
        self.assertEqual(RequestId.from_value(RequestId.integer(5)).to_json(), 5)
        self.assertEqual(RequestId.integer(2**63 - 1).to_json(), 2**63 - 1)
        self.assertEqual(RequestId.integer(-(2**63)).to_json(), -(2**63))

        with self.assertRaises(TypeError):
            RequestId.from_value(True)
        with self.assertRaisesRegex(ValueError, "request id must fit in i64"):
            RequestId.integer(2**63)
        with self.assertRaisesRegex(ValueError, "request id must fit in i64"):
            RequestId.integer(-(2**63) - 1)

    def test_elicitation_request_event_wraps_request_id(self):
        event = ElicitationRequestEvent("server", 7, ElicitationRequest.form("fill", {"type": "object"}))

        self.assertEqual(event.id, RequestId.integer(7))

    def test_mcp_values_reject_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "name must be a string"):
            Tool(name=123, input_schema={})  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "icons must be a list"):
            Tool(name="lookup", input_schema={}, icons=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "uri must be a string"):
            Resource(name="doc", uri=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "size must fit in i64"):
            Resource(name="doc", uri="file:///doc", size=2**63)
        with self.assertRaisesRegex(TypeError, "mimeType must be a string"):
            Resource.from_mcp_value({"name": "doc", "uri": "file:///doc", "mimeType": 1})
        with self.assertRaisesRegex(TypeError, "mimeType must be a string"):
            ResourceContent.from_mcp_value({"uri": "file:///doc", "mimeType": 1, "text": "hello"})
        with self.assertRaisesRegex(TypeError, "uri_template must be a string"):
            ResourceTemplate(uri_template=123, name="files")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "mimeType must be a string"):
            ResourceTemplate.from_mcp_value({"uriTemplate": "file:///{path}", "name": "files", "mimeType": 1})
        with self.assertRaisesRegex(TypeError, "content must be a list"):
            CallToolResult(content="not-a-list")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "is_error must be a bool"):
            CallToolResult(content=(), is_error=1)  # type: ignore[arg-type]

    def test_tool_from_mcp_value_accepts_schema_aliases(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # Tool::from_mcp_value accepts MCP JSON using both camelCase wire
        # fields and snake_case aliases, then serializes protocol output with
        # camelCase and `_meta`.
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
        primary = Tool.from_mcp_value({"name": "primary", "inputSchema": {"type": "object"}})

        self.assertEqual(tool.input_schema, {"type": "object"})
        self.assertEqual(tool.output_schema, {"type": "object"})
        self.assertEqual(tool.icons, ({"src": "icon.png"},))
        self.assertEqual(primary.input_schema, {"type": "object"})
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
        # Rust parity: codex-protocol/src/mcp.rs
        # resource_size_deserializes_without_narrowing.
        self.assertEqual(Resource.from_mcp_value({"name": "big", "uri": "file:///tmp/big", "size": 5_000_000_000}).size, 5_000_000_000)
        self.assertEqual(Resource.from_mcp_value({"name": "negative", "uri": "file:///tmp/negative", "size": -1}).size, -1)
        self.assertEqual(Resource.from_mcp_value({"name": "max", "uri": "file:///tmp/max", "size": 2**63 - 1}).size, 2**63 - 1)
        self.assertEqual(Resource.from_mcp_value({"name": "min", "uri": "file:///tmp/min", "size": -(2**63)}).size, -(2**63))
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

    def test_resource_template_adapter_aliases_serialize_to_camel_case(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # ResourceTemplate::from_mcp_value accepts camelCase wire fields and
        # snake_case aliases, then serializes protocol output with camelCase.
        primary = ResourceTemplate.from_mcp_value(
            {
                "uriTemplate": "file:///{path}",
                "name": "files",
                "mimeType": "text/plain",
            }
        )
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

        self.assertEqual(primary.uri_template, "file:///{path}")
        self.assertEqual(primary.mime_type, "text/plain")
        self.assertEqual(template.uri_template, "file:///{path}")
        self.assertEqual(template.mime_type, "text/plain")
        self.assertEqual(
            template.to_mapping(),
            {
                "uriTemplate": "file:///{path}",
                "name": "files",
                "mimeType": "text/plain",
            },
        )

    def test_resource_adapter_aliases_serialize_to_camel_case(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # Resource::from_mcp_value accepts camelCase wire fields and
        # snake_case aliases, then serializes protocol output with camelCase
        # and `_meta`.
        primary = Resource.from_mcp_value(
            {
                "name": "primary-doc",
                "uri": "file:///tmp/primary",
                "mimeType": "text/markdown",
            }
        )
        resource = Resource.from_mcp_value(
            {
                "name": "doc",
                "uri": "file:///tmp/doc",
                "mime_type": "text/plain",
                "title": "Doc",
                "_meta": {"id": 1},
            }
        )

        self.assertEqual(primary.mime_type, "text/markdown")
        self.assertEqual(resource.mime_type, "text/plain")
        self.assertEqual(resource.to_mapping()["mimeType"], "text/plain")
        self.assertEqual(
            resource.to_mapping(),
            {
                "name": "doc",
                "uri": "file:///tmp/doc",
                "mimeType": "text/plain",
                "title": "Doc",
                "_meta": {"id": 1},
            },
        )

    def test_resource_content_text_and_blob_variants(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # ResourceContent is an untagged enum with text and blob variants,
        # camelCase `mimeType`, snake_case `mime_type` adapter input, and
        # optional `_meta`.
        text = ResourceContent.from_mcp_value({"uri": "file:///a", "mimeType": "text/plain", "text": "hello"})
        blob = ResourceContent.from_mcp_value({"uri": "file:///b", "mime_type": "application/octet-stream", "blob": "YmFzZTY0", "_meta": {"x": 1}})

        self.assertEqual(text, ResourceContent.text_content("file:///a", "hello", mime_type="text/plain"))
        self.assertEqual(text.to_mapping(), {"uri": "file:///a", "mimeType": "text/plain", "text": "hello"})
        self.assertEqual(
            blob.to_mapping(),
            {
                "uri": "file:///b",
                "mimeType": "application/octet-stream",
                "blob": "YmFzZTY0",
                "_meta": {"x": 1},
            },
        )

    def test_call_tool_result_serializes_optional_fields(self):
        # Rust parity: codex-protocol/src/mcp.rs
        # CallToolResult serializes camelCase `structuredContent`/`isError`,
        # preserves optional `_meta`, and requires content to be an array.
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
        self.assertEqual(result.to_mapping()["_meta"], {"trace": "1"})

        snake_alias = CallToolResult.from_mapping(
            {
                "content": [],
                "structured_content": {"ok": True},
                "is_error": True,
            }
        )
        self.assertEqual(
            snake_alias.to_mapping(),
            {
                "content": [],
                "structuredContent": {"ok": True},
                "isError": True,
            },
        )

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

    def test_dynamic_tool_spec_defaults_and_prefers_explicit_defer_loading(self):
        # Rust: codex-protocol/src/dynamic_tools.rs
        # Behavior: deferLoading defaults false, and explicit deferLoading wins
        # over legacy exposeToContext when both fields are present.
        self.assertFalse(
            DynamicToolSpec.from_mapping(
                {
                    "name": "lookup_ticket",
                    "description": "Fetch a ticket",
                    "inputSchema": {"type": "object"},
                }
            ).defer_loading
        )
        self.assertFalse(
            DynamicToolSpec.from_mapping(
                {
                    "name": "lookup_ticket",
                    "description": "Fetch a ticket",
                    "inputSchema": {"type": "object"},
                    "exposeToContext": True,
                }
            ).defer_loading
        )
        self.assertFalse(
            DynamicToolSpec.from_mapping(
                {
                    "name": "lookup_ticket",
                    "description": "Fetch a ticket",
                    "inputSchema": {"type": "object"},
                    "deferLoading": False,
                    "exposeToContext": False,
                }
            ).defer_loading
        )

    def test_dynamic_tool_spec_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "name must be a string"):
            DynamicToolSpec(name=123, description="Fetch", input_schema={})

        with self.assertRaisesRegex(TypeError, "description must be a string"):
            DynamicToolSpec(name="lookup", description=123, input_schema={})

        with self.assertRaisesRegex(TypeError, "namespace must be a string or None"):
            DynamicToolSpec(name="lookup", description="Fetch", input_schema={}, namespace=123)

        with self.assertRaisesRegex(TypeError, "defer_loading must be a bool"):
            DynamicToolSpec(name="lookup", description="Fetch", input_schema={}, defer_loading=1)

    def test_dynamic_tool_call_request_defaults_and_serialization(self):
        request = DynamicToolCallRequest.from_mapping(
            {
                "callId": "call-1",
                "turnId": "turn-1",
                "tool": "lookup",
                "arguments": {"id": "T1"},
            }
        )
        timed_request = DynamicToolCallRequest.from_mapping(
            {
                "callId": "call-2",
                "turnId": "turn-2",
                "startedAtMs": -(2**63),
                "namespace": "connector",
                "tool": "lookup",
                "arguments": {"id": "T2"},
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
        self.assertEqual(timed_request.started_at_ms, -(2**63))
        self.assertEqual(timed_request.namespace, "connector")

    def test_dynamic_tool_call_request_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "call_id must be a string"):
            DynamicToolCallRequest(123, "turn-1", "lookup", {})

        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            DynamicToolCallRequest("call-1", 123, "lookup", {})

        with self.assertRaisesRegex(TypeError, "tool must be a string"):
            DynamicToolCallRequest("call-1", "turn-1", 123, {})

        with self.assertRaisesRegex(TypeError, "namespace must be a string or None"):
            DynamicToolCallRequest("call-1", "turn-1", "lookup", {}, namespace=123)

        with self.assertRaisesRegex(TypeError, "started_at_ms must be an integer"):
            DynamicToolCallRequest("call-1", "turn-1", "lookup", {}, started_at_ms=True)

        with self.assertRaisesRegex(ValueError, "started_at_ms must fit in i64"):
            DynamicToolCallRequest("call-1", "turn-1", "lookup", {}, started_at_ms=2**63)

        with self.assertRaisesRegex(ValueError, "startedAtMs must fit in i64"):
            DynamicToolCallRequest.from_mapping(
                {
                    "callId": "call-1",
                    "turnId": "turn-1",
                    "tool": "lookup",
                    "arguments": {},
                    "startedAtMs": 2**63,
                }
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
        self.assertEqual(
            response.to_mapping(),
            {
                "contentItems": [
                    {"type": "inputText", "text": "hello"},
                    {"type": "inputImage", "imageUrl": "data:image/png;base64,abc"},
                ],
                "success": True,
            },
        )

    def test_dynamic_tool_response_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "inputText item requires text"):
            DynamicToolCallOutputContentItem.input_text(123)

        with self.assertRaisesRegex(ValueError, "inputText item cannot include image_url"):
            DynamicToolCallOutputContentItem("inputText", text="hello", image_url="data:image/png;base64,abc")

        with self.assertRaisesRegex(TypeError, "inputImage item requires image_url"):
            DynamicToolCallOutputContentItem.input_image(123)

        with self.assertRaisesRegex(ValueError, "inputImage item cannot include text"):
            DynamicToolCallOutputContentItem("inputImage", text="hello", image_url="data:image/png;base64,abc")

        with self.assertRaisesRegex(TypeError, "content_items entries must be DynamicToolCallOutputContentItem"):
            DynamicToolResponse(({"type": "inputText", "text": "hello"},), True)

        with self.assertRaisesRegex(TypeError, "success must be a bool"):
            DynamicToolResponse((DynamicToolCallOutputContentItem.input_text("hello"),), 1)

    def test_mcp_approval_meta_constants_match_upstream(self):
        # Rust: codex-protocol/src/mcp_approval_meta.rs
        expected = {
            "APPROVAL_KIND_KEY": "codex_approval_kind",
            "APPROVAL_KIND_MCP_TOOL_CALL": "mcp_tool_call",
            "APPROVAL_KIND_TOOL_SUGGESTION": "tool_suggestion",
            "REQUEST_TYPE_KEY": "codex_request_type",
            "REQUEST_TYPE_APPROVAL_REQUEST": "approval_request",
            "APPROVALS_REVIEWER_KEY": "approvals_reviewer",
            "PERSIST_KEY": "persist",
            "PERSIST_SESSION": "session",
            "PERSIST_ALWAYS": "always",
            "SOURCE_KEY": "source",
            "SOURCE_CONNECTOR": "connector",
            "CONNECTOR_ID_KEY": "connector_id",
            "CONNECTOR_NAME_KEY": "connector_name",
            "CONNECTOR_DESCRIPTION_KEY": "connector_description",
            "TOOL_NAME_KEY": "tool_name",
            "TOOL_TITLE_KEY": "tool_title",
            "TOOL_DESCRIPTION_KEY": "tool_description",
            "TOOL_PARAMS_KEY": "tool_params",
            "TOOL_PARAMS_DISPLAY_KEY": "tool_params_display",
        }
        imported_values = {
            "APPROVAL_KIND_KEY": APPROVAL_KIND_KEY,
            "APPROVAL_KIND_MCP_TOOL_CALL": APPROVAL_KIND_MCP_TOOL_CALL,
            "APPROVAL_KIND_TOOL_SUGGESTION": APPROVAL_KIND_TOOL_SUGGESTION,
            "REQUEST_TYPE_KEY": REQUEST_TYPE_KEY,
            "REQUEST_TYPE_APPROVAL_REQUEST": REQUEST_TYPE_APPROVAL_REQUEST,
            "APPROVALS_REVIEWER_KEY": APPROVALS_REVIEWER_KEY,
            "PERSIST_KEY": PERSIST_KEY,
            "PERSIST_SESSION": PERSIST_SESSION,
            "PERSIST_ALWAYS": PERSIST_ALWAYS,
            "SOURCE_KEY": SOURCE_KEY,
            "SOURCE_CONNECTOR": SOURCE_CONNECTOR,
            "CONNECTOR_ID_KEY": CONNECTOR_ID_KEY,
            "CONNECTOR_NAME_KEY": CONNECTOR_NAME_KEY,
            "CONNECTOR_DESCRIPTION_KEY": CONNECTOR_DESCRIPTION_KEY,
            "TOOL_NAME_KEY": TOOL_NAME_KEY,
            "TOOL_TITLE_KEY": TOOL_TITLE_KEY,
            "TOOL_DESCRIPTION_KEY": TOOL_DESCRIPTION_KEY,
            "TOOL_PARAMS_KEY": TOOL_PARAMS_KEY,
            "TOOL_PARAMS_DISPLAY_KEY": TOOL_PARAMS_DISPLAY_KEY,
        }

        self.assertEqual(imported_values, expected)
        self.assertEqual({name: getattr(protocol, name) for name in expected}, expected)


if __name__ == "__main__":
    unittest.main()
