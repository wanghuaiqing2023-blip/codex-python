import unittest

from pycodex.core import (
    FreeformToolFormat,
    ToolSearchInfo,
    ToolSearchSourceInfo,
    ToolSpec,
    coalesce_loadable_tool_specs,
    default_namespace_description,
    loadable_tool_spec_from_spec,
)


class ToolSearchEntryTests(unittest.TestCase):
    def test_function_specs_become_deferred_loadable_tools(self) -> None:
        spec = {
            "type": "function",
            "name": "lookup_order",
            "description": "Look up an order",
            "strict": False,
            "defer_loading": False,
            "parameters": {"type": "object", "properties": {}},
            "output_schema": {"type": "object"},
        }

        output = loadable_tool_spec_from_spec(spec)

        self.assertEqual(
            output,
            {
                "type": "function",
                "name": "lookup_order",
                "description": "Look up an order",
                "strict": False,
                "defer_loading": True,
                "parameters": {"type": "object", "properties": {}},
            },
        )
        self.assertEqual(spec["defer_loading"], False)
        self.assertIn("output_schema", spec)

    def test_namespace_specs_default_description_and_defer_child_tools(self) -> None:
        spec = {
            "type": "namespace",
            "name": "mcp__calendar__",
            "description": "  ",
            "tools": [
                {
                    "type": "function",
                    "name": "create_event",
                    "description": "Create events",
                    "strict": False,
                    "parameters": {"type": "object"},
                    "output_schema": {"type": "object"},
                }
            ],
        }

        output = ToolSearchInfo.from_spec("calendar events", spec)

        self.assertIsNotNone(output)
        self.assertEqual(output.entry.search_text, "calendar events")
        self.assertEqual(
            output.entry.output,
            {
                "type": "namespace",
                "name": "mcp__calendar__",
                "description": default_namespace_description("mcp__calendar__"),
                "tools": [
                    {
                        "type": "function",
                        "name": "create_event",
                        "description": "Create events",
                        "strict": False,
                        "parameters": {"type": "object"},
                        "defer_loading": True,
                    }
                ],
            },
        )

    def test_hosted_or_freeform_specs_are_not_tool_search_loadable(self) -> None:
        self.assertIsNone(loadable_tool_spec_from_spec(ToolSpec.image_generation("png")))
        self.assertIsNone(loadable_tool_spec_from_spec({"type": "web_search"}))
        self.assertIsNone(
            loadable_tool_spec_from_spec(
                ToolSpec.freeform(
                    name="patch",
                    description="Patch files",
                    format=FreeformToolFormat.grammar(
                        syntax="lark",
                        definition='start: "patch"',
                    ),
                )
            )
        )

    def test_source_info_can_be_carried_with_search_info(self) -> None:
        info = ToolSearchInfo.from_spec(
            "dynamic lookup",
            {
                "type": "function",
                "name": "lookup",
                "description": "Lookup",
                "strict": False,
                "parameters": {"type": "object"},
            },
            {"name": "Dynamic tools", "description": "Thread tools"},
        )

        self.assertEqual(
            info.source_info,
            ToolSearchSourceInfo("Dynamic tools", "Thread tools"),
        )
        self.assertEqual(
            info.source_info.to_mapping(),
            {"name": "Dynamic tools", "description": "Thread tools"},
        )

    def test_loadable_namespace_specs_coalesce_in_result_order(self) -> None:
        specs = (
            {
                "type": "namespace",
                "name": "mcp__calendar__",
                "description": "Calendar tools",
                "tools": [{"type": "function", "name": "create_event"}],
            },
            {"type": "function", "name": "local_echo"},
            {
                "type": "namespace",
                "name": "mcp__calendar__",
                "description": "Calendar tools",
                "tools": [{"type": "function", "name": "list_events"}],
            },
        )

        self.assertEqual(
            coalesce_loadable_tool_specs(specs),
            (
                {
                    "type": "namespace",
                    "name": "mcp__calendar__",
                    "description": "Calendar tools",
                    "tools": [
                        {"type": "function", "name": "create_event"},
                        {"type": "function", "name": "list_events"},
                    ],
                },
                {"type": "function", "name": "local_echo"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
