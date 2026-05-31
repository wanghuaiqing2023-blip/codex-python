import unittest

from pycodex.core.shell_spec import (
    CommandToolOptions,
    create_approval_parameters,
    create_exec_command_tool,
    create_exec_command_tool_with_environment_id,
    create_request_permissions_tool,
    create_shell_command_tool,
    create_write_stdin_tool,
    permission_profile_schema,
    request_permissions_tool_description,
    unified_exec_output_schema,
)


class CoreShellSpecTests(unittest.TestCase):
    def test_exec_command_tool_matches_expected_shape(self) -> None:
        tool = create_exec_command_tool(CommandToolOptions(True, False))
        self.assertEqual(tool["name"], "exec_command")
        self.assertIsNone(tool["defer_loading"])
        self.assertEqual(tool["parameters"]["required"], ["cmd"])
        self.assertIn("login", tool["parameters"]["properties"])
        self.assertIn("sandbox_permissions", tool["parameters"]["properties"])
        self.assertFalse(tool["parameters"]["additionalProperties"])
        self.assertEqual(tool["output_schema"], unified_exec_output_schema())

    def test_exec_command_can_include_environment_id_and_additional_permissions(self) -> None:
        tool = create_exec_command_tool_with_environment_id(CommandToolOptions(False, True), True)
        properties = tool["parameters"]["properties"]
        self.assertIn("environment_id", properties)
        self.assertNotIn("login", properties)
        self.assertIn("additional_permissions", properties)

    def test_write_stdin_tool_matches_expected_shape(self) -> None:
        tool = create_write_stdin_tool()
        self.assertEqual(tool["name"], "write_stdin")
        self.assertIsNone(tool["defer_loading"])
        self.assertEqual(tool["parameters"]["required"], ["session_id"])
        self.assertFalse(tool["parameters"]["additionalProperties"])
        self.assertEqual(tool["output_schema"]["required"], ["wall_time_seconds", "output"])

    def test_shell_command_tool_uses_legacy_command_required_field(self) -> None:
        tool = create_shell_command_tool(CommandToolOptions(True, False))
        self.assertEqual(tool["name"], "shell_command")
        self.assertEqual(tool["parameters"]["required"], ["command"])
        self.assertIn("login", tool["parameters"]["properties"])

    def test_request_permissions_tool_includes_full_permission_schema(self) -> None:
        description = request_permissions_tool_description()
        tool = create_request_permissions_tool(description)
        self.assertEqual(tool["name"], "request_permissions")
        self.assertIsNone(tool["defer_loading"])
        self.assertIsNone(tool["output_schema"])
        self.assertEqual(tool["description"], description)
        self.assertEqual(tool["parameters"]["required"], ["permissions"])
        self.assertEqual(tool["parameters"]["properties"]["permissions"], permission_profile_schema())
        self.assertFalse(tool["parameters"]["additionalProperties"])

    def test_approval_parameters_switch_additional_permissions(self) -> None:
        disabled = create_approval_parameters(False)
        enabled = create_approval_parameters(True)
        self.assertNotIn("additional_permissions", disabled)
        self.assertIn("additional_permissions", enabled)
        self.assertIn("with_additional_permissions", enabled["sandbox_permissions"]["description"])

    def test_options_reject_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            CommandToolOptions(allow_login_shell=1, exec_permission_approvals_enabled=False)
        with self.assertRaises(TypeError):
            create_approval_parameters(1)


if __name__ == "__main__":
    unittest.main()
