import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tool_context import ExecCommandToolOutput, ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.core.tool_registry import ToolInvocation
from pycodex.core.unified_exec_handler import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    DEFAULT_EXEC_YIELD_TIME_MS,
    DEFAULT_WRITE_STDIN_YIELD_TIME_MS,
    ExecCommandArgs,
    ExecCommandEnvironmentArgs,
    ExecCommandHandler,
    ExecCommandHandlerOptions,
    UnifiedExecShellMode,
    WriteStdinArgs,
    WriteStdinHandler,
    WriteStdinRequest,
    ZshForkConfig,
    clamp_yield_time,
    get_command,
    intercept_exec_apply_patch,
    resolve_exec_command_invocation,
    resolve_write_stdin_yield_time,
)
from pycodex.protocol import SandboxPermissions, TerminalInteractionEvent, ToolName, TruncationPolicyConfig


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

    def test_unified_exec_yield_time_clamps_match_rust_manager(self) -> None:
        self.assertEqual(clamp_yield_time(1), 250)
        self.assertEqual(clamp_yield_time(500), 500)
        self.assertEqual(clamp_yield_time(60_000), 30_000)
        self.assertEqual(resolve_write_stdin_yield_time("input", 1), 250)
        self.assertEqual(resolve_write_stdin_yield_time("", 1), 5_000)
        self.assertEqual(
            resolve_write_stdin_yield_time("", 600_000),
            DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
        )

    def test_unified_exec_numeric_bounds_match_rust_deserialization(self) -> None:
        with self.assertRaisesRegex(ValueError, "yield_time_ms must fit in u64"):
            ExecCommandArgs.from_json('{"cmd":"echo hi","yield_time_ms":-1}')
        with self.assertRaisesRegex(ValueError, "max_output_tokens must fit in usize"):
            ExecCommandArgs.from_json('{"cmd":"echo hi","max_output_tokens":-1}')
        with self.assertRaisesRegex(ValueError, "session_id must fit in i32"):
            WriteStdinArgs.from_json('{"session_id":2147483648}')
        with self.assertRaisesRegex(ValueError, "yield_time_ms must fit in u64"):
            WriteStdinArgs.from_json('{"session_id":45,"yield_time_ms":-1}')
        with self.assertRaisesRegex(ValueError, "max_output_tokens must fit in usize"):
            WriteStdinArgs.from_json('{"session_id":45,"max_output_tokens":-1}')

    def test_write_stdin_handler_forwards_request_to_unified_exec_manager(self) -> None:
        class Manager:
            def __init__(self) -> None:
                self.request = None

            async def write_stdin(self, request: WriteStdinRequest) -> ExecCommandToolOutput:
                self.request = request
                return ExecCommandToolOutput(
                    event_call_id="event-stdin",
                    chunk_id="chunk-stdin",
                    wall_time_seconds=0.1,
                    raw_output=b"continued\n",
                    truncation_policy=request.truncation_policy,
                    process_id=None,
                    exit_code=0,
                    hook_command="python child.py",
                )

        manager = Manager()
        invocation = ToolInvocation(
            call_id="call-stdin",
            tool_name="write_stdin",
            payload=ToolPayload.function(
                json.dumps(
                    {
                        "session_id": 45,
                        "chars": "hello\n",
                        "yield_time_ms": 1,
                        "max_output_tokens": 12,
                    }
                )
            ),
            session=SimpleNamespace(
                services=SimpleNamespace(unified_exec_manager=manager)
            ),
            turn=SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123)),
        )

        output = asyncio.run(WriteStdinHandler().handle(invocation))

        self.assertIsInstance(output, ExecCommandToolOutput)
        self.assertIsNotNone(manager.request)
        self.assertEqual(manager.request.process_id, 45)
        self.assertEqual(manager.request.input, "hello\n")
        self.assertEqual(manager.request.yield_time_ms, 250)
        self.assertEqual(manager.request.max_output_tokens, 12)
        self.assertEqual(manager.request.truncation_policy, TruncationPolicyConfig.tokens(123))

    def test_write_stdin_handler_emits_terminal_interaction_for_visible_input(self) -> None:
        class Manager:
            async def write_stdin(self, request: WriteStdinRequest) -> ExecCommandToolOutput:
                return ExecCommandToolOutput(
                    event_call_id="exec-call-45",
                    chunk_id="chunk-stdin",
                    wall_time_seconds=0.1,
                    raw_output=b"",
                    truncation_policy=request.truncation_policy,
                    process_id=None,
                    exit_code=0,
                    hook_command="python child.py",
                )

        class Session:
            def __init__(self) -> None:
                self.services = SimpleNamespace(unified_exec_manager=Manager())
                self.events = []

            async def send_event(self, turn: object, event: object) -> None:
                self.events.append((turn, event))

        turn = SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123))
        session = Session()
        invocation = ToolInvocation(
            call_id="write-call",
            tool_name="write_stdin",
            payload=ToolPayload.function(
                json.dumps({"session_id": 45, "chars": "hello\n", "yield_time_ms": 250})
            ),
            session=session,
            turn=turn,
        )

        asyncio.run(WriteStdinHandler().handle(invocation))

        self.assertEqual(len(session.events), 1)
        self.assertIs(session.events[0][0], turn)
        event = session.events[0][1]
        self.assertEqual(event.type, "terminal_interaction")
        self.assertIsInstance(event.payload, TerminalInteractionEvent)
        self.assertEqual(event.payload.call_id, "exec-call-45")
        self.assertEqual(event.payload.process_id, "45")
        self.assertEqual(event.payload.stdin, "hello\n")

    def test_write_stdin_handler_skips_completed_empty_poll_terminal_interaction(self) -> None:
        class Manager:
            async def write_stdin(self, request: WriteStdinRequest) -> ExecCommandToolOutput:
                return ExecCommandToolOutput(
                    event_call_id="exec-call-45",
                    chunk_id="chunk-stdin",
                    wall_time_seconds=0.1,
                    raw_output=b"done\n",
                    truncation_policy=request.truncation_policy,
                    process_id=None,
                    exit_code=0,
                    hook_command="python child.py",
                )

        class Session:
            def __init__(self) -> None:
                self.services = SimpleNamespace(unified_exec_manager=Manager())
                self.events = []

            async def send_event(self, turn: object, event: object) -> None:
                self.events.append((turn, event))

        invocation = ToolInvocation(
            call_id="write-call",
            tool_name="write_stdin",
            payload=ToolPayload.function(json.dumps({"session_id": 45, "chars": ""})),
            session=Session(),
            turn=SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123)),
        )

        asyncio.run(WriteStdinHandler().handle(invocation))

        self.assertEqual(invocation.session.events, [])

    def test_write_stdin_handler_emits_terminal_interaction_for_live_empty_poll(self) -> None:
        class Manager:
            async def write_stdin(self, request: WriteStdinRequest) -> ExecCommandToolOutput:
                return ExecCommandToolOutput(
                    event_call_id="exec-call-46",
                    chunk_id="chunk-stdin",
                    wall_time_seconds=0.1,
                    raw_output=b"still running\n",
                    truncation_policy=request.truncation_policy,
                    process_id=46,
                    hook_command="python child.py",
                )

        class Session:
            def __init__(self) -> None:
                self.services = SimpleNamespace(unified_exec_manager=Manager())
                self.events = []

            async def send_event(self, turn: object, event: object) -> None:
                self.events.append((turn, event))

        invocation = ToolInvocation(
            call_id="write-call",
            tool_name="write_stdin",
            payload=ToolPayload.function(json.dumps({"session_id": 45, "chars": ""})),
            session=Session(),
            turn=SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123)),
        )

        asyncio.run(WriteStdinHandler().handle(invocation))

        self.assertEqual(len(invocation.session.events), 1)
        event = invocation.session.events[0][1]
        self.assertEqual(event.type, "terminal_interaction")
        self.assertIsInstance(event.payload, TerminalInteractionEvent)
        self.assertEqual(event.payload.call_id, "exec-call-46")
        self.assertEqual(event.payload.process_id, "46")
        self.assertEqual(event.payload.stdin, "")

    def test_write_stdin_handler_wraps_manager_errors(self) -> None:
        class Manager:
            def write_stdin(self, _request: WriteStdinRequest) -> None:
                raise RuntimeError("missing session")

        invocation = ToolInvocation(
            call_id="call-stdin-error",
            tool_name="write_stdin",
            payload=ToolPayload.function(json.dumps({"session_id": 45})),
            session=SimpleNamespace(
                services=SimpleNamespace(unified_exec_manager=Manager())
            ),
            turn=SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123)),
        )

        with self.assertRaisesRegex(Exception, "write_stdin failed: missing session"):
            asyncio.run(WriteStdinHandler().handle(invocation))

    def test_write_stdin_handler_maps_bad_arguments_to_model_error(self) -> None:
        invocation = ToolInvocation(
            call_id="call-stdin-bad-args",
            tool_name="write_stdin",
            payload=ToolPayload.function(json.dumps({"session_id": "bad"})),
            session=SimpleNamespace(
                services=SimpleNamespace(unified_exec_manager=object())
            ),
            turn=SimpleNamespace(truncation_policy=TruncationPolicyConfig.tokens(123)),
        )

        with self.assertRaises(FunctionCallError) as error:
            asyncio.run(WriteStdinHandler().handle(invocation))

        self.assertIn("failed to parse function arguments:", str(error.exception))
        self.assertIn("session_id must be an integer", str(error.exception))

    def test_get_command_uses_session_shell_when_unspecified(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello"}')
        resolved = get_command(args, Shell(ShellType.BASH, "/bin/bash"), allow_login_shell=True)
        self.assertEqual(resolved.command, (str(Path("/bin/bash")), "-lc", "echo hello"))
        self.assertEqual(resolved.shell_type, ShellType.BASH)

    def test_get_command_rejects_explicit_login_when_disallowed(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello","login":true}')
        with self.assertRaisesRegex(ValueError, "login shell is disabled by config"):
            get_command(args, Shell(ShellType.BASH, "/bin/bash"), allow_login_shell=False)

    def test_get_command_ignores_explicit_shell_in_zsh_fork_mode(self) -> None:
        args = ExecCommandArgs.from_json('{"cmd":"echo hello","shell":"/bin/bash"}')
        mode = UnifiedExecShellMode.zsh_fork(ZshForkConfig("/opt/codex/zsh"))
        resolved = get_command(args, Shell(ShellType.BASH, "/bin/bash"), mode, allow_login_shell=True)
        self.assertEqual(resolved.command, (str(Path("/opt/codex/zsh")), "-lc", "echo hello"))
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

    def test_resolve_exec_command_invocation_uses_selected_environment_cwd(self) -> None:
        remote = SimpleNamespace(environment_id="remote", cwd=Path("/remote"))
        invocation = ToolInvocation(
            call_id="call-remote",
            tool_name=ToolName.plain("exec_command"),
            payload=ToolPayload.function(
                json.dumps(
                    {
                        "cmd": "pwd",
                        "environment_id": "remote",
                        "workdir": "project",
                    }
                )
            ),
            turn=SimpleNamespace(
                environments=(
                    SimpleNamespace(environment_id="local", cwd=Path("/local")),
                    remote,
                )
            ),
        )

        resolved = resolve_exec_command_invocation(
            invocation,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
        )

        self.assertIs(resolved.turn_environment, remote)
        self.assertEqual(resolved.cwd, Path("/remote/project"))
        self.assertEqual(resolved.environment_args.environment_id, "remote")
        self.assertEqual(resolved.args.cmd, "pwd")
        self.assertEqual(resolved.resolved_command.command, (str(Path("/bin/bash")), "-c", "pwd"))

    def test_resolve_exec_command_invocation_defaults_to_primary_environment(self) -> None:
        primary = SimpleNamespace(environment_id="local", cwd=Path("/local"))
        invocation = ToolInvocation(
            call_id="call-local",
            tool_name="exec_command",
            payload=ToolPayload.function(json.dumps({"cmd": "pwd"})),
            turn=SimpleNamespace(environments=(primary,)),
        )

        resolved = resolve_exec_command_invocation(
            invocation,
            session_shell=Shell(ShellType.BASH, "/bin/bash"),
        )

        self.assertIs(resolved.turn_environment, primary)
        self.assertEqual(resolved.cwd, Path("/local"))

        missing_environment = ToolInvocation(
            call_id="call-none",
            tool_name="exec_command",
            payload=ToolPayload.function(json.dumps({"cmd": "pwd"})),
            turn=SimpleNamespace(environments=()),
        )
        with self.assertRaisesRegex(ValueError, "unified exec is unavailable"):
            resolve_exec_command_invocation(missing_environment)

    def test_exec_command_handler_runs_in_selected_environment_workdir(self) -> None:
        shell, command = self.local_shell_and_pwd_command()
        with tempfile.TemporaryDirectory() as local_dir, tempfile.TemporaryDirectory() as remote_dir:
            local_root = Path(local_dir)
            remote_root = Path(remote_dir)
            child = remote_root / "child"
            child.mkdir()
            invocation = ToolInvocation(
                call_id="call-run",
                tool_name="exec_command",
                payload=ToolPayload.function(
                    json.dumps(
                        {
                            "cmd": command,
                            "environment_id": "remote",
                            "workdir": "child",
                        }
                    )
                ),
                session=SimpleNamespace(user_shell=lambda: shell),
                turn=SimpleNamespace(
                    environments=(
                        SimpleNamespace(environment_id="local", cwd=local_root),
                        SimpleNamespace(environment_id="remote", cwd=remote_root),
                    )
                ),
            )

            output = ExecCommandHandler(
                ExecCommandHandlerOptions(include_environment_id=True)
            ).handle(invocation)

            self.assertEqual(output.exit_code, 0)
            self.assertIn(str(child), output.raw_output.decode("utf-8", errors="replace"))
            self.assertEqual(output.hook_command, command)

    def test_exec_command_handler_returns_nonzero_output(self) -> None:
        shell, command = self.local_shell_and_failure_command()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invocation = ToolInvocation(
                call_id="call-fail",
                tool_name="exec_command",
                payload=ToolPayload.function(json.dumps({"cmd": command})),
                session=SimpleNamespace(user_shell=lambda: shell),
                turn=SimpleNamespace(environments=(SimpleNamespace(environment_id="local", cwd=root),)),
            )

            output = ExecCommandHandler().handle(invocation)

            self.assertEqual(output.exit_code, 7)
            self.assertIn("pycodex-fail", output.raw_output.decode("utf-8", errors="replace"))

    def test_exec_command_handler_maps_bad_arguments_to_model_error(self) -> None:
        invocation = ToolInvocation(
            call_id="call-bad-args",
            tool_name="exec_command",
            payload=ToolPayload.function(json.dumps({"cmd": 123})),
            turn=SimpleNamespace(environments=(SimpleNamespace(environment_id="local", cwd=Path.cwd()),)),
        )

        with self.assertRaises(FunctionCallError) as error:
            ExecCommandHandler().handle(invocation)

        self.assertIn("failed to parse function arguments:", str(error.exception))
        self.assertIn("cmd must be a string", str(error.exception))

    def test_intercept_exec_apply_patch_applies_direct_patch_without_spawning_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch = (
                "*** Begin Patch\n"
                "*** Add File: added.txt\n"
                "+hello\n"
                "*** End Patch"
            )

            output = intercept_exec_apply_patch(("apply_patch", patch), root)

            self.assertEqual((root / "added.txt").read_text(encoding="utf-8"), "hello\n")
            self.assertEqual(
                output,
                "Success. Updated the following files:\n"
                f"A {root / 'added.txt'}\n",
            )

    def test_exec_command_handler_intercepts_apply_patch_shell_command(self) -> None:
        sh_path = shutil.which("sh")
        if sh_path is None:
            self.skipTest("sh is unavailable for portable heredoc interception test")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = (
                "apply_patch <<'PATCH'\n"
                "*** Begin Patch\n"
                "*** Add File: added.txt\n"
                "+hello\n"
                "*** End Patch\n"
                "PATCH"
            )
            invocation = ToolInvocation(
                call_id="call-apply-patch",
                tool_name="exec_command",
                payload=ToolPayload.function(json.dumps({"cmd": command})),
                session=SimpleNamespace(user_shell=lambda: Shell(ShellType.SH, sh_path)),
                turn=SimpleNamespace(environments=(SimpleNamespace(environment_id="local", cwd=root),)),
            )

            output = ExecCommandHandler().handle(invocation)

            self.assertIsNone(output.exit_code)
            self.assertEqual((root / "added.txt").read_text(encoding="utf-8"), "hello\n")
            self.assertIn("Success. Updated the following files:", output.raw_output.decode("utf-8"))

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

    def local_shell_and_pwd_command(self) -> tuple[Shell, str]:
        if sys.platform == "win32":
            return Shell(ShellType.POWERSHELL, shutil.which("powershell") or "powershell.exe"), "(Get-Location).Path"
        return Shell(ShellType.SH, shutil.which("sh") or "/bin/sh"), "pwd"

    def local_shell_and_failure_command(self) -> tuple[Shell, str]:
        if sys.platform == "win32":
            return (
                Shell(ShellType.POWERSHELL, shutil.which("powershell") or "powershell.exe"),
                "Write-Error 'pycodex-fail'; exit 7",
            )
        return Shell(ShellType.SH, shutil.which("sh") or "/bin/sh"), "echo pycodex-fail >&2; exit 7"


if __name__ == "__main__":
    unittest.main()
