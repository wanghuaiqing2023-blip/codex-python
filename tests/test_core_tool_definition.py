import unittest

from pycodex.core import ToolDefinition


def tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="lookup_order",
        description="Look up an order",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object"},
        defer_loading=False,
    )


class ToolDefinitionTests(unittest.TestCase):
    def test_renamed_overrides_name_only(self) -> None:
        self.assertEqual(
            tool_definition().renamed("mcp__orders__lookup_order"),
            ToolDefinition(
                name="mcp__orders__lookup_order",
                description="Look up an order",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={"type": "object"},
                defer_loading=False,
            ),
        )

    def test_into_deferred_drops_output_schema_and_sets_defer_loading(self) -> None:
        self.assertEqual(
            tool_definition().into_deferred(),
            ToolDefinition(
                name="lookup_order",
                description="Look up an order",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema=None,
                defer_loading=True,
            ),
        )

    def test_mapping_round_trip_omits_absent_output_schema(self) -> None:
        deferred = tool_definition().into_deferred()

        self.assertEqual(
            ToolDefinition.from_mapping(deferred.to_mapping()),
            deferred,
        )
        self.assertNotIn("output_schema", deferred.to_mapping())

    def test_input_and_output_schemas_are_copied(self) -> None:
        schema = {"type": "object", "properties": {"id": {"type": "string"}}}
        output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        definition = ToolDefinition(
            "lookup",
            "Lookup",
            schema,
            output_schema,
        )

        schema["properties"]["id"]["type"] = "number"
        output_schema["properties"]["ok"]["type"] = "string"

        self.assertEqual(definition.input_schema["properties"]["id"]["type"], "string")
        self.assertEqual(definition.output_schema["properties"]["ok"]["type"], "boolean")


if __name__ == "__main__":
    unittest.main()
