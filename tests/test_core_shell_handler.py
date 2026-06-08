import json
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.exec import ExecCapturePolicy, ExecExpiration, ExecParams
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.handlers.shell import (
    ShellCommandBackend,
    ShellCommandBackendConfig,
    ShellCommandHandler,
    ShellCommandHandlerOptions,
    ShellCommandInvocationRequest,
    ShellCommandToolCallParams,
    RunExecLikeArgs,
    build_shell_request,
    run_exec_like,
    shell_command_payload_command,
)
from pycodex.core.tools.handlers.utils import EffectiveAdditionalPermissions
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.protocol import (
    CODEX_THREAD_ID_ENV_VAR,
    AskForApproval,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    SandboxPermissions,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    ThreadId,
    ToolName,
)


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
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs
        # Rust tests: shell_command_handler_rejects_login_when_disallowed and
        # shell_command_handler_defaults_to_non_login_when_disallowed.
        with self.assertRaisesRegex(FunctionCallError, "login shell is disabled by config") as err:
            ShellCommandHandler.resolve_use_login_shell(True, False)
        self.assertTrue(err.exception.is_model_response)
        self.assertFalse(ShellCommandHandler.resolve_use_login_shell(None, False))
        self.assertTrue(ShellCommandHandler.resolve_use_login_shell(None, True))

    def test_base_command_uses_shell_exec_args(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs
        # Rust test: shell_command_handler_respects_explicit_login_flag.
        command = ShellCommandHandler.base_command(Shell(ShellType.BASH, "/bin/bash"), "echo hi", True)
        self.assertEqual(command, ("/bin/bash", "-lc", "echo hi"))

    def test_to_exec_params_uses_session_shell_and_turn_context(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs
        # Rust test: shell_command_handler_to_exec_params_uses_session_shell_and_turn_context.
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

    def test_build_shell_request_uses_default_exec_policy_sandbox_for_preapproved_permissions(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell.rs
        # Behavior anchor: run_exec_like passes SandboxPermissions::UseDefault
        # into ExecApprovalRequest when effective additional permissions are
        # already preapproved, while ShellRequest retains the effective runtime
        # sandbox permissions.
        thread_id = ThreadId.new()
        exec_params = ShellCommandHandler.to_exec_params(
            ShellCommandToolCallParams(command="echo hello"),
            SimpleNamespace(user_shell=lambda: Shell(ShellType.BASH, "/bin/bash")),
            SimpleNamespace(cwd=Path("/repo"), shell_environment_policy=ShellEnvironmentPolicy.default()),
            thread_id,
            allow_login_shell=False,
        )
        granular = GranularApprovalConfig(
            sandbox_approval=False,
            rules=True,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=True,
        )

        preapproved = build_shell_request(
            exec_params,
            hook_command="echo hello",
            shell_type=ShellType.BASH,
            effective_additional_permissions=EffectiveAdditionalPermissions(
                SandboxPermissions.REQUIRE_ESCALATED,
                permissions_preapproved=True,
            ),
            normalized_additional_permissions=None,
            approval_policy=granular,
            permission_profile=PermissionProfile.workspace_write(),
            file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
            sandbox_cwd=Path("/repo"),
        )
        not_preapproved = build_shell_request(
            exec_params,
            hook_command="echo hello",
            shell_type=ShellType.BASH,
            effective_additional_permissions=EffectiveAdditionalPermissions(
                SandboxPermissions.REQUIRE_ESCALATED,
                permissions_preapproved=False,
            ),
            normalized_additional_permissions=None,
            approval_policy=granular,
            permission_profile=PermissionProfile.workspace_write(),
            file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
            sandbox_cwd=Path("/repo"),
        )

        self.assertEqual(preapproved.sandbox_permissions, SandboxPermissions.REQUIRE_ESCALATED)
        self.assertTrue(preapproved.additional_permissions_preapproved)
        self.assertEqual(preapproved.exec_approval_requirement.type, "skip")
        self.assertEqual(not_preapproved.exec_approval_requirement.type, "forbidden")

    def test_build_shell_request_preserves_full_buffer_capture_policy(self) -> None:
        # Rust source: codex-rs/core/src/exec.rs::build_exec_request.
        # Rust test: codex-rs/core/src/exec_tests.rs::process_exec_tool_call_preserves_full_buffer_capture_policy.
        exec_params = ExecParams(
            command=("/bin/bash", "-lc", "printf hello"),
            cwd=Path("/repo"),
            expiration=ExecExpiration.from_timeout_ms(1),
            capture_policy=ExecCapturePolicy.FULL_BUFFER,
            env={},
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            justification=None,
        )

        request = build_shell_request(
            exec_params,
            hook_command="printf hello",
            shell_type=ShellType.BASH,
            effective_additional_permissions=EffectiveAdditionalPermissions(
                SandboxPermissions.USE_DEFAULT,
                permissions_preapproved=False,
            ),
            normalized_additional_permissions=None,
            approval_policy=AskForApproval.NEVER,
            permission_profile=PermissionProfile.disabled(),
            file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(),
            sandbox_cwd=Path("/repo"),
        )

        self.assertEqual(request.capture_policy, ExecCapturePolicy.FULL_BUFFER)

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

    def test_handler_entrypoint_parses_invocation_and_dispatches_runner(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs::ShellCommandHandler::handle
        # Rust contract: handle parses function payloads, derives ExecParams, preserves the raw hook command,
        # and hands the shell request to the runtime path.
        captured = {}
        thread_id = ThreadId.new()

        async def runner(request: ShellCommandInvocationRequest):
            captured["request"] = request
            return {
                "text": "shell output",
                "success": True,
                "post_tool_use_response": "wire shell output",
            }

        turn = SimpleNamespace(
            cwd=Path("/repo"),
            shell_environment_policy=ShellEnvironmentPolicy.default(),
            network="net",
            config=SimpleNamespace(
                permissions=SimpleNamespace(
                    allow_login_shell=True,
                    windows_sandbox_private_desktop=False,
                )
            ),
        )
        session = SimpleNamespace(
            conversation_id=thread_id,
            user_shell=lambda: Shell(ShellType.BASH, "/bin/bash"),
        )
        invocation = ToolInvocation(
            call_id="call-shell",
            tool_name=ToolName.plain("shell_command"),
            session=session,
            turn=turn,
            cancellation_token=object(),
            tracker=object(),
            payload=ToolPayload.function(
                json.dumps(
                    {
                        "command": "echo hello",
                        "workdir": "subdir",
                        "timeout_ms": 50,
                        "login": True,
                        "prefix_rule": ["echo"],
                    }
                )
            ),
        )

        output = asyncio.run(ShellCommandHandler(runner=runner).handle(invocation))

        request = captured["request"]
        self.assertIs(request.invocation, invocation)
        self.assertEqual(request.hook_command, "echo hello")
        self.assertEqual(request.exec_params.command, ("/bin/bash", "-lc", "echo hello"))
        self.assertEqual(request.exec_params.cwd, Path("/repo/subdir"))
        self.assertEqual(request.exec_params.expiration.timeout_ms(), 50)
        self.assertEqual(request.exec_params.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertEqual(request.exec_params.network, "net")
        self.assertEqual(request.shell_type, ShellType.BASH)
        self.assertEqual(request.prefix_rule, ("echo",))
        self.assertEqual(request.backend, ShellCommandBackend.CLASSIC)
        self.assertEqual(request.workdir, Path("/repo/subdir"))
        self.assertEqual(output.into_text(), "shell output")
        self.assertEqual(output.post_tool_use_response("call-shell", invocation.payload), "wire shell output")

    def test_run_exec_like_builds_shell_request_and_dispatches_runner(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell.rs::run_exec_like.
        # Behavior anchor: run_exec_like normalizes permissions, builds the
        # ShellRequest, and hands execution to the shell runtime boundary.
        captured = {}
        thread_id = ThreadId.new()
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            set_values={"EXPLICIT": "1"},
        )
        turn = SimpleNamespace(
            cwd=Path("/repo"),
            shell_environment_policy=policy,
            approval_policy=AskForApproval.ON_REQUEST,
            permission_profile=lambda: PermissionProfile.workspace_write(),
            file_system_sandbox_policy=lambda: FileSystemSandboxPolicy.workspace_write(()),
        )
        session = SimpleNamespace(
            conversation_id=thread_id,
            user_shell=lambda: Shell(ShellType.BASH, "/bin/bash"),
        )
        params = ShellCommandToolCallParams(
            command="echo hello",
            sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
            justification="need unsandboxed",
            prefix_rule=("echo",),
        )
        exec_params = ShellCommandHandler.to_exec_params(
            params,
            session,
            turn,
            thread_id,
            allow_login_shell=False,
        )
        invocation = ToolInvocation(
            call_id="call-run-like",
            tool_name=ToolName.plain("shell_command"),
            session=session,
            turn=turn,
            cancellation_token=object(),
            tracker=object(),
            payload=ToolPayload.function('{"command":"echo hello"}'),
        )

        def runner(request: ShellCommandInvocationRequest) -> dict[str, object]:
            captured["request"] = request
            return {"text": "ok", "post_tool_use_response": "wire"}

        output = asyncio.run(
            run_exec_like(
                RunExecLikeArgs(
                    tool_name=ToolName.plain("shell_command"),
                    exec_params=exec_params,
                    cancellation_token=invocation.cancellation_token,
                    hook_command=params.command,
                    shell_type=ShellType.BASH,
                    additional_permissions=params.additional_permissions,
                    prefix_rule=params.prefix_rule,
                    session=session,
                    turn=turn,
                    tracker=invocation.tracker,
                    call_id=invocation.call_id,
                    shell_runtime_backend=ShellCommandBackend.CLASSIC,
                    invocation=invocation,
                    params=params,
                    workdir=exec_params.cwd,
                    runner=runner,
                )
            )
        )

        request = captured["request"]
        self.assertEqual(output.into_text(), "ok")
        self.assertEqual(request.shell_request.hook_command, "echo hello")
        self.assertEqual(request.shell_request.command, ("/bin/bash", "-c", "echo hello"))
        self.assertEqual(request.shell_request.explicit_env_overrides, {"EXPLICIT": "1"})
        self.assertEqual(request.shell_request.sandbox_permissions, SandboxPermissions.REQUIRE_ESCALATED)
        self.assertEqual(request.shell_request.justification, "need unsandboxed")
        self.assertEqual(request.shell_request.exec_approval_requirement.type, "needs_approval")
        self.assertEqual(request.prefix_rule, ("echo",))

    def test_handler_entrypoint_rejects_unsupported_payload_and_missing_runtime(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs::ShellCommandHandler::handle
        # Rust contract: non-function payloads are model-visible errors before runtime dispatch.
        handler = ShellCommandHandler()
        invocation = ToolInvocation(
            call_id="call-shell",
            tool_name=ToolName.plain("shell_command"),
            session=SimpleNamespace(user_shell=lambda: Shell(ShellType.BASH, "/bin/bash")),
            turn=SimpleNamespace(
                cwd=Path("/repo"),
                shell_environment_policy=ShellEnvironmentPolicy.default(),
                config=SimpleNamespace(permissions=SimpleNamespace(allow_login_shell=False)),
            ),
            cancellation_token=object(),
            tracker=object(),
            payload=ToolPayload.custom("raw"),
        )

        with self.assertRaisesRegex(FunctionCallError, "unsupported payload for shell_command handler"):
            handler.handle(invocation)

        missing_runtime = ToolInvocation(
            call_id="call-shell",
            tool_name=ToolName.plain("shell_command"),
            session=SimpleNamespace(
                conversation_id=ThreadId.new(),
                user_shell=lambda: Shell(ShellType.BASH, "/bin/bash"),
            ),
            turn=invocation.turn,
            cancellation_token=object(),
            tracker=object(),
            payload=ToolPayload.function('{"command":"echo hello"}'),
        )
        with self.assertRaisesRegex(FunctionCallError, "shell_command runtime is unavailable"):
            asyncio.run(handler.handle(missing_runtime))

    def test_pre_tool_use_payload_uses_bash_hook(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs
        # Rust test: shell_command_pre_tool_use_payload_uses_raw_command.
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

        with self.assertRaisesRegex(FunctionCallError, "updatedInput without string field `command`") as bad_command:
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
        # Rust source: codex-rs/core/src/tools/handlers/shell/shell_command.rs
        # Rust test: build_post_tool_use_payload_uses_tool_output_wire_value.
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
