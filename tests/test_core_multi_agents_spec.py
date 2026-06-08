import unittest
from types import SimpleNamespace

from pycodex.protocol import ModelServiceTier, ReasoningEffort, ReasoningEffortPreset
from pycodex.core.tools.handlers.multi_agents_spec import (
    MULTI_AGENT_V1_NAMESPACE,
    SPAWN_AGENT_INHERITED_MODEL_GUIDANCE,
    SPAWN_AGENT_MODEL_OVERRIDE_DESCRIPTION,
    SPAWN_AGENT_SERVICE_TIER_OVERRIDE_DESCRIPTION,
    SpawnAgentToolOptions,
    WaitAgentTimeoutOptions,
    create_close_agent_tool_v2,
    create_collab_input_items_schema,
    create_followup_task_tool,
    create_list_agents_tool,
    create_resume_agent_tool,
    create_send_input_tool_v1,
    create_send_message_tool,
    create_spawn_agent_tool_v1,
    create_spawn_agent_tool_v2,
    create_wait_agent_tool_v1,
    create_wait_agent_tool_v2,
    hide_spawn_agent_metadata_options,
    spawn_agent_models_description,
    spawn_agent_output_schema_v2,
)


def model_preset(model_id: str, show_in_picker: bool) -> SimpleNamespace:
    return SimpleNamespace(
        model=f"{model_id}-model",
        description=f"{model_id} description",
        default_reasoning_effort=ReasoningEffort.MEDIUM,
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffort.MEDIUM, "Balanced"),
        ),
        service_tiers=(
            ModelServiceTier("priority", "Fast", "1.5x speed, increased usage"),
        ),
        show_in_picker=show_in_picker,
    )


class CoreMultiAgentsSpecTests(unittest.TestCase):
    def test_spawn_agent_v1_is_namespaced_and_exposes_output_schema(self) -> None:
        spec = create_spawn_agent_tool_v1(SpawnAgentToolOptions(agent_type_description="Agent role."))
        self.assertEqual(spec["type"], "namespace")
        self.assertEqual(spec["name"], MULTI_AGENT_V1_NAMESPACE)
        tool = spec["tools"][0]
        self.assertEqual(tool["name"], "spawn_agent")
        self.assertIn("agent_type", tool["parameters"]["properties"])
        self.assertEqual(tool["output_schema"]["required"], ["agent_id", "nickname"])

    def test_spawn_agent_v2_requires_task_name_and_message(self) -> None:
        spec = create_spawn_agent_tool_v2(
            SpawnAgentToolOptions(
                available_models=(
                    model_preset("visible", True),
                    model_preset("hidden", False),
                ),
                agent_type_description="Agent role.",
                include_usage_hint=True,
                max_concurrent_threads_per_session=3,
            )
        )
        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "spawn_agent")
        self.assertEqual(spec["parameters"]["required"], ["task_name", "message"])
        self.assertIn("max_concurrent_threads_per_session = 3", spec["description"])
        self.assertIn(SPAWN_AGENT_INHERITED_MODEL_GUIDANCE, spec["description"])
        self.assertIn("The spawned agent will have the same tools as you", spec["description"])
        self.assertIn(
            "- `visible-model`: visible description Reasoning efforts: medium (default). Service tiers: priority.",
            spec["description"],
        )
        self.assertNotIn("hidden-model", spec["description"])
        properties = spec["parameters"]["properties"]
        self.assertIn("task_name", properties)
        self.assertIn("message", properties)
        self.assertIn("fork_turns", properties)
        self.assertNotIn("items", properties)
        self.assertNotIn("fork_context", properties)
        self.assertEqual(properties["agent_type"]["description"], "Agent role.")
        self.assertEqual(properties["model"]["description"], SPAWN_AGENT_MODEL_OVERRIDE_DESCRIPTION)
        self.assertEqual(
            properties["service_tier"]["description"],
            SPAWN_AGENT_SERVICE_TIER_OVERRIDE_DESCRIPTION,
        )
        self.assertEqual(spec["output_schema"]["required"], ["task_name", "nickname"])

    def test_spawn_agent_v2_caps_visible_model_summaries(self) -> None:
        spec = create_spawn_agent_tool_v2(
            SpawnAgentToolOptions(
                available_models=tuple(
                    model_preset(name, True)
                    for name in ("first", "second", "third", "fourth", "fifth", "sixth")
                ),
                agent_type_description="Agent role.",
                include_usage_hint=True,
                max_concurrent_threads_per_session=3,
            )
        )

        for name in ("first", "second", "third", "fourth", "fifth"):
            self.assertIn(f"`{name}-model`", spec["description"])
        self.assertNotIn("`sixth-model`", spec["description"])

    def test_hide_spawn_agent_metadata_removes_model_role_reasoning(self) -> None:
        properties = {"agent_type": {}, "model": {}, "reasoning_effort": {}, "service_tier": {}, "message": {}}
        hide_spawn_agent_metadata_options(properties)
        self.assertEqual(properties, {"message": {}})
        schema = spawn_agent_output_schema_v2(True)
        self.assertEqual(schema["required"], ["task_name"])
        self.assertNotIn("nickname", schema["properties"])
        spec = create_spawn_agent_tool_v2(
            SpawnAgentToolOptions(
                available_models=(model_preset("visible", True),),
                agent_type_description="Agent role.",
                hide_agent_type_model_reasoning=True,
                include_usage_hint=True,
            )
        )
        spec_properties = spec["parameters"]["properties"]
        self.assertNotIn("agent_type", spec_properties)
        self.assertNotIn("model", spec_properties)
        self.assertNotIn("reasoning_effort", spec_properties)
        self.assertNotIn("service_tier", spec_properties)

    def test_send_and_close_tool_shapes(self) -> None:
        send_input = create_send_input_tool_v1()["tools"][0]
        self.assertEqual(send_input["parameters"]["required"], ["target"])
        self.assertIn("items", send_input["parameters"]["properties"])
        send_message = create_send_message_tool()
        self.assertEqual(send_message["parameters"]["required"], ["target", "message"])
        self.assertEqual(
            send_message["parameters"]["properties"]["target"]["description"],
            "Relative or canonical task name to message (from spawn_agent).",
        )
        self.assertNotIn("output_schema", send_message)
        followup_task = create_followup_task_tool()
        self.assertEqual(followup_task["name"], "followup_task")
        self.assertEqual(followup_task["parameters"]["required"], ["target", "message"])
        self.assertNotIn("output_schema", followup_task)
        self.assertIn("previous_status", create_close_agent_tool_v2()["output_schema"]["properties"])
        resume = create_resume_agent_tool()
        self.assertEqual(resume["type"], "namespace")
        self.assertEqual(resume["tools"][0]["name"], "resume_agent")
        self.assertEqual(resume["tools"][0]["parameters"]["required"], ["id"])

    def test_wait_agent_parameters_use_configured_timeout_bounds(self) -> None:
        options = WaitAgentTimeoutOptions(default_timeout_ms=20, min_timeout_ms=10, max_timeout_ms=30)
        v1 = create_wait_agent_tool_v1(options)["tools"][0]
        self.assertEqual(v1["parameters"]["required"], ["targets"])
        self.assertIn("Defaults to 20, min 10, max 30", v1["parameters"]["properties"]["timeout_ms"]["description"])
        v2 = create_wait_agent_tool_v2(options)
        self.assertNotIn("required", v2["parameters"])
        self.assertIn("timed_out", v2["output_schema"]["properties"])

    def test_list_agents_and_collab_input_schema(self) -> None:
        list_agents = create_list_agents_tool()
        self.assertIn("path_prefix", list_agents["parameters"]["properties"])
        self.assertEqual(
            list_agents["output_schema"]["properties"]["agents"]["items"]["required"],
            ["agent_name", "agent_status", "last_task_message"],
        )
        self.assertEqual(
            list_agents["output_schema"]["properties"]["agents"]["items"]["properties"]["agent_status"]["allOf"][0]["oneOf"][0]["enum"],
            ["pending_init", "running", "interrupted", "shutdown", "not_found"],
        )
        items = create_collab_input_items_schema()
        self.assertEqual(items["type"], "array")
        self.assertIn("mention", items["items"]["properties"]["type"]["description"])

    def test_model_description_filters_picker_visible_models(self) -> None:
        description = spawn_agent_models_description(
            (
                model_preset("hidden", False),
                model_preset("visible", True),
            )
        )
        self.assertIn(
            "- `visible-model`: visible description Reasoning efforts: medium (default). Service tiers: priority.",
            description,
        )
        self.assertNotIn("hidden-model", description)

    def test_options_reject_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            SpawnAgentToolOptions(available_models="gpt")
        with self.assertRaises(TypeError):
            WaitAgentTimeoutOptions(default_timeout_ms=True)


if __name__ == "__main__":
    unittest.main()
