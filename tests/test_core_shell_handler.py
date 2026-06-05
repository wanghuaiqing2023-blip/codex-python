import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.exec import ExecCapturePolicy
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.handlers.shell import (
    ShellCommandBackend,
    ShellCommandBackendConfig,
    ShellCommandHandler,
    ShellCommandHandlerOptions,
    ShellCommandToolCallParams,
    shell_command_payload_command,
)
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.protocol import CODEX_THREAD_ID_ENV_VAR, SandboxPermissions, ShellEnvironmentPolicy, ShellEnvironmentPolicyInherit, ThreadId, ToolName


class CoreShellHandlerTests(unittest.TestCase):
    def test_shell_command_params_parse_required_command_and_defaults(self) -> None:
        params = ShellCommandToolCallParams.from_json('{"command":"printf shell command"}')
        self.assertEqual(params.command, "printf shell command")
        self.assertIsNone(params.workdir)
        self.assertIsNone(params.timeout_ms)
        self.assertIsNone(params.login)
        self.assertEqual(params.sandbox_permissions_or_default(), SandboxPermissions.USE_DEFAULT)

    def test_shell_command_payload_command_returns_raw_command(self) -> None:
        payload = ToolPayload.function('{"command":"printf shell command"}')
        self.assertEqual(shell_command_payload_command(payload), "printf shell command")

    def test_resolve_use_login_shell_rejects_disallowed_explicit_login(self) -> None:
        with self.assertRaisesRegex(FunctionCallError, "login shell is disabled by config") as err:
            ShellCommandHandler.resolve_use_login_shell(True, False)
        self.assertTrue(err.exception.is_model_response)
        self.assertFalse(ShellCommandHandler.resolve_use_login_shell(None, False))
        self.assertTrue(ShellCommandHandler.resolve_use_login_shell(None, True))

    def test_base_command_uses_shell_exec_args(self) -> None:
        command = ShellCommandHandler.base_command(Shell(ShellType.BASH, "/bin/bash"), "echo hi", True)
        self.assertEqual(command, ("/bin/bash", "-lc", "echo hi"))

    def test_to_exec_params_uses_session_shell_and_turn_context(self) -> None:
        thread_id = ThreadId.new()
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            set_values={"ONLY_VAR": "visible"},
        )
        turn = SimpleNamespace(
            cwd=Path("/repo"),
            shell_environment_policy=policy,
            network="net",
            windows_sandbox_level="restricted",
            config=SimpleNamespace(
                permissions=SimpleNamespace(windows_sandbox_private_desktop=True)
            ),
        )
        params = ShellCommandToolCallParams(
            command="echo hello",
            workdir="subdir",
            timeout_ms=1234,
            sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
            justification="because tests",
        )

        exec_params = ShellCommandHandler.to_exec_params(
            params,
            SimpleNamespace(user_shell=lambda: Shell(ShellType.BASH, "/bin/bash")),
            turn,
            thread_id,
            allow_login_shell=True,
        )

        self.assertEqual(exec_params.command, ("/bin/bash", "-lc", "echo hello"))
        self.assertEqual(exec_params.cwd, Path("/repo/subdir"))
        self.assertEqual(exec_params.expiration.timeout_ms(), 1234)
        self.assertEqual(exec_params.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertEqual(exec_params.env["ONLY_VAR"], "visible")
        self.assertEqual(exec_params.env[CODEX_THREAD_ID_ENV_VAR], thread_id.to_json())
        self.assertEqual(exec_params.network, "net")
        self.assertEqual(exec_params.sandbox_permissions, SandboxPermissions.REQUIRE_ESCALATED)
        self.assertEqual(exec_params.windows_sandbox_level, "restricted")
        self.assertTrue(exec_params.windows_sandbox_private_desktop)
        self.assertEqual(exec_params.justification, "because tests")
        self.assertIsNone(exec_params.arg0)

    def test_handler_backend_and_spec(self) -> None:
        handler = ShellCommandHandler(
            ShellCommandHandlerOptions(
                backend_config=ShellCommandBackendConfig.ZSH_FORK,
                allow_login_shell=True,
                exec_permission_approvals_enabled=True,
            )
        )
        self.assertEqual(handler.shell_runtime_backend(), ShellCommandBackend.ZSH_FORK)
        spec = handler.spec()
        self.assertEqual(spec["name"], "shell_command")
        self.assertIn("login", spec["parameters"]["properties"])
        self.assertTrue(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.waits_for_runtime_cancellation())

    def test_pre_tool_use_payload_uses_bash_hook(self) -> None:
        invocation = ToolInvocation(
            call_id="call-42",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function('{"command":"printf shell command"}'),
        )
        payload = ShellCommandHandler().pre_tool_use_payload(invocation)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.tool_name, HookToolName.bash())
        self.assertEqual(payload.tool_input, {"command": "printf shell command"})

    def test_with_updated_hook_input_rewrites_command_only(self) -> None:
        invocation = ToolInvocation(
            call_id="call-43",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function('{"command":"old","workdir":"/repo"}'),
        )
        updated = ShellCommandHandler().with_updated_hook_input(invocation, {"command": "new"})
        self.assertEqual(json.loads(updated.payload.arguments or ""), {"command": "new", "workdir": "/repo"})

    def test_with_updated_hook_input_uses_model_visible_errors(self) -> None:
        handler = ShellCommandHandler()
        with self.assertRaisesRegex(FunctionCallError, "unsupported shell_command payload") as unsupported:
            handler.with_updated_hook_input(
                ToolInvocation(
                    call_id="call-44",
                    tool_name=ToolName.plain("shell_command"),
                    payload=ToolPayload.custom("raw"),
                ),
                {"command": "new"},
            )
        self.assertTrue(unsupported.exception.is_model_response)

        with self.assertRaisesRegex(FunctionCallError, "updated hook input command must be a string") as bad_command:
            handler.with_updated_hook_input(
                ToolInvocation(
                    call_id="call-45",
                    tool_name=ToolName.plain("shell_command"),
                    payload=ToolPayload.function('{"command":"old"}'),
                ),
                {"command": 1},
            )
        self.assertTrue(bad_command.exception.is_model_response)

    def test_post_tool_use_payload_uses_tool_output_wire_value(self) -> None:
        invocation = ToolInvocation(
            call_id="call-42",
            tool_name=ToolName.plain("shell_command"),
            payload=ToolPayload.function('{"command":"printf shell command"}'),
        )
        output = FunctionToolOutput(body=(), success=True, post_tool_use_response_value="shell output")
        payload = ShellCommandHandler().post_tool_use_payload(invocation, output)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.tool_name, HookToolName.bash())
        self.assertEqual(payload.tool_use_id, "call-42")
        self.assertEqual(payload.tool_input, {"command": "printf shell command"})
        self.assertEqual(payload.tool_response, "shell output")


if __name__ == "__main__":
    unittest.main()
