import json
import unittest

from pycodex.core.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tool_context import ExecCommandToolOutput, ToolPayload
from pycodex.core.tool_registry import ToolInvocation
from pycodex.core.unified_exec_handler import (
    DEFAULT_EXEC_YIELD_TIME_MS,
    DEFAULT_WRITE_STDIN_YIELD_TIME_MS,
    ExecCommandArgs,
    ExecCommandEnvironmentArgs,
    ExecCommandHandler,
    UnifiedExecShellMode,
    WriteStdinArgs,
    WriteStdinHandler,
    ZshForkConfig,
    get_command,
)
from pycodex.protocol import SandboxPermissions, ToolName, TruncationPolicyConfig


class CoreUnifiedExecHandlerTests(unittest.TestCase):
    def test_exec_command_args_defaults_match_rust_handler(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello"}')
        self.assertEqual(args.cmd, "echo hello")
        self.assertFalse(args.tty)
        self.assertEqual(args.yield_time_ms, DEFAULT_EXEC_YIELD_TIME_MS)
        self.assertIsNone(args.max_output_tokens)
        self.assertEqual(args.sandbox_permissions, SandboxPermissions.USE_DEFAULT)

    def test_environment_args_keep_workdir_raw(self) -> None:
        args = ExecCommandEnvironmentArgs.from_json('{"environment_id":"env-1","workdir":"subdir"}')
        self.assertEqual(args.environment_id, "env-1")
        self.assertEqual(args.workdir, "subdir")

    def test_write_stdin_args_defaults_match_rust_handler(self) -> None:
        args = WriteStdinArgs.from_json('{"session_id":45}')
        self.assertEqual(args.session_id, 45)
        self.assertEqual(args.chars, "")
        self.assertEqual(args.yield_time_ms, DEFAULT_WRITE_STDIN_YIELD_TIME_MS)

    def test_get_command_uses_session_shell_when_unspecified(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello"}')
        resolved = get_command(args, Shell(ShellType.BASH, "/bin/bash"), allow_login_shell=True)
        self.assertEqual(resolved.command, ("/bin/bash", "-lc", "echo hello"))
        self.assertEqual(resolved.shell_type, ShellType.BASH)

    def test_get_command_rejects_explicit_login_when_disallowed(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello","login":true}')
        with self.assertRaisesRegex(ValueError, "login shell is disabled by config"):
            get_command(args, Shell(ShellType.BASH, "/bin/bash"), allow_login_shell=False)

    def test_get_command_ignores_explicit_shell_in_zsh_fork_mode(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello","shell":"/bin/bash"}')
        mode = UnifiedExecShellMode.zsh_fork(ZshForkConfig("/opt/codex/zsh"))
        resolved = get_command(args, Shell(ShellType.BASH, "/bin/bash"), mode, allow_login_shell=True)
        self.assertEqual(resolved.command, ("/opt/codex/zsh", "-lc", "echo hello"))
        self.assertEqual(resolved.shell_type, ShellType.ZSH)

    def test_exec_command_pre_hook_uses_raw_command_as_bash(self) -> None:
        invocation = ToolInvocation(
            call_id="call-43",
            tool_name=ToolName.plain("exec_command"),
            payload=ToolPayload.function('{"cmd":"printf exec command"}'),
        )
        payload = ExecCommandHandler().pre_tool_use_payload(invocation)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.tool_name, HookToolName.bash())
        self.assertEqual(payload.tool_input, {"command": "printf exec command"})

    def test_exec_command_with_updated_hook_input_rewrites_cmd_only(self) -> None:
        invocation = ToolInvocation(
            call_id="call-44",
            tool_name=ToolName.plain("exec_command"),
            payload=ToolPayload.function('{"cmd":"old","workdir":"/repo"}'),
        )
        updated = ExecCommandHandler().with_updated_hook_input(invocation, {"command": "new"})
        self.assertEqual(json.loads(updated.payload.arguments or ""), {"cmd": "new", "workdir": "/repo"})

    def test_post_hook_uses_completed_exec_output_and_bash_name(self) -> None:
        invocation = ToolInvocation(
            call_id="write-call",
            tool_name=ToolName.plain("write_stdin"),
            payload=ToolPayload.function('{"session_id":45,"chars":""}'),
        )
        output = ExecCommandToolOutput(
            event_call_id="exec-call-45",
            chunk_id="chunk-1",
            wall_time_seconds=0.498,
            raw_output=b"finished\n",
            truncation_policy=TruncationPolicyConfig.tokens(10_000),
            process_id=None,
            exit_code=0,
            hook_command="sleep 1; echo finished",
        )
        payload = WriteStdinHandler().post_tool_use_payload(invocation, output)
        self.assertIsNotNone(payload)
        self.assertEqual(payload.tool_name, HookToolName.bash())
        self.assertEqual(payload.tool_use_id, "exec-call-45")
        self.assertEqual(payload.tool_input, {"command": "sleep 1; echo finished"})
        self.assertEqual(payload.tool_response, "finished\n")

    def test_post_hook_skips_running_sessions(self) -> None:
        invocation = ToolInvocation(
            call_id="call-45",
            tool_name=ToolName.plain("exec_command"),
            payload=ToolPayload.function('{"cmd":"echo three"}'),
        )
        output = ExecCommandToolOutput(
            event_call_id="event-45",
            chunk_id="chunk-1",
            wall_time_seconds=0.498,
            raw_output=b"three",
            truncation_policy=TruncationPolicyConfig.tokens(10_000),
            process_id=45,
            hook_command="echo three",
        )
        self.assertIsNone(ExecCommandHandler().post_tool_use_payload(invocation, output))


if __name__ == "__main__":
    unittest.main()
