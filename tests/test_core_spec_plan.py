import unittest

from pycodex.core import (
    PlannedTools,
    RegisteredTool,
    ToolCall,
    ToolExposure,
    ToolPayload,
    ToolPlanOptions,
    ToolSearchHandler,
    ToolSearchInfo,
    add_apply_patch_tool,
    append_tool_search_executor,
    build_model_visible_specs_and_registry,
    build_tool_router_from_plan,
    merge_into_namespaces,
)
from pycodex.protocol import ApplyPatchToolType
from pycodex.protocol import ToolName


def function_spec(name: str, description: str | None = None) -> dict[str, object]:
    return {
        "type": "function",
        "name": name,
        "description": description or f"{name} description",
        "strict": False,
        "parameters": {"type": "object", "properties": {}},
    }


def namespace_spec(namespace: str, *tool_names: str, description: str = "") -> dict[str, object]:
    return {
        "type": "namespace",
        "name": namespace,
        "description": description,
        "tools": [function_spec(name) for name in tool_names],
    }


class SearchableRegisteredTool(RegisteredTool):
    def search_info(self):
        return ToolSearchInfo.from_spec(
            f"{self.name.name} deferred search text",
            self.tool_spec,
            {"name": "Deferred tools", "description": "Tools hidden until search."},
        )


class SpecPlanTests(unittest.TestCase):
    def test_merge_into_namespaces_coalesces_and_sorts_functions(self) -> None:
        merged = merge_into_namespaces(
            [
                namespace_spec("mcp__calendar__", "list_events"),
                function_spec("local_echo"),
                namespace_spec("mcp__calendar__", "create_event", description="Calendar tools"),
                namespace_spec("empty__", "z_tool"),
            ]
        )

        self.assertEqual([spec["type"] for spec in merged], ["namespace", "function", "namespace"])
        self.assertEqual(merged[0]["description"], "Calendar tools")
        self.assertEqual(
            [tool["name"] for tool in merged[0]["tools"]],
            ["create_event", "list_events"],
        )
        self.assertEqual(merged[2]["description"], "Tools in the empty__ namespace.")

    def test_model_visible_specs_follow_tool_exposure(self) -> None:
        planned = PlannedTools()
        planned.add(RegisteredTool.plain("direct", tool_spec=function_spec("direct")))
        planned.add_with_exposure(
            RegisteredTool.plain("deferred", tool_spec=function_spec("deferred")),
            ToolExposure.DEFERRED,
        )
        planned.add_dispatch_only(
            RegisteredTool.plain("hidden", tool_spec=function_spec("hidden"))
        )
        planned.add_with_exposure(
            RegisteredTool.plain("model_only", tool_spec=function_spec("model_only")),
            ToolExposure.DIRECT_MODEL_ONLY,
        )

        specs, registry = build_model_visible_specs_and_registry(
            planned,
            ToolPlanOptions(search_tool_enabled=False),
        )

        self.assertEqual(
            [spec["name"] for spec in specs],
            ["direct", "model_only"],
        )
        self.assertEqual(
            registry.tool_names(),
            (
                ToolName.plain("deferred"),
                ToolName.plain("direct"),
                ToolName.plain("hidden"),
                ToolName.plain("model_only"),
            ),
        )
        self.assertEqual(registry.tool_exposure(ToolName.plain("hidden")), ToolExposure.HIDDEN)

    def test_deferred_search_infos_inject_tool_search_handler(self) -> None:
        planned = PlannedTools()
        planned.add(RegisteredTool.plain("direct", tool_spec=function_spec("direct")))
        planned.add_with_exposure(
            SearchableRegisteredTool(
                name=ToolName.namespaced("mcp__calendar__", "create_event"),
                tool_spec=namespace_spec("mcp__calendar__", "create_event"),
            ),
            ToolExposure.DEFERRED,
        )

        specs, registry = build_model_visible_specs_and_registry(planned)

        self.assertEqual([spec["type"] for spec in specs], ["function", "tool_search"])
        self.assertIsInstance(registry.tool(ToolName.plain("tool_search")), ToolSearchHandler)
        self.assertEqual(
            registry.tool_exposure(ToolName.namespaced("mcp__calendar__", "create_event")),
            ToolExposure.DEFERRED,
        )
        tool_search_spec = next(spec for spec in specs if spec["type"] == "tool_search")
        self.assertIn("- Deferred tools: Tools hidden until search.", tool_search_spec["description"])

    def test_tool_search_is_not_injected_without_search_or_namespace_support(self) -> None:
        for options in (
            ToolPlanOptions(search_tool_enabled=False, namespace_tools_enabled=True),
            ToolPlanOptions(search_tool_enabled=True, namespace_tools_enabled=False),
        ):
            planned = PlannedTools()
            planned.add_with_exposure(
                SearchableRegisteredTool(
                    name=ToolName.namespaced("mcp__calendar__", "create_event"),
                    tool_spec=namespace_spec("mcp__calendar__", "create_event"),
                ),
                ToolExposure.DEFERRED,
            )

            append_tool_search_executor(planned, options)

            self.assertNotIn(ToolName.plain("tool_search"), [tool.tool_name() for tool in planned.runtimes])

    def test_namespace_specs_are_filtered_when_namespace_support_is_disabled(self) -> None:
        planned = PlannedTools()
        planned.add(
            RegisteredTool.namespaced(
                "mcp__calendar__",
                "create_event",
                tool_spec=namespace_spec("mcp__calendar__", "create_event"),
            )
        )
        planned.add_hosted_spec(function_spec("hosted"))

        specs, registry = build_model_visible_specs_and_registry(
            planned,
            ToolPlanOptions(namespace_tools_enabled=False),
        )

        self.assertEqual(specs, (function_spec("hosted"),))
        self.assertIsNotNone(registry.tool(ToolName.namespaced("mcp__calendar__", "create_event")))

    def test_build_tool_router_from_plan_preserves_specs_and_registry_queries(self) -> None:
        planned = PlannedTools()
        planned.add(
            RegisteredTool.plain(
                "parallel_tool",
                tool_spec=function_spec("parallel_tool"),
                supports_parallel=True,
            )
        )

        router = build_tool_router_from_plan(planned)

        self.assertEqual(router.model_visible_specs(), (function_spec("parallel_tool"),))
        self.assertTrue(
            router.tool_supports_parallel(
                ToolCall(
                    tool_name=ToolName.plain("parallel_tool"),
                    call_id="call-parallel",
                    payload=ToolPayload.function("{}"),
                )
            )
        )

    def test_add_apply_patch_tool_follows_environment_and_model_support(self) -> None:
        for has_environment, apply_patch_tool_type in (
            (False, ApplyPatchToolType.FREEFORM),
            (True, None),
        ):
            planned = PlannedTools()
            add_apply_patch_tool(
                planned,
                has_environment=has_environment,
                apply_patch_tool_type=apply_patch_tool_type,
            )
            specs, registry = build_model_visible_specs_and_registry(planned)

            self.assertEqual(specs, ())
            self.assertEqual(registry.tool_names(), ())

        planned = PlannedTools()
        add_apply_patch_tool(
            planned,
            has_environment=True,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
            multi_environment=True,
        )

        specs, registry = build_model_visible_specs_and_registry(planned)

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["type"], "custom")
        self.assertEqual(specs[0]["name"], "apply_patch")
        self.assertIn("Environment ID", specs[0]["format"]["definition"])
        self.assertEqual(registry.tool_names(), (ToolName.plain("apply_patch"),))
        self.assertTrue(
            registry.matches_kind(
                ToolName.plain("apply_patch"),
                ToolPayload.custom("*** Begin Patch\n"),
            )
        )
        self.assertFalse(
            registry.matches_kind(
                ToolName.plain("apply_patch"),
                ToolPayload.function("{}"),
            )
        )


if __name__ == "__main__":
    unittest.main()
