import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core import (
    PlannedTools,
    RegisteredTool,
    ToolCall,
    CodeModeExecuteHandler,
    CodeModeWaitHandler,
    PUBLIC_TOOL_NAME,
    ToolExposure,
    ToolPayload,
    ToolPlanOptions,
    WAIT_TOOL_NAME,
    add_apply_patch_tool_for_turn_context,
    add_apply_patch_tool,
    add_extension_tools,
    add_unified_exec_tools_for_turn_context,
    add_view_image_tool_for_turn_context,
    build_environment_tool_router_from_turn_context,
    add_hosted_model_tools,
    append_tool_search_executor,
    build_model_visible_specs_and_registry,
    build_tool_router_from_plan,
    code_mode_namespace_descriptions,
    hosted_model_tool_specs,
    image_generation_tool_enabled,
    is_hidden_by_code_mode_only,
    merge_into_namespaces,
    prepend_code_mode_executors,
    tool_environment_includes_environment_id,
    tool_environment_mode_from_turn_context,
)
from pycodex.core.tools.handlers.tool_search import ToolSearchHandler
from pycodex.core.tools.tool_search_entry import (
    ToolSearchInfo,
)
from pycodex.core.tools.spec_plan import (
    add_core_utility_tools_for_turn_context,
    add_request_permissions_tool,
    spawn_agent_tool_options_from_turn_context,
    wait_agent_timeout_options_from_turn_context,
)
from pycodex.exec.session import ExecSessionConfig
from pycodex.features import Feature, Features
from pycodex.protocol import ApplyPatchToolType, ConfigShellToolType
from pycodex.protocol import TurnEnvironmentSelection
from pycodex.protocol import ToolName, WebSearchMode, WebSearchToolType


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


class ExtensionExecutor:
    def __init__(self, name: ToolName | str) -> None:
        self.name = ToolName.from_value(name)

    def tool_name(self) -> ToolName:
        return self.name

    def spec(self):
        if self.name.namespace is not None:
            return namespace_spec(self.name.namespace, self.name.name)
        return function_spec(self.name.name)

    def handle(self, _call):
        return None


class SpecPlanTests(unittest.TestCase):
    def test_collaboration_tool_options_use_resolved_config_and_turn_models(self) -> None:
        # Rust: core/src/tools/spec_plan.rs::add_collaboration_tools uses the
        # current TurnContext models plus Config role and timeout defaults.
        model = SimpleNamespace(model="gpt-visible", show_in_picker=True)
        context = SimpleNamespace(
            config=ExecSessionConfig(model="gpt-visible", model_provider_id="openai", cwd=Path("C:/repo")),
            available_models=(model,),
        )

        spawn_options = spawn_agent_tool_options_from_turn_context(context)
        wait_options = wait_agent_timeout_options_from_turn_context(context)

        self.assertEqual(spawn_options.available_models, (model,))
        self.assertTrue(spawn_options.include_usage_hint)
        self.assertIn("default: {", spawn_options.agent_type_description)
        self.assertIn("explorer: {", spawn_options.agent_type_description)
        self.assertIn("worker: {", spawn_options.agent_type_description)
        self.assertEqual(wait_options.min_timeout_ms, 10_000)
        self.assertEqual(wait_options.default_timeout_ms, 30_000)
        self.assertEqual(wait_options.max_timeout_ms, 3_600_000)

    def test_goal_core_tools_precede_request_user_input_and_reserve_extension_names(self) -> None:
        # Rust: codex-core::tools::spec_plan::add_core_utility_tools registers
        # Goal handlers after PlanHandler; later extension duplicates are skipped.
        planned = PlannedTools()
        options = ToolPlanOptions(goal_tools_enabled=True)
        add_core_utility_tools_for_turn_context(
            planned,
            SimpleNamespace(
                environments=(),
                model_info=SimpleNamespace(apply_patch_tool_type=None),
            ),
            options,
        )
        add_extension_tools(
            planned,
            (
                ExtensionExecutor("get_goal"),
                ExtensionExecutor("create_goal"),
                ExtensionExecutor("update_goal"),
            ),
            options,
        )

        specs, registry = build_model_visible_specs_and_registry(planned, options)
        self.assertEqual(
            [spec["name"] for spec in specs[:5]],
            ["update_plan", "get_goal", "create_goal", "update_goal", "request_user_input"],
        )
        self.assertEqual(registry.tool_names().count(ToolName.plain("get_goal")), 1)

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

    def test_merge_into_namespaces_accepts_tuple_tools_like_rust_vec_append(self) -> None:
        first = namespace_spec("mcp__calendar__", "list_events")
        first["tools"] = tuple(first["tools"])
        second = namespace_spec("mcp__calendar__", "create_event")
        second["tools"] = tuple(second["tools"])

        merged = merge_into_namespaces((first, second))

        self.assertEqual(
            [tool["name"] for tool in merged[0]["tools"]],
            ["create_event", "list_events"],
        )

    def test_model_visible_specs_follow_tool_exposure(self) -> None:
        class StringNamedRuntime:
            def tool_name(self):
                return "string_named"

            def spec(self):
                return function_spec("string_named")

        planned = PlannedTools()
        planned.add(RegisteredTool.plain("direct", tool_spec=function_spec("direct")))
        planned.add(StringNamedRuntime())
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
            ["direct", "string_named", "model_only"],
        )
        self.assertEqual(
            registry.tool_names(),
            (
                ToolName.plain("deferred"),
                ToolName.plain("direct"),
                ToolName.plain("hidden"),
                ToolName.plain("model_only"),
                ToolName.plain("string_named"),
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

    def test_code_mode_enabled_prepends_exec_and_wait_handlers(self) -> None:
        planned = PlannedTools()
        planned.add(RegisteredTool.plain("lookup_order", tool_spec=function_spec("lookup_order")))

        prepend_code_mode_executors(planned, ToolPlanOptions(code_mode_enabled=True))

        self.assertIsInstance(planned.runtimes[0], CodeModeExecuteHandler)
        self.assertIsInstance(planned.runtimes[1], CodeModeWaitHandler)

        specs, registry = build_model_visible_specs_and_registry(
            PlannedTools(runtimes=[RegisteredTool.plain("lookup_order", tool_spec=function_spec("lookup_order"))]),
            ToolPlanOptions(code_mode_enabled=True),
        )

        self.assertEqual([spec["name"] for spec in specs[:3]], [PUBLIC_TOOL_NAME, WAIT_TOOL_NAME, "lookup_order"])
        self.assertIsNotNone(registry.tool(ToolName.plain(PUBLIC_TOOL_NAME)))
        self.assertIsNotNone(registry.tool(ToolName.plain(WAIT_TOOL_NAME)))

    def test_code_mode_only_hides_nested_tools_but_keeps_model_only_tools(self) -> None:
        planned = PlannedTools()
        planned.add(RegisteredTool.plain("lookup_order", tool_spec=function_spec("lookup_order")))
        planned.add_with_exposure(
            RegisteredTool.plain("model_only", tool_spec=function_spec("model_only")),
            ToolExposure.DIRECT_MODEL_ONLY,
        )

        options = ToolPlanOptions(code_mode_enabled=True, code_mode_only=True)
        specs, registry = build_model_visible_specs_and_registry(planned, options)

        self.assertEqual([spec["name"] for spec in specs], [PUBLIC_TOOL_NAME, WAIT_TOOL_NAME, "model_only"])
        self.assertTrue(is_hidden_by_code_mode_only(ToolName.plain("lookup_order"), ToolExposure.DIRECT, options))
        self.assertFalse(
            is_hidden_by_code_mode_only(ToolName.plain("model_only"), ToolExposure.DIRECT_MODEL_ONLY, options)
        )
        self.assertIsNotNone(registry.tool(ToolName.plain("lookup_order")))

    def test_code_mode_namespace_descriptions_keep_first_non_empty_description(self) -> None:
        planned = PlannedTools()
        planned.add(
            RegisteredTool.namespaced(
                "mcp__calendar__",
                "list_events",
                tool_spec=namespace_spec("mcp__calendar__", "list_events"),
            )
        )
        planned.add(
            RegisteredTool.namespaced(
                "mcp__calendar__",
                "create_event",
                tool_spec=namespace_spec("mcp__calendar__", "create_event", description="Calendar tools"),
            )
        )

        descriptions = code_mode_namespace_descriptions(planned.runtimes)

        self.assertEqual(descriptions["mcp__calendar__"].name, "mcp__calendar__")
        self.assertEqual(descriptions["mcp__calendar__"].description, "Calendar tools")

    def test_add_extension_tools_skips_registered_duplicate_names_like_rust(self) -> None:
        # Rust parity: codex-core::tools::spec_plan
        # spec_plan.rs::append_extension_tool_executors skips names already registered.
        planned = PlannedTools()
        planned.add(RegisteredTool.plain("local_echo", tool_spec=function_spec("local_echo")))

        add_extension_tools(
            planned,
            (
                ExtensionExecutor("local_echo"),
                ExtensionExecutor("extension_echo"),
                ExtensionExecutor("extension_echo"),
            ),
        )
        specs, registry = build_model_visible_specs_and_registry(planned)

        self.assertEqual([spec["name"] for spec in specs], ["local_echo", "extension_echo"])
        self.assertEqual(
            registry.tool_names(),
            (ToolName.plain("extension_echo"), ToolName.plain("local_echo")),
        )

    def test_add_extension_tools_reserves_code_mode_and_tool_search_names_like_rust(self) -> None:
        # Rust parity: codex-core::tools::spec_plan
        # append_extension_tool_executors reserves code-mode exec/wait and pending tool_search.
        code_mode_plan = PlannedTools()
        add_extension_tools(
            code_mode_plan,
            (
                ExtensionExecutor(PUBLIC_TOOL_NAME),
                ExtensionExecutor(WAIT_TOOL_NAME),
                ExtensionExecutor("extension_ok"),
            ),
            ToolPlanOptions(code_mode_enabled=True),
        )
        code_mode_specs, code_mode_registry = build_model_visible_specs_and_registry(
            code_mode_plan,
            ToolPlanOptions(code_mode_enabled=True),
        )

        self.assertEqual([spec["name"] for spec in code_mode_specs], [PUBLIC_TOOL_NAME, WAIT_TOOL_NAME, "extension_ok"])
        self.assertIsInstance(code_mode_registry.tool(ToolName.plain(PUBLIC_TOOL_NAME)), CodeModeExecuteHandler)
        self.assertIsInstance(code_mode_registry.tool(ToolName.plain(WAIT_TOOL_NAME)), CodeModeWaitHandler)

        search_plan = PlannedTools()
        search_plan.add_with_exposure(
            SearchableRegisteredTool(
                name=ToolName.namespaced("mcp__calendar__", "create_event"),
                tool_spec=namespace_spec("mcp__calendar__", "create_event"),
            ),
            ToolExposure.DEFERRED,
        )
        add_extension_tools(
            search_plan,
            (ExtensionExecutor("tool_search"), ExtensionExecutor("extension_ok")),
        )
        search_specs, search_registry = build_model_visible_specs_and_registry(search_plan)

        self.assertEqual([spec.get("name", spec["type"]) for spec in search_specs], ["extension_ok", "tool_search"])
        self.assertIsInstance(search_registry.tool(ToolName.plain("tool_search")), ToolSearchHandler)
        self.assertIsNotNone(search_registry.tool(ToolName.plain("extension_ok")))

    def test_hosted_model_tool_specs_follow_provider_and_standalone_web_run(self) -> None:
        # Rust parity: codex-core::tools::spec_plan
        # spec_plan_tests.rs::hosted_tools_follow_provider_auth_model_and_config_gates.
        options = ToolPlanOptions(
            provider_web_search=True,
            web_search_mode=WebSearchMode.LIVE,
            web_search_tool_type=WebSearchToolType.TEXT_AND_IMAGE,
        )

        specs = tuple(spec.to_mapping() for spec in hosted_model_tool_specs(options))

        self.assertEqual(
            specs,
            (
                {
                    "type": "web_search",
                    "external_web_access": True,
                    "search_content_types": ["text", "image"],
                },
            ),
        )
        self.assertEqual(
            hosted_model_tool_specs(
                ToolPlanOptions(
                    provider_web_search=True,
                    standalone_web_run_available=True,
                    web_search_mode=WebSearchMode.LIVE,
                )
            ),
            (),
        )
        self.assertEqual(
            hosted_model_tool_specs(
                ToolPlanOptions(
                    provider_web_search=False,
                    web_search_mode=WebSearchMode.LIVE,
                )
            ),
            (),
        )

    def test_hosted_model_tool_specs_gate_image_generation_like_rust(self) -> None:
        disabled = ToolPlanOptions(
            auth_uses_codex_backend=True,
            provider_image_generation=True,
            image_generation_enabled=True,
            model_supports_image_input=False,
        )
        enabled = ToolPlanOptions(
            auth_uses_codex_backend=True,
            provider_image_generation=True,
            image_generation_enabled=True,
            model_supports_image_input=True,
        )

        self.assertFalse(image_generation_tool_enabled(disabled))
        self.assertTrue(image_generation_tool_enabled(enabled))
        self.assertEqual(
            tuple(spec.to_mapping() for spec in hosted_model_tool_specs(enabled)),
            ({"type": "image_generation", "output_format": "png"},),
        )

    def test_build_model_visible_specs_adds_hosted_specs_from_options(self) -> None:
        planned = PlannedTools()
        add_hosted_model_tools(
            planned,
            ToolPlanOptions(provider_web_search=True, web_search_mode=WebSearchMode.CACHED),
        )
        self.assertEqual(
            [spec.to_mapping() for spec in planned.hosted_specs],
            [{"type": "web_search", "external_web_access": False}],
        )

        specs, _registry = build_model_visible_specs_and_registry(
            PlannedTools(),
            ToolPlanOptions(provider_web_search=True, web_search_mode=WebSearchMode.CACHED),
        )

        self.assertEqual(specs, ({"type": "web_search", "external_web_access": False},))

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

    def test_turn_environment_mode_helpers_match_rust_counts(self) -> None:
        self.assertEqual(tool_environment_mode_from_turn_context(SimpleNamespace(environments=())), "none")
        single = SimpleNamespace(environments=(TurnEnvironmentSelection("local", Path("C:/repo")),))
        multiple = SimpleNamespace(
            environments=(
                TurnEnvironmentSelection("local", Path("C:/repo")),
                TurnEnvironmentSelection("remote", Path("C:/remote")),
            )
        )

        self.assertEqual(tool_environment_mode_from_turn_context(single), "single")
        self.assertFalse(tool_environment_includes_environment_id(single))
        self.assertEqual(tool_environment_mode_from_turn_context(multiple), "multiple")
        self.assertTrue(tool_environment_includes_environment_id(multiple))

    def test_turn_context_environment_tools_include_environment_id_only_for_multiple_environments(self) -> None:
        no_environment = SimpleNamespace(environments=())
        single = SimpleNamespace(environments=(TurnEnvironmentSelection("local", Path("C:/repo")),))
        multiple = SimpleNamespace(
            environments=(
                TurnEnvironmentSelection("local", Path("C:/repo")),
                TurnEnvironmentSelection("remote", Path("C:/remote")),
            )
        )

        disabled = PlannedTools()
        add_unified_exec_tools_for_turn_context(disabled, no_environment)
        add_apply_patch_tool_for_turn_context(
            disabled,
            no_environment,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        )
        add_view_image_tool_for_turn_context(disabled, no_environment)
        disabled_specs, disabled_registry = build_model_visible_specs_and_registry(disabled)
        self.assertEqual(disabled_specs, ())
        self.assertEqual(disabled_registry.tool_names(), ())

        single_plan = PlannedTools()
        add_unified_exec_tools_for_turn_context(single_plan, single)
        add_apply_patch_tool_for_turn_context(
            single_plan,
            single,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        )
        add_view_image_tool_for_turn_context(single_plan, single)
        single_specs, single_registry = build_model_visible_specs_and_registry(single_plan)
        single_by_name = {spec["name"]: spec for spec in single_specs}
        self.assertNotIn("environment_id", single_by_name["exec_command"]["parameters"]["properties"])
        self.assertNotIn("Environment ID", single_by_name["apply_patch"]["format"]["definition"])
        self.assertNotIn("environment_id", single_by_name["view_image"]["parameters"]["properties"])
        self.assertEqual(
            set(single_registry.tool_names()),
            {
                ToolName.plain("exec_command"),
                ToolName.plain("write_stdin"),
                ToolName.plain("apply_patch"),
                ToolName.plain("view_image"),
            },
        )

        multiple_plan = PlannedTools()
        add_unified_exec_tools_for_turn_context(multiple_plan, multiple)
        add_apply_patch_tool_for_turn_context(
            multiple_plan,
            multiple,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        )
        add_view_image_tool_for_turn_context(multiple_plan, multiple)
        multiple_specs, _multiple_registry = build_model_visible_specs_and_registry(multiple_plan)
        multiple_by_name = {spec["name"]: spec for spec in multiple_specs}
        self.assertIn("environment_id", multiple_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("Environment ID", multiple_by_name["apply_patch"]["format"]["definition"])
        self.assertIn("environment_id", multiple_by_name["view_image"]["parameters"]["properties"])

    def test_build_environment_tool_router_from_turn_context_uses_environment_mode(self) -> None:
        features = Features.with_defaults().enable(Feature.UNIFIED_EXEC)
        turn_context = SimpleNamespace(
            features=features,
            model_info=SimpleNamespace(shell_type=ConfigShellToolType.UNIFIED_EXEC),
            config=SimpleNamespace(permissions=SimpleNamespace(allow_login_shell=False)),
            environments=(
                TurnEnvironmentSelection("local", Path("C:/repo")),
                TurnEnvironmentSelection("remote", Path("C:/remote")),
            )
        )

        router = build_environment_tool_router_from_turn_context(
            turn_context,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        )

        specs_by_name = {spec["name"]: spec for spec in router.model_visible_specs()}
        self.assertIn("environment_id", specs_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("Environment ID", specs_by_name["apply_patch"]["format"]["definition"])
        self.assertIn("environment_id", specs_by_name["view_image"]["parameters"]["properties"])

    def test_build_environment_tool_router_uses_shell_command_when_unified_exec_is_disabled(self) -> None:
        # Rust owner: codex-core::tools::spec_plan::add_shell_tools.
        # Rust source: spec_plan.rs selects the shell family through
        # shell_type_for_model_and_features instead of forcing unified exec.
        features = Features.with_defaults().disable(Feature.UNIFIED_EXEC)
        turn_context = SimpleNamespace(
            features=features,
            model_info=SimpleNamespace(shell_type=ConfigShellToolType.UNIFIED_EXEC),
            config=SimpleNamespace(permissions=SimpleNamespace(allow_login_shell=False)),
            environments=(TurnEnvironmentSelection("local", Path("C:/repo")),),
        )

        router = build_environment_tool_router_from_turn_context(turn_context)
        specs = router.model_visible_specs()
        names = [spec["name"] for spec in specs]

        self.assertIn("shell_command", names)
        self.assertNotIn("exec_command", names)
        self.assertNotIn("write_stdin", names)
        shell_command = next(spec for spec in specs if spec["name"] == "shell_command")
        self.assertIn("timeout_ms", shell_command["parameters"]["properties"])

    def test_add_request_permissions_tool_follows_feature_gate_like_rust(self) -> None:
        disabled = PlannedTools()
        add_request_permissions_tool(disabled, request_permissions_tool_enabled=False)
        disabled_specs, disabled_registry = build_model_visible_specs_and_registry(disabled)

        self.assertEqual(disabled_specs, ())
        self.assertEqual(disabled_registry.tool_names(), ())

        enabled = PlannedTools()
        add_request_permissions_tool(enabled, request_permissions_tool_enabled=True)
        enabled_specs, enabled_registry = build_model_visible_specs_and_registry(enabled)

        self.assertEqual(len(enabled_specs), 1)
        self.assertEqual(enabled_specs[0]["name"], "request_permissions")
        self.assertIsNotNone(enabled_registry.tool(ToolName.plain("request_permissions")))
        self.assertTrue(
            enabled_registry.matches_kind(
                ToolName.plain("request_permissions"),
                ToolPayload.function('{"permissions":{"network":{"enabled":true}}}'),
            )
        )

        with self.assertRaises(TypeError):
            add_request_permissions_tool(PlannedTools(), request_permissions_tool_enabled=1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
