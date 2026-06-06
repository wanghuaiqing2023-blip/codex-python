import sys
import unittest

from pycodex.core.tools.handlers.shell_spec import (
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
    windows_shell_guidance,
)


class CoreShellSpecTests(unittest.TestCase):
    # Rust source:
    # codex/codex-rs/core/src/tools/handlers/shell_spec.rs
    # Rust tests:
    # codex/codex-rs/core/src/tools/handlers/shell_spec_tests.rs

    def test_unified_exec_output_schema_matches_rust_contract(self) -> None:
        # Rust behavior source: shell_spec.rs unified_exec_output_schema.
        self.assertEqual(
            unified_exec_output_schema(),
            {
                "type": "object",
                "properties": {
                    "chunk_id": {
                        "type": "string",
                        "description": "Chunk identifier included when the response reports one.",
                    },
                    "wall_time_seconds": {
                        "type": "number",
                        "description": "Elapsed wall time spent waiting for output in seconds.",
                    },
                    "exit_code": {
                        "type": "number",
                        "description": "Process exit code when the command finished during this call.",
                    },
                    "session_id": {
                        "type": "number",
                        "description": "Session identifier to pass to write_stdin when the process is still running.",
                    },
                    "original_token_count": {
                        "type": "number",
                        "description": "Approximate token count before output truncation.",
                    },
                    "output": {
                        "type": "string",
                        "description": "Command output text, possibly truncated.",
                    },
                },
                "required": ["wall_time_seconds", "output"],
                "additionalProperties": False,
            },
        )

    def test_approval_parameters_match_rust_permission_contract(self) -> None:
        # Rust behavior source: shell_spec.rs create_approval_parameters.
        common = {
            "justification": {
                "type": "string",
                "description": (
                    'Only set if sandbox_permissions is \\"require_escalated\\".\n'
                    "                    Request approval from the user to run this command outside the sandbox.\n"
                    "                    Phrased as a simple question that summarizes the purpose of the\n"
                    "                    command as it relates to the task at hand - e.g. 'Do you want to\n"
                    "                    fetch and pull the latest version of this git branch?'"
                ),
            },
            "prefix_rule": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Only specify when sandbox_permissions is `require_escalated`.\n"
                    "                        Suggest a prefix command pattern that will allow you to fulfill similar requests from the user in the future.\n"
                    '                        Should be a short but reasonable prefix, e.g. [\\"git\\", \\"pull\\"] or [\\"uv\\", \\"run\\"] or [\\"pytest\\"].'
                ),
            },
        }
        disabled = {
            "sandbox_permissions": {
                "type": "string",
                "description": 'Sandbox permissions for the command. Set to "require_escalated" to request running without sandbox restrictions; defaults to "use_default".',
            },
            **common,
        }
        enabled = {
            "sandbox_permissions": {
                "type": "string",
                "description": 'Sandbox permissions for the command. Use "with_additional_permissions" to request additional sandboxed filesystem or network permissions (preferred), or "require_escalated" to request running without sandbox restrictions; defaults to "use_default".',
            },
            **common,
            "additional_permissions": permission_profile_schema(),
        }
        self.assertEqual(create_approval_parameters(False), disabled)
        self.assertEqual(create_approval_parameters(True), enabled)

    def test_permission_profile_schema_matches_rust_contract(self) -> None:
        # Rust behavior source: shell_spec.rs permission_profile_schema.
        self.assertEqual(
            permission_profile_schema(),
            {
                "type": "object",
                "properties": {
                    "network": {
                        "type": "object",
                        "properties": {
                            "enabled": {
                                "type": "boolean",
                                "description": "Set to true to request network access.",
                            }
                        },
                        "additionalProperties": False,
                    },
                    "file_system": {
                        "type": "object",
                        "properties": {
                            "read": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Absolute paths to grant read access to.",
                            },
                            "write": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Absolute paths to grant write access to.",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        )

    def test_exec_command_tool_matches_expected_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_exec_command_tool
        # Rust test: shell_spec_tests.rs::exec_command_tool_matches_expected_spec
        tool = create_exec_command_tool(CommandToolOptions(True, False))
        self.assertEqual(tool["name"], "exec_command")
        self.assertIsNone(tool["defer_loading"])
        self.assertEqual(tool["parameters"]["required"], ["cmd"])
        self.assertIn("login", tool["parameters"]["properties"])
        self.assertIn("sandbox_permissions", tool["parameters"]["properties"])
        self.assertFalse(tool["parameters"]["additionalProperties"])
        self.assertEqual(tool["output_schema"], unified_exec_output_schema())

    def test_exec_command_tool_matches_rust_unit_expected_spec(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_exec_command_tool
        # Rust test: shell_spec_tests.rs::exec_command_tool_matches_expected_spec
        description = "Runs a command in a PTY, returning output or a session ID for ongoing interaction."
        if sys.platform.startswith("win"):
            description = f"{description}\n\n{windows_shell_guidance()}"
        properties = {
            "cmd": {"type": "string", "description": "Shell command to execute."},
            "workdir": {
                "type": "string",
                "description": "Optional working directory to run the command in; defaults to the turn cwd.",
            },
            "shell": {
                "type": "string",
                "description": "Shell binary to launch. Defaults to the user's default shell.",
            },
            "tty": {
                "type": "boolean",
                "description": "Whether to allocate a TTY for the command. Defaults to false (plain pipes); set to true to open a PTY and access TTY process.",
            },
            "yield_time_ms": {
                "type": "number",
                "description": "How long to wait (in milliseconds) for output before yielding.",
            },
            "max_output_tokens": {
                "type": "number",
                "description": "Maximum number of tokens to return. Excess output will be truncated.",
            },
            "login": {
                "type": "boolean",
                "description": "Whether to run the shell with -l/-i semantics. Defaults to true.",
            },
        }
        properties.update(create_approval_parameters(False))
        self.assertEqual(
            create_exec_command_tool(CommandToolOptions(True, False)),
            {
                "type": "function",
                "name": "exec_command",
                "description": description,
                "strict": False,
                "defer_loading": None,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": ["cmd"],
                    "additionalProperties": False,
                },
                "output_schema": unified_exec_output_schema(),
            },
        )

    def test_exec_command_can_include_environment_id_and_additional_permissions(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_exec_command_tool_with_environment_id
        # Rust contract: environment_id and additional_permissions are gated by independent options.
        tool = create_exec_command_tool_with_environment_id(CommandToolOptions(False, True), True)
        properties = tool["parameters"]["properties"]
        self.assertEqual(
            properties["environment_id"],
            {
                "type": "string",
                "description": "Optional environment id from the <environment_context> block. If omitted, uses the primary environment.",
            },
        )
        self.assertNotIn("login", properties)
        self.assertEqual(properties["additional_permissions"], permission_profile_schema())

        without_environment = create_exec_command_tool_with_environment_id(
            CommandToolOptions(False, True),
            False,
        )
        self.assertNotIn("environment_id", without_environment["parameters"]["properties"])

    def test_write_stdin_tool_matches_expected_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_write_stdin_tool
        # Rust test: shell_spec_tests.rs::write_stdin_tool_matches_expected_spec
        tool = create_write_stdin_tool()
        self.assertEqual(tool["name"], "write_stdin")
        self.assertIsNone(tool["defer_loading"])
        self.assertEqual(tool["parameters"]["required"], ["session_id"])
        self.assertFalse(tool["parameters"]["additionalProperties"])
        self.assertEqual(tool["output_schema"]["required"], ["wall_time_seconds", "output"])

    def test_write_stdin_tool_matches_rust_unit_expected_spec(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_write_stdin_tool
        # Rust test: shell_spec_tests.rs::write_stdin_tool_matches_expected_spec
        self.assertEqual(
            create_write_stdin_tool(),
            {
                "type": "function",
                "name": "write_stdin",
                "description": "Writes characters to an existing unified exec session and returns recent output.",
                "strict": False,
                "defer_loading": None,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "number",
                            "description": "Identifier of the running unified exec session.",
                        },
                        "chars": {
                            "type": "string",
                            "description": "Bytes to write to stdin (may be empty to poll).",
                        },
                        "yield_time_ms": {
                            "type": "number",
                            "description": "How long to wait (in milliseconds) for output before yielding.",
                        },
                        "max_output_tokens": {
                            "type": "number",
                            "description": "Maximum number of tokens to return. Excess output will be truncated.",
                        },
                    },
                    "required": ["session_id"],
                    "additionalProperties": False,
                },
                "output_schema": unified_exec_output_schema(),
            },
        )

    def test_shell_command_tool_uses_legacy_command_required_field(self) -> None:
        tool = create_shell_command_tool(CommandToolOptions(True, False))
        self.assertEqual(tool["name"], "shell_command")
        self.assertEqual(tool["parameters"]["required"], ["command"])
        self.assertIn("login", tool["parameters"]["properties"])

    def test_shell_command_tool_matches_rust_unit_expected_spec(self) -> None:
        # Rust test source: shell_command_tool_matches_expected_spec.
        if sys.platform.startswith("win"):
            description = (
                "Runs a Powershell command (Windows) and returns its output.\n\n"
                "Examples of valid command strings:\n\n"
                '- ls -a (show hidden): "Get-ChildItem -Force"\n'
                '- recursive find by name: "Get-ChildItem -Recurse -Filter *.py"\n'
                "- recursive grep: \"Get-ChildItem -Path C:\\\\myrepo -Recurse | Select-String -Pattern 'TODO' -CaseSensitive\"\n"
                '- ps aux | grep python: "Get-Process | Where-Object { $_.ProcessName -like \'*python*\' }"\n'
                '- setting an env var: "$env:FOO=\'bar\'; echo $env:FOO"\n'
                '- running an inline Python script: "@\'\\\\nprint(\'Hello, world!\')\\\\n\'@ | python -"\n\n'
                f"{windows_shell_guidance()}"
            )
        else:
            description = (
                "Runs a shell command and returns its output.\n"
                "- Always set the `workdir` param when using the shell_command function. Do not use `cd` unless absolutely necessary."
            )
        properties = {
            "command": {
                "type": "string",
                "description": "The shell script to execute in the user's default shell",
            },
            "workdir": {
                "type": "string",
                "description": "The working directory to execute the command in",
            },
            "timeout_ms": {
                "type": "number",
                "description": "The timeout for the command in milliseconds",
            },
            "login": {
                "type": "boolean",
                "description": "Whether to run the shell with login shell semantics. Defaults to true.",
            },
        }
        properties.update(create_approval_parameters(False))
        self.assertEqual(
            create_shell_command_tool(CommandToolOptions(True, False)),
            {
                "type": "function",
                "name": "shell_command",
                "description": description,
                "strict": False,
                "defer_loading": None,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        )

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
