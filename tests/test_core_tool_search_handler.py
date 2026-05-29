import unittest

from pycodex.core import (
    FunctionCallError,
    TOOL_SEARCH_DEFAULT_LIMIT,
    TOOL_SEARCH_TOOL_NAME,
    ToolPayload,
    ToolSearchHandler,
    ToolSearchInfo,
    ToolSearchOutput,
    ToolSearchSourceInfo,
    create_tool_search_tool,
)
from pycodex.protocol import SearchToolCallParams, ToolName


def function_spec(name: str, description: str) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": False,
        "parameters": {"type": "object", "properties": {}},
    }


def namespace_spec(namespace: str, tool_name: str, description: str) -> dict[str, object]:
    return {
        "type": "namespace",
        "name": namespace,
        "description": "",
        "tools": [function_spec(tool_name, description)],
    }


class ToolSearchHandlerTests(unittest.TestCase):
    def test_tool_search_spec_deduplicates_and_renders_sources(self) -> None:
        spec = create_tool_search_tool(
            [
                ToolSearchSourceInfo(
                    "Google Drive",
                    "Use Google Drive as the single entrypoint for Drive, Docs, Sheets, and Slides work.",
                ),
                ToolSearchSourceInfo("Google Drive"),
                ToolSearchSourceInfo("docs"),
            ],
            default_limit=8,
        )

        self.assertEqual(spec["type"], "tool_search")
        self.assertEqual(spec["execution"], "client")
        self.assertIn("- Google Drive: Use Google Drive", spec["description"])
        self.assertIn("- docs", spec["description"])
        self.assertEqual(
            spec["parameters"],
            {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of tools to return (defaults to 8).",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for deferred tools.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    def test_tool_search_spec_reports_no_enabled_sources(self) -> None:
        self.assertIn("None currently enabled.", create_tool_search_tool([])["description"])

    def test_handler_metadata_matches_upstream_tool_contract(self) -> None:
        handler = ToolSearchHandler([])

        self.assertEqual(handler.tool_name(), ToolName.plain(TOOL_SEARCH_TOOL_NAME))
        self.assertTrue(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("calendar"))))
        self.assertFalse(handler.matches_kind(ToolPayload.function("{}")))
        self.assertEqual(
            handler.spec()["parameters"]["properties"]["limit"]["description"],
            f"Maximum number of tools to return (defaults to {TOOL_SEARCH_DEFAULT_LIMIT}).",
        )

    def test_handle_validates_payload_query_and_limit(self) -> None:
        handler = ToolSearchHandler([])

        with self.assertRaisesRegex(FunctionCallError, "unsupported payload") as unsupported:
            handler.handle(ToolPayload.function("{}"))
        self.assertTrue(unsupported.exception.is_fatal)
        with self.assertRaisesRegex(FunctionCallError, "query must not be empty") as empty_query:
            handler.handle(ToolPayload.tool_search(SearchToolCallParams("  ")))
        self.assertTrue(empty_query.exception.is_model_response)
        with self.assertRaisesRegex(FunctionCallError, "limit must be greater than zero") as bad_limit:
            handler.handle(ToolPayload.tool_search(SearchToolCallParams("calendar", limit=0)))
        self.assertTrue(bad_limit.exception.is_model_response)

    def test_empty_handler_returns_completed_empty_tool_search_output(self) -> None:
        output = ToolSearchHandler([]).handle(
            ToolPayload.tool_search(SearchToolCallParams("calendar"))
        )

        self.assertEqual(output, ToolSearchOutput(()))

    def test_bm25_search_returns_relevant_deferred_tools_in_score_order(self) -> None:
        handler = ToolSearchHandler(
            [
                ToolSearchInfo.from_spec(
                    "calendar create event schedule meeting",
                    namespace_spec("mcp__calendar__", "create_event", "Create events"),
                    ToolSearchSourceInfo("calendar"),
                ),
                ToolSearchInfo.from_spec(
                    "email inbox recent messages",
                    namespace_spec("mcp__gmail__", "get_recent_emails", "Recent email"),
                    ToolSearchSourceInfo("gmail"),
                ),
                ToolSearchInfo.from_spec(
                    "calendar list event agenda schedule",
                    namespace_spec("mcp__calendar__", "list_events", "List events"),
                    ToolSearchSourceInfo("calendar"),
                ),
            ]
        )

        results = handler.handle(
            ToolPayload.tool_search(SearchToolCallParams("calendar event", limit=2))
        )

        self.assertEqual(len(results.tools), 1)
        calendar_namespace = results.tools[0]
        self.assertEqual(calendar_namespace["type"], "namespace")
        self.assertEqual(calendar_namespace["name"], "mcp__calendar__")
        self.assertEqual(
            [tool["name"] for tool in calendar_namespace["tools"]],
            ["create_event", "list_events"],
        )

    def test_search_output_tools_coalesces_explicit_result_entries(self) -> None:
        create_info = ToolSearchInfo.from_spec(
            "calendar create",
            namespace_spec("mcp__calendar__", "create_event", "Create events"),
        )
        local_info = ToolSearchInfo.from_spec(
            "local echo",
            function_spec("local_echo", "Echo locally"),
        )
        list_info = ToolSearchInfo.from_spec(
            "calendar list",
            namespace_spec("mcp__calendar__", "list_events", "List events"),
        )
        handler = ToolSearchHandler([create_info, local_info, list_info])

        tools = handler.search_output_tools([create_info.entry, local_info.entry, list_info.entry])

        self.assertEqual([tool["type"] for tool in tools], ["namespace", "function"])
        self.assertEqual(
            [tool["name"] for tool in tools[0]["tools"]],
            ["create_event", "list_events"],
        )

    def test_spec_rejects_non_rust_source_and_limit_shapes(self) -> None:
        with self.assertRaises(TypeError):
            create_tool_search_tool([{"name": "docs"}])
        with self.assertRaises(TypeError):
            create_tool_search_tool([], default_limit=True)
        with self.assertRaises(ValueError):
            create_tool_search_tool([], default_limit=-1)

    def test_handler_constructor_rejects_non_search_info_entries(self) -> None:
        with self.assertRaises(TypeError):
            ToolSearchHandler((object(),))
        with self.assertRaises(TypeError):
            ToolSearchHandler("calendar")

    def test_handler_rejects_non_rust_query_limit_and_payload_shapes(self) -> None:
        handler = ToolSearchHandler([])

        with self.assertRaises(TypeError):
            handler.matches_kind(object())
        with self.assertRaises(TypeError):
            handler.search(1)
        with self.assertRaises(TypeError):
            handler.search("calendar", True)
        with self.assertRaises(ValueError):
            handler.search("calendar", -1)

    def test_search_output_tools_rejects_non_entry_results(self) -> None:
        handler = ToolSearchHandler([])

        with self.assertRaises(TypeError):
            handler.search_output_tools((object(),))
        with self.assertRaises(TypeError):
            handler.search_output_tools("calendar")


if __name__ == "__main__":
    unittest.main()
