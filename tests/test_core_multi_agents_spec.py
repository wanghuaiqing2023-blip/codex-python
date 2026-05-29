import unittest

from pycodex.core.multi_agents_spec import (
    MULTI_AGENT_V1_NAMESPACE,
    SpawnAgentToolOptions,
    WaitAgentTimeoutOptions,
    create_close_agent_tool_v2,
    create_collab_input_items_schema,
    create_followup_task_tool,
    create_list_agents_tool,
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
            SpawnAgentToolOptions(agent_type_description="Agent role.", max_concurrent_threads_per_session=3)
        )
        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "spawn_agent")
        self.assertEqual(spec["parameters"]["required"], ["task_name", "message"])
        self.assertIn("max_concurrent_threads_per_session = 3", spec["description"])

    def test_hide_spawn_agent_metadata_removes_model_role_reasoning(self) -> None:
        properties = {"agent_type": {}, "model": {}, "reasoning_effort": {}, "service_tier": {}, "message": {}}
        hide_spawn_agent_metadata_options(properties)
        self.assertEqual(properties, {"message": {}})
        schema = spawn_agent_output_schema_v2(True)
        self.assertEqual(schema["required"], ["task_name"])
        self.assertNotIn("nickname", schema["properties"])

    def test_send_and_close_tool_shapes(self) -> None:
        send_input = create_send_input_tool_v1()["tools"][0]
        self.assertEqual(send_input["parameters"]["required"], ["target"])
        self.assertIn("items", send_input["parameters"]["properties"])
        self.assertEqual(create_send_message_tool()["parameters"]["required"], ["target", "message"])
        self.assertEqual(create_followup_task_tool()["name"], "followup_task")
        self.assertIn("previous_status", create_close_agent_tool_v2()["output_schema"]["properties"])

    def test_wait_agent_parameters_use_configured_timeout_bounds(self) -> None:
        options = WaitAgentTimeoutOptions(default_timeout_ms=20, min_timeout_ms=10, max_timeout_ms=30)
        v1 = create_wait_agent_tool_v1(options)["tools"][0]
        self.assertEqual(v1["parameters"]["required"], ["targets"])
        self.assertIn("Defaults to 20, min 10, max 30", v1["parameters"]["properties"]["timeout_ms"]["description"])
        v2 = create_wait_agent_tool_v2(options)
        self.assertNotIn("required", v2["parameters"])
        self.assertIn("timed_out", v2["output_schema"]["properties"])

    def test_list_agents_and_collab_input_schema(self) -> None:
        self.assertIn("agents", create_list_agents_tool()["output_schema"]["properties"])
        items = create_collab_input_items_schema()
        self.assertEqual(items["type"], "array")
        self.assertIn("mention", items["items"]["properties"]["type"]["description"])

    def test_model_description_filters_picker_visible_models(self) -> None:
        description = spawn_agent_models_description(
            (
                {"model": "hidden", "description": "Hidden", "show_in_picker": False},
                {"model": "gpt-x", "description": "Fast", "show_in_picker": True},
            )
        )
        self.assertIn("gpt-x", description)
        self.assertNotIn("hidden", description)

    def test_options_reject_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            SpawnAgentToolOptions(available_models="gpt")
        with self.assertRaises(TypeError):
            WaitAgentTimeoutOptions(default_timeout_ms=True)


if __name__ == "__main__":
    unittest.main()
