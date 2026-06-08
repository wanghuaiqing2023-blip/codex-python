import asyncio
import array
import socket
import tempfile
import subprocess
import unittest
import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pycodex.execpolicy import (
    Decision,
    ExecPolicyPrefixRule,
    PROMPT_CONFLICT_REASON,
    REJECT_RULES_APPROVAL_REASON,
    REJECT_SANDBOX_APPROVAL_REASON,
    commands_for_intercepted_exec_policy,
)
from pycodex.core.guardian.approval_request import (
    GuardianNetworkAccessTrigger as CanonicalGuardianNetworkAccessTrigger,
)
from pycodex.core import (
    CODEX_PROXY_GIT_SSH_COMMAND_MARKER,
    ESCALATE_SOCKET_ENV_VAR,
    EXEC_WRAPPER_ENV_VAR,
    PROXY_ACTIVE_ENV_KEY,
    PROXY_ENV_KEYS,
    ApplyPatchRequest,
    ApplyPatchFileSystemSandboxContext,
    DecisionSource,
    ExecApprovalRequirement,
    ExecResult,
    GuardianNetworkAccessTrigger,
    InterceptedExecPolicyContext,
    InterceptedExecPolicyEvaluation,
    NetworkApprovalMode,
    ParsedShellCommand,
    PreparedUnifiedExecSpawn,
    PreparedUnifiedExecZshFork,
    SHELL_ESCALATE_HANDSHAKE_MESSAGE,
    SHELL_SOCKET_MAX_FDS_PER_MESSAGE,
    SHELL_SOCKET_STREAM_MAX_PAYLOAD,
    SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS,
    ShellRequest,
    Shell,
    ShellSnapshot,
    ShellType,
    ShellRuntimeBackend,
    ShellEscalateAction,
    ShellEscalateClientHandshakePlan,
    ShellEscalateClientSocketPair,
    ShellEscalateClientWrapperPlan,
    ShellEscalateClientAction,
    ShellEscalateClientPlan,
    ShellEscalatePolicyInput,
    ShellEscalateRequest,
    ShellEscalateResponse,
    ShellEscalationDecision,
    ShellEscalationExecution,
    ShellEscalationPolicyPlan,
    ShellEscalateServerPlan,
    ShellCommandExecutorRunContext,
    ShellLocalExecvPlan,
    ShellPrepareSandboxedExecContext,
    ShellPrepareSandboxedExecParams,
    ShellSandboxTransformRequest,
    ShellPreparedExec,
    ShellSuperExecMessage,
    ShellSuperExecResult,
    ShellSuperExecSpawnPlan,
    ShellSuperExecSubprocessSpec,
    ShellZshForkCancellationPlan,
    ShellZshForkExecParams,
    SandboxCommand,
    SandboxExecRequest,
    SandboxType,
    ToolRuntimeError,
    UnifiedExecDirectRunPlan,
    UnifiedExecOptions,
    UnifiedExecRequest,
    ZshForkSpawnLifecycle,
    approval_sandbox_permissions,
    apply_patch_approval_keys,
    apply_patch_file_system_sandbox_context_for_attempt,
    apply_patch_permission_request_payload,
    apply_patch_sandbox_cwd,
    apply_patch_wants_no_sandbox_approval,
    build_override_exports_for_keys,
    build_sandbox_command,
    build_unified_exec_sandbox_command,
    disable_powershell_profile_for_elevated_windows_sandbox,
    decision_driven_by_policy,
    exec_env_for_sandbox_permissions,
    exec_result_from_tool_output,
    execve_prompt_is_rejected_by_policy,
    extract_shell_script,
    effective_file_system_sandbox_policy,
    evaluate_intercepted_exec_policy,
    is_valid_shell_variable_name,
    join_program_and_argv,
    map_exec_result,
    maybe_prepare_unified_exec_zsh_fork,
    maybe_run_shell_command_zsh_fork,
    managed_network_for_runtime,
    maybe_wrap_shell_lc_with_snapshot,
    shell_prepared_exec_effective_arg0,
    shell_prepared_exec_program_and_args,
    prepare_unified_exec_zsh_fork_from_session,
    shell_escalate_action_from_decision,
    shell_escalate_client_action_from_response,
    shell_escalate_client_handshake_payload,
    shell_escalate_client_handshake_plan,
    shell_escalate_client_handshake_plan_send,
    shell_escalate_client_handshake_run,
    shell_escalate_client_plan_from_response,
    shell_escalate_client_plan_run,
    shell_escalate_client_request_exchange,
    shell_escalate_client_request_run,
    shell_escalate_client_response_run,
    shell_escalate_client_send_handshake,
    shell_escalate_client_socket_pair,
    shell_escalate_client_wrapper_plan,
    shell_escalate_client_wrapper_plan_run,
    shell_escalate_client_wrapper_plan_send_handshake,
    shell_escalate_client_wrapper_run,
    shell_escalate_client_wrapper_run_with_socket_pair,
    shell_escalate_decision_for_request,
    shell_escalate_policy_input_from_request,
    shell_escalate_request_from_client,
    shell_escalate_response_from_decision,
    shell_escalate_server_continue_after_response,
    shell_escalate_server_decision_send_response,
    shell_escalate_server_decision_run,
    shell_escalate_server_plan_from_decision,
    shell_escalate_server_plan_send_response,
    shell_escalate_server_request_run,
    shell_escalation_merge_env_overlay,
    shell_escalation_policy_plan,
    shell_escalation_request_env,
    shell_escalation_session_env,
    shell_escalation_socket_fd_from_env,
    shell_local_execv_plan,
    shell_local_execv_run,
    shell_super_exec_duplicate_fd_for_transfer,
    shell_super_exec_exchange_exit_code,
    shell_super_exec_exit_code_from_result,
    shell_super_exec_fd_pairs,
    shell_super_exec_message_for_escalate_action,
    shell_super_exec_result_from_exit_status,
    shell_super_exec_send_receive_exit_code,
    shell_super_exec_spawn_plan,
    shell_super_exec_stdio_transfer_fds,
    shell_super_exec_subprocess_spec,
    shell_super_exec_dup2_preexec_fn,
    shell_super_exec_popen_kwargs,
    shell_super_exec_run_prepared,
    shell_super_exec_run_subprocess,
    shell_approval_keys,
    shell_command_executor_exec_request,
    shell_command_executor_run,
    shell_network_approval_spec,
    shell_prepare_escalated_exec,
    shell_prepare_escalated_exec_params,
    shell_prepare_sandboxed_exec,
    shell_escalation_decision_after_review,
    shell_escalation_decision_for_approved_review,
    shell_escalation_decision_for_policy_decision,
    shell_request_escalation_execution,
    shell_zsh_fork_cancellation_plan,
    shell_zsh_fork_exec_params,
    shell_permission_request_payload,
    shell_single_quote,
    shell_socket_build_length_prefixed_payload,
    shell_socket_recvmsg_with_fds,
    shell_socket_extract_length_prefixed_payload,
    shell_socket_recv_stream_frame_with_fds,
    shell_socket_sendmsg_with_fds,
    shell_socket_send_stream_frame_with_fds,
    shell_socket_validate_fds_for_message,
    unified_exec_approval_keys,
    unified_exec_direct_run_plan,
    unified_exec_network_approval_spec,
    unified_exec_options,
    unified_exec_permission_request_payload,
    unified_exec_sandbox_cwd,
)
from pycodex.core import SandboxAttempt
from pycodex.core.exec import ExecRequest
from pycodex.core import DEFAULT_EXEC_COMMAND_TIMEOUT_MS, ExecCapturePolicy, ExecExpirationKind
from pycodex.core.exec import CancellationToken
from pycodex.core.tools.network_approval import (
    NetworkApprovalService,
    NetworkApprovalSpec as CanonicalNetworkApprovalSpec,
    begin_network_approval,
)
from pycodex.core.tools.runtimes import flat_tool_name
from pycodex.protocol import (
    AskForApproval,
    CODEX_THREAD_ID_ENV_VAR,
    ExecToolCallOutput,
    FileChange,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkPermissions,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    NetworkSandboxPolicy,
    PermissionProfile,
    ReviewDecision,
    AdditionalPermissionProfile,
    FileSystemPermissions,
    SandboxPermissions,
    StreamOutput,
    ToolName,
    WindowsSandboxLevel,
)


class ToolRuntimesTests(unittest.TestCase):
    def test_zsh_fork_backend_non_unix_falls_back_to_normal_paths(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/zsh_fork_backend.rs
        # Contract: cfg(not(unix)) implementations return Ok(None) for shell
        # and unified-exec paths without invoking escalation.
        async def run() -> None:
            with patch("pycodex.core.tools.runtimes.os.name", "nt"):
                shell_result = await maybe_run_shell_command_zsh_fork(
                    object(),
                    object(),
                    object(),
                    ("zsh", "-lc", "echo hi"),
                    try_run_zsh_fork=lambda *_args: self.fail("delegate should not run"),
                )
                unified_result = await maybe_prepare_unified_exec_zsh_fork(
                    object(),
                    object(),
                    object(),
                    "exec-request",
                    object(),
                    prepare_unified_exec_zsh_fork=lambda *_args: self.fail("delegate should not run"),
                )
            self.assertIsNone(shell_result)
            self.assertIsNone(unified_result)

        asyncio.run(run())

    def test_zsh_fork_backend_unix_delegates_shell_command(self) -> None:
        # Rust source: maybe_run_shell_command delegates to
        # unix_escalation::try_run_zsh_fork on Unix.
        output = ExecToolCallOutput(exit_code=7)
        calls: list[tuple[object, object, object, tuple[str, ...]]] = []

        async def delegate(req: object, attempt: object, ctx: object, command: tuple[str, ...]) -> ExecToolCallOutput:
            calls.append((req, attempt, ctx, command))
            return output

        async def run() -> None:
            req = object()
            attempt = object()
            ctx = object()
            with patch("pycodex.core.tools.runtimes.os.name", "posix"):
                result = await maybe_run_shell_command_zsh_fork(
                    req,
                    attempt,
                    ctx,
                    ["zsh", "-lc", "echo hi"],
                    try_run_zsh_fork=delegate,
                )
            self.assertIs(result, output)
            self.assertEqual(calls, [(req, attempt, ctx, ("zsh", "-lc", "echo hi"))])

        asyncio.run(run())

    def test_zsh_fork_backend_unix_wraps_prepared_unified_exec_spawn(self) -> None:
        # Rust source: maybe_prepare_unified_exec wraps the unix escalation
        # result in PreparedUnifiedExecSpawn with a ZshFork spawn lifecycle.
        closed: list[bool] = []

        class EscalationSession:
            def env(self) -> dict[str, str]:
                return {ESCALATE_SOCKET_ENV_VAR: "42"}

            def close_client_socket(self) -> None:
                closed.append(True)

        prepared = type(
            "Prepared",
            (),
            {"exec_request": "prepared-exec", "escalation_session": EscalationSession()},
        )()
        calls: list[tuple[object, object, object, object, Path, Path]] = []
        config = type(
            "Config",
            (),
            {
                "shell_zsh_path": Path("/bin/zsh"),
                "main_execve_wrapper_exe": Path("/tmp/wrapper"),
            },
        )()

        def delegate(
            req: object,
            attempt: object,
            ctx: object,
            exec_request: object,
            shell_zsh_path: Path,
            wrapper_exe: Path,
        ) -> object:
            calls.append((req, attempt, ctx, exec_request, shell_zsh_path, wrapper_exe))
            return prepared

        async def run() -> None:
            req = object()
            attempt = object()
            ctx = object()
            with patch("pycodex.core.tools.runtimes.os.name", "posix"):
                result = await maybe_prepare_unified_exec_zsh_fork(
                    req,
                    attempt,
                    ctx,
                    "exec-request",
                    config,
                    prepare_unified_exec_zsh_fork=delegate,
                )
            self.assertIsInstance(result, PreparedUnifiedExecSpawn)
            self.assertEqual(result.exec_request, "prepared-exec")
            self.assertIsInstance(result.spawn_lifecycle, ZshForkSpawnLifecycle)
            self.assertEqual(result.spawn_lifecycle.inherited_fds(), [42])
            result.spawn_lifecycle.after_spawn()
            self.assertEqual(closed, [True])
            self.assertEqual(
                calls,
                [(req, attempt, ctx, "exec-request", Path("/bin/zsh"), Path("/tmp/wrapper"))],
            )

        asyncio.run(run())

    def test_shell_zsh_fork_exec_params_match_rust_try_run_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: try_run_zsh_fork constructs ExecParams from
        # ParsedShellCommand and the effective request timeout.
        params = shell_zsh_fork_exec_params(
            ("/usr/bin/env", "A=1", "/bin/zsh", "-lc", "echo hi"),
            Path("/work/tree"),
            None,
        )

        self.assertEqual(
            params,
            ShellZshForkExecParams(
                command="echo hi",
                workdir="/work/tree",
                timeout_ms=DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
                login=True,
            ),
        )
        self.assertEqual(
            shell_zsh_fork_exec_params(("/bin/zsh", "-c", "pwd"), "/tmp/project", 1234),
            ShellZshForkExecParams("pwd", "/tmp/project", 1234, False),
        )
        with self.assertRaises(ToolRuntimeError):
            shell_zsh_fork_exec_params(("sandbox-exec", "-fc", "echo no"), "/work", None)

    def test_shell_zsh_fork_cancellation_plan_matches_rust_network_denial_merge(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: try_run_zsh_fork uses the stopwatch cancellation
        # token directly unless the sandbox attempt carries a network-denial
        # cancellation token, in which case it combines them with cancel_when_either.
        stopwatch = CancellationToken()
        no_network = shell_zsh_fork_cancellation_plan(stopwatch)

        self.assertEqual(
            no_network,
            ShellZshForkCancellationPlan(
                stopwatch_token=stopwatch,
                cancel_token=stopwatch,
                network_denial_cancellation_token=None,
            ),
        )

        network = CancellationToken()
        with_network = shell_zsh_fork_cancellation_plan(stopwatch, network)

        self.assertIs(with_network.stopwatch_token, stopwatch)
        self.assertIs(with_network.network_denial_cancellation_token, network)
        self.assertIsNot(with_network.cancel_token, stopwatch)
        self.assertIsNot(with_network.cancel_token, network)
        self.assertFalse(with_network.cancel_token.is_cancelled())
        network.cancel()
        self.assertTrue(with_network.cancel_token.is_cancelled())

        stopwatch_2 = CancellationToken()
        network_2 = CancellationToken()
        with_stopwatch_cancel = shell_zsh_fork_cancellation_plan(stopwatch_2, network_2)
        stopwatch_2.cancel()
        self.assertTrue(with_stopwatch_cancel.cancel_token.is_cancelled())

    def test_prepare_unified_exec_zsh_fork_from_session_matches_rust_env_extension(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: prepare_unified_exec_zsh_fork parses the shell command,
        # rejects non-zsh targets, and extends the ExecRequest env with the
        # EscalationSession env after start_session succeeds.
        class EscalationSession:
            def env(self) -> dict[str, str]:
                return {
                    ESCALATE_SOCKET_ENV_VAR: "9",
                    EXEC_WRAPPER_ENV_VAR: "/tmp/wrapper",
                    "EXTRA_SESSION_VALUE": "kept",
                }

        request = ExecRequest(
            command=("/usr/bin/env", "A=1", "/bin/zsh", "-lc", "echo hi"),
            cwd=Path("/work"),
            env={"BASE": "1", ESCALATE_SOCKET_ENV_VAR: "old"},
            permission_profile=PermissionProfile.read_only(),
        )
        session = EscalationSession()

        prepared = prepare_unified_exec_zsh_fork_from_session(request, Path("/bin/zsh"), session)

        self.assertIsInstance(prepared, PreparedUnifiedExecZshFork)
        self.assertIs(prepared.escalation_session, session)
        self.assertIsNot(prepared.exec_request, request)
        self.assertEqual(request.env[ESCALATE_SOCKET_ENV_VAR], "old")
        self.assertEqual(
            prepared.exec_request.env,
            {
                "BASE": "1",
                ESCALATE_SOCKET_ENV_VAR: "9",
                EXEC_WRAPPER_ENV_VAR: "/tmp/wrapper",
                "EXTRA_SESSION_VALUE": "kept",
            },
        )
        self.assertIsNone(
            prepare_unified_exec_zsh_fork_from_session(
                request,
                Path("/usr/local/bin/zsh"),
                session,
            )
        )
        self.assertIsNone(
            prepare_unified_exec_zsh_fork_from_session(
                ExecRequest(command=("sandbox-exec", "-fc", "echo no"), cwd=Path("/work")),
                Path("/bin/zsh"),
                session,
            )
        )

    def test_shell_escalation_env_vars_match_rust_protocol_constants(self) -> None:
        self.assertEqual(ESCALATE_SOCKET_ENV_VAR, "CODEX_ESCALATE_SOCKET")
        self.assertEqual(EXEC_WRAPPER_ENV_VAR, "EXEC_WRAPPER")

    def test_shell_escalation_session_env_matches_server_start_session_shape(self) -> None:
        self.assertEqual(
            shell_escalation_session_env(42, Path("/tmp/exec-wrapper")),
            {
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
        )
        with self.assertRaises(TypeError):
            shell_escalation_session_env(True, "/tmp/exec-wrapper")

    def test_shell_escalation_request_env_filters_internal_protocol_vars(self) -> None:
        env = {
            "A": "B",
            "CODEX_ESCALATE_SOCKET": "42",
            "EXEC_WRAPPER": "/tmp/exec-wrapper",
        }

        self.assertEqual(shell_escalation_request_env(env), {"A": "B"})
        self.assertEqual(
            env,
            {
                "A": "B",
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
        )
        with self.assertRaises(TypeError):
            shell_escalation_request_env({"A": 1})
        with self.assertRaises(TypeError):
            shell_escalation_request_env(object())

    def test_shell_escalation_merge_env_overlay_only_copies_protocol_vars(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellCommandExecutor::run only merges
        # CODEX_ESCALATE_SOCKET and EXEC_WRAPPER from env_overlay.
        base_env = {
            "A": "base",
            "PATH": "/bin",
            "CODEX_ESCALATE_SOCKET": "old",
        }
        overlay = {
            "A": "overlay",
            "CODEX_ESCALATE_SOCKET": "42",
            "EXEC_WRAPPER": "/tmp/exec-wrapper",
            "IGNORED": "value",
        }

        self.assertEqual(
            shell_escalation_merge_env_overlay(base_env, overlay),
            {
                "A": "base",
                "PATH": "/bin",
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
        )
        self.assertEqual(base_env["CODEX_ESCALATE_SOCKET"], "old")
        with self.assertRaises(TypeError):
            shell_escalation_merge_env_overlay({"A": "B"}, {"CODEX_ESCALATE_SOCKET": 42})
        with self.assertRaises(TypeError):
            shell_escalation_merge_env_overlay(object(), {})

    def test_shell_command_executor_exec_request_matches_rust_run_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellCommandExecutor::run ExecRequest construction.
        cancellation = CancellationToken()
        profile = PermissionProfile.read_only()
        file_system_policy, network_policy = profile.to_runtime_permissions()
        context = ShellCommandExecutorRunContext(
            command=("/usr/bin/touch", "/tmp/file"),
            cwd=Path("/work"),
            env={"A": "base"},
            network="network",
            sandbox=SandboxType.LINUX_SECCOMP,
            sandbox_policy_cwd=Path("/policy"),
            windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
            permission_profile=profile,
            file_system_sandbox_policy=file_system_policy,
            network_sandbox_policy=network_policy,
            arg0="touch",
        )

        request = shell_command_executor_exec_request(
            context,
            {
                "A": "ignored",
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
            cancellation,
        )

        self.assertEqual(request.command, ("/usr/bin/touch", "/tmp/file"))
        self.assertEqual(request.cwd, Path("/work"))
        self.assertEqual(
            request.env,
            {
                "A": "base",
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
        )
        self.assertIs(request.network, context.network)
        self.assertIs(request.expiration.cancellation, cancellation)
        self.assertEqual(request.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertEqual(request.sandbox, SandboxType.LINUX_SECCOMP)
        self.assertEqual(request.windows_sandbox_policy_cwd, Path("/policy"))
        self.assertEqual(request.windows_sandbox_level, WindowsSandboxLevel.RESTRICTED_TOKEN)
        self.assertFalse(request.windows_sandbox_private_desktop)
        self.assertEqual(request.permission_profile, profile)
        self.assertEqual(request.file_system_sandbox_policy, file_system_policy)
        self.assertEqual(request.network_sandbox_policy, network_policy)
        self.assertIsNone(request.windows_sandbox_filesystem_overrides)
        self.assertIsNone(request.exec_server_env_config)
        self.assertEqual(request.arg0, "touch")

    def test_shell_command_executor_run_maps_exec_output_to_rust_exec_result(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellCommandExecutor::run output mapping.
        profile = PermissionProfile.read_only()
        file_system_policy, network_policy = profile.to_runtime_permissions()
        context = ShellCommandExecutorRunContext(
            command=("/usr/bin/printf", "hello"),
            cwd=Path("/work"),
            env={"A": "base"},
            network=None,
            sandbox=SandboxType.NONE,
            sandbox_policy_cwd=Path("/policy"),
            windows_sandbox_level=WindowsSandboxLevel.DISABLED,
            permission_profile=profile,
            file_system_sandbox_policy=file_system_policy,
            network_sandbox_policy=network_policy,
        )
        cancellation = CancellationToken()
        after_spawn_calls: list[bool] = []
        seen: list[tuple[object, object, object]] = []

        async def execute(request: object, stdout_stream: object, after_spawn: object) -> ExecToolCallOutput:
            seen.append((request, stdout_stream, after_spawn))
            if callable(after_spawn):
                after_spawn()
            return ExecToolCallOutput(
                exit_code=7,
                stdout=StreamOutput.new("out"),
                stderr=StreamOutput.new("err"),
                aggregated_output=StreamOutput.new("outerr"),
                duration=timedelta(milliseconds=12),
                timed_out=True,
            )

        result = asyncio.run(
            shell_command_executor_run(
                context,
                {"EXEC_WRAPPER": "/tmp/exec-wrapper"},
                cancellation,
                execute_exec_request_with_after_spawn=execute,
                after_spawn=lambda: after_spawn_calls.append(True),
            )
        )

        request, stdout_stream, after_spawn = seen[0]
        self.assertIsNone(stdout_stream)
        self.assertTrue(callable(after_spawn))
        self.assertEqual(request.env, {"A": "base", "EXEC_WRAPPER": "/tmp/exec-wrapper"})
        self.assertEqual(after_spawn_calls, [True])
        self.assertEqual(
            result,
            ExecResult(
                exit_code=7,
                stdout="out",
                stderr="err",
                output="outerr",
                duration=timedelta(milliseconds=12),
                timed_out=True,
            ),
        )
        self.assertEqual(
            exec_result_from_tool_output(
                ExecToolCallOutput(
                    exit_code=0,
                    stdout=StreamOutput.new("stdout"),
                    stderr=StreamOutput.new("stderr"),
                    aggregated_output=StreamOutput.new("aggregate"),
                )
            ),
            ExecResult(exit_code=0, stdout="stdout", stderr="stderr", output="aggregate"),
        )

    def test_shell_escalation_socket_fd_from_env_matches_client_fd_parse(self) -> None:
        self.assertEqual(shell_escalation_socket_fd_from_env({"CODEX_ESCALATE_SOCKET": "42"}), 42)
        with self.assertRaisesRegex(ValueError, "CODEX_ESCALATE_SOCKET is not a valid file descriptor: -1"):
            shell_escalation_socket_fd_from_env({"CODEX_ESCALATE_SOCKET": "-1"})
        with self.assertRaises(ValueError):
            shell_escalation_socket_fd_from_env({"CODEX_ESCALATE_SOCKET": "not-an-int"})
        with self.assertRaises(KeyError):
            shell_escalation_socket_fd_from_env({})
        with self.assertRaises(TypeError):
            shell_escalation_socket_fd_from_env({"CODEX_ESCALATE_SOCKET": 42})

    def test_shell_escalate_client_handshake_payload_matches_rust_send_with_fds_shape(self) -> None:
        self.assertEqual(SHELL_ESCALATE_HANDSHAKE_MESSAGE, b"\x00")
        self.assertEqual(shell_escalate_client_handshake_payload(17), (b"\x00", (17,)))
        self.assertEqual(shell_escalate_client_handshake_payload(18, b"x"), (b"x", (18,)))
        with self.assertRaisesRegex(ValueError, "server_socket_fd is not a valid file descriptor: -1"):
            shell_escalate_client_handshake_payload(-1)
        with self.assertRaises(TypeError):
            shell_escalate_client_handshake_payload(True)
        with self.assertRaises(TypeError):
            shell_escalate_client_handshake_payload(17, "not-bytes")  # type: ignore[arg-type]

    def test_shell_escalate_client_socket_pair_matches_wrapper_pair_shape(self) -> None:
        class FakeSocket:
            def __init__(self, fd: int) -> None:
                self.fd = fd

            def fileno(self) -> int:
                return self.fd

        server = FakeSocket(17)
        client = FakeSocket(18)

        self.assertEqual(
            shell_escalate_client_socket_pair(pair_factory=lambda: (server, client)),
            ShellEscalateClientSocketPair(server, client, 17, 18),
        )
        with self.assertRaises(TypeError):
            shell_escalate_client_socket_pair(pair_factory=lambda: (server,))
        with self.assertRaises(TypeError):
            shell_escalate_client_socket_pair(pair_factory=lambda: (server, object()))
        with self.assertRaisesRegex(ValueError, "server_fd is not a valid file descriptor: -1"):
            ShellEscalateClientSocketPair(server, client, -1, 18)

    def test_shell_socket_validate_fds_for_message_matches_rust_limit(self) -> None:
        self.assertEqual(SHELL_SOCKET_MAX_FDS_PER_MESSAGE, 16)
        self.assertEqual(shell_socket_validate_fds_for_message([0, 1, 2]), (0, 1, 2))
        with self.assertRaisesRegex(ValueError, "too many fds: 17"):
            shell_socket_validate_fds_for_message(range(17))
        with self.assertRaises(TypeError):
            shell_socket_validate_fds_for_message([True])
        with self.assertRaisesRegex(ValueError, "fd is not a valid file descriptor: -1"):
            shell_socket_validate_fds_for_message([-1])

    def test_shell_socket_sendmsg_with_fds_matches_datagram_send_boundary(self) -> None:
        calls: list[Any] = []

        def fake_sendmsg(buffers: list[bytes], ancillary: list[Any]) -> int:
            calls.append((buffers, ancillary))
            return len(buffers[0])

        self.assertEqual(shell_socket_sendmsg_with_fds(object(), b"hi", [3], sendmsg=fake_sendmsg), 2)
        self.assertEqual(calls[0][0], [b"hi"])
        self.assertEqual(calls[0][1][0][0], socket.SOL_SOCKET)
        self.assertEqual(calls[0][1][0][1], socket.SCM_RIGHTS)
        self.assertEqual(calls[0][1][0][2].tolist(), [3])
        with self.assertRaisesRegex(OSError, "short datagram write: wrote 1 bytes out of 2"):
            shell_socket_sendmsg_with_fds(object(), b"hi", [], sendmsg=lambda _buffers, _ancillary: 1)

    def test_shell_socket_send_stream_frame_with_fds(self) -> None:
        calls: list[tuple[bytes, list[Any]]] = []
        payload = b"hello"
        framed_payload = len(payload).to_bytes(4, "little") + payload

        def fake_sendmsg(buffers: list[bytes], ancillary: list[Any]) -> int:
            chunk = bytes(buffers[0])
            calls.append((chunk, ancillary))
            if len(calls) == 1:
                return len(chunk) - 1
            return len(chunk)

        self.assertEqual(
            shell_socket_send_stream_frame_with_fds(
                object(),
                payload,
                (10, 11),
                sendmsg=fake_sendmsg,
            ),
            len(framed_payload),
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], framed_payload)
        self.assertEqual(calls[0][1][0][2].tolist(), [10, 11])
        self.assertEqual(calls[1][0], framed_payload[-1:])
        self.assertEqual(calls[1][1], [])

    def test_shell_socket_send_stream_frame_with_fds_raises_when_peer_closes_before_payload(
        self,
    ) -> None:
        self.assertRaisesRegex(
            OSError,
            "socket closed while sending frame payload",
            lambda: shell_socket_send_stream_frame_with_fds(
                object(),
                b"payload",
                (10, 11),
                sendmsg=lambda _buffers, _ancillary: 0,
            ),
        )

    def test_shell_socket_send_stream_frame_with_fds_send_callback_falls_back_to_send_without_fds(
        self,
    ) -> None:
        calls: list[tuple[bytes, ...]] = []

        def fake_send(data: bytes) -> int:
            calls.append((data,))
            return len(data)

        self.assertEqual(
            shell_socket_send_stream_frame_with_fds(
                object(),
                b"payload",
                (10,),
                send=fake_send,
            ),
            len(b"payload") + 4,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], b"\x07\0\0\0payload")

    def test_shell_socket_send_stream_frame_with_fds_send_callback_with_fds_only_on_first_chunk(self) -> None:
        calls: list[tuple[bytes, tuple[int, ...] | None]] = []

        def fake_send(data: bytes, fds: tuple[int, ...] | None = None) -> int:
            calls.append((data, fds))
            if len(calls) == 1:
                return len(data) - 1
            return len(data)

        payload = b"f" * (SHELL_SOCKET_STREAM_MAX_PAYLOAD + 1)
        self.assertEqual(
            shell_socket_send_stream_frame_with_fds(
                object(),
                payload,
                (10,),
                send=fake_send,
            ),
            len(shell_socket_build_length_prefixed_payload(payload)),
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], (10,))
        self.assertEqual(len(calls[0][0]), SHELL_SOCKET_STREAM_MAX_PAYLOAD)
        self.assertEqual(len(calls[1][0]), 6)
        self.assertEqual(calls[1][1], ())

    def test_shell_socket_recvmsg_with_fds_matches_datagram_receive_boundary(self) -> None:
        received = array.array("i", [7, 8])
        calls: list[Any] = []

        def fake_recvmsg(buffer_size: int, ancbuf_size: int) -> tuple[bytes, list[Any], int, None]:
            calls.append((buffer_size, ancbuf_size))
            return (
                b"ok",
                [
                    (socket.SOL_SOCKET, socket.SCM_RIGHTS, received.tobytes()),
                    (999, 999, b"ignored"),
                ],
                0,
                None,
            )

        self.assertEqual(
            shell_socket_recvmsg_with_fds(object(), 4096, recvmsg=fake_recvmsg),
            (b"ok", (7, 8)),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 4096)
        self.assertGreaterEqual(calls[0][1], socket.CMSG_SPACE(2 * received.itemsize))
        self.assertEqual(
            shell_socket_recvmsg_with_fds(
                object(),
                4096,
                recvmsg=lambda _buffer_size, _ancbuf_size: (b"plain", [], 0, None),
            ),
            (b"plain", ()),
        )
        with self.assertRaisesRegex(OSError, "ancillary data truncated"):
            shell_socket_recvmsg_with_fds(
                object(),
                4096,
                recvmsg=lambda _buffer_size, _ancbuf_size: (b"", [], socket.MSG_CTRUNC, None),
            )
        with self.assertRaisesRegex(ValueError, "buffer_size must be positive"):
            shell_socket_recvmsg_with_fds(object(), 0, recvmsg=fake_recvmsg)

    def test_shell_socket_recv_stream_frame_with_fds(self) -> None:
        calls: list[tuple[Any, ...]] = []

        def fake_recvmsg(
            buffer_size: int,
            ancbuf_size: int,
        ) -> tuple[bytes, list[Any], int, None]:
            calls.append(("recvmsg", buffer_size, ancbuf_size))
            header = b"\x05\x00"
            control = array.array("i", [22]).tobytes()
            return (header, [(socket.SOL_SOCKET, socket.SCM_RIGHTS, control)], 0, None)

        recv_calls = 0

        def fake_recv(size: int) -> bytes:
            nonlocal recv_calls
            recv_calls += 1
            if recv_calls == 1:
                return b"\x00\x00"
            if recv_calls == 2:
                return b"world"
            return b""

        payload, transferred_fds = shell_socket_recv_stream_frame_with_fds(
            object(),
            max_fds=4,
            recvmsg=fake_recvmsg,
            recv=fake_recv,
        )
        self.assertEqual(payload, b"world")
        self.assertEqual(transferred_fds, (22,))
        self.assertEqual(
            calls,
            [("recvmsg", 4, socket.CMSG_SPACE(4 * array.array("i").itemsize))],
        )

    def test_shell_socket_recv_stream_frame_with_fds_raises_when_peer_closes_before_header(self) -> None:
        self.assertRaisesRegex(
            OSError,
            "socket closed while receiving frame header",
            lambda: shell_socket_recv_stream_frame_with_fds(
                object(),
                recvmsg=lambda _buffer_size, _ancbuf_size: (b"", [], 0, None),
                recv=lambda _size: b"",
            ),
        )

    def test_shell_socket_recv_stream_frame_with_fds_raises_when_peer_closes_before_payload(self) -> None:
        self.assertRaisesRegex(
            OSError,
            "socket closed while receiving frame payload",
            lambda: shell_socket_recv_stream_frame_with_fds(
                object(),
                recvmsg=lambda _buffer_size, _ancbuf_size: (
                    b"\x04\x00\x00\x00",
                    [],
                    0,
                    None,
                ),
                recv=lambda _size: b"",
            ),
        )

    def test_shell_escalate_client_wrapper_plan_keeps_client_socket_and_handshake_shape(self) -> None:
        class FakeSocket:
            def __init__(self, name: str, fd: int) -> None:
                self.name = name
                self.fd = fd

            def fileno(self) -> int:
                return self.fd

        server = FakeSocket("server", 17)
        client = FakeSocket("client", 18)
        socket_pair = ShellEscalateClientSocketPair(server, client, 17, 18)

        self.assertEqual(
            shell_escalate_client_wrapper_plan(
                env={"CODEX_ESCALATE_SOCKET": "42"},
                pair_factory=lambda: (server, client),
            ),
            ShellEscalateClientWrapperPlan(
                socket_pair,
                ShellEscalateClientHandshakePlan(42, b"\x00", (17,)),
            ),
        )
        with self.assertRaises(TypeError):
            ShellEscalateClientWrapperPlan(object(), ShellEscalateClientHandshakePlan(42, b"\x00", (17,)))
        with self.assertRaises(TypeError):
            ShellEscalateClientWrapperPlan(socket_pair, object())

    def test_shell_escalate_client_handshake_plan_matches_get_client_then_send_shape(self) -> None:
        self.assertEqual(
            shell_escalate_client_handshake_plan(17, env={"CODEX_ESCALATE_SOCKET": "42"}),
            ShellEscalateClientHandshakePlan(42, b"\x00", (17,)),
        )
        self.assertEqual(
            shell_escalate_client_handshake_plan(18, env={"CODEX_ESCALATE_SOCKET": "43"}, message=b"x"),
            ShellEscalateClientHandshakePlan(43, b"x", (18,)),
        )
        with self.assertRaisesRegex(ValueError, "CODEX_ESCALATE_SOCKET is not a valid file descriptor: -1"):
            shell_escalate_client_handshake_plan(17, env={"CODEX_ESCALATE_SOCKET": "-1"})
        with self.assertRaisesRegex(ValueError, "attached fd is not a valid file descriptor: -1"):
            ShellEscalateClientHandshakePlan(42, b"\x00", (-1,))

    def test_shell_escalate_client_handshake_plan_send_uses_parent_datagram_fd(self) -> None:
        calls: list[tuple[int, bytes, tuple[int, ...]]] = []
        plan = ShellEscalateClientHandshakePlan(42, b"\x00", (17,))

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> str:
            calls.append((handshake_client_fd, message, fds))
            return "sent"

        self.assertEqual(
            shell_escalate_client_handshake_plan_send(plan, send_with_fds=fake_send_with_fds),
            "sent",
        )
        self.assertEqual(calls, [(42, b"\x00", (17,))])
        with self.assertRaisesRegex(RuntimeError, "failed to send handshake datagram"):
            shell_escalate_client_handshake_plan_send(
                plan,
                send_with_fds=lambda _fd, _message, _fds: (_ for _ in ()).throw(OSError("send failed")),
            )
        with self.assertRaises(TypeError):
            shell_escalate_client_handshake_plan_send(object(), send_with_fds=fake_send_with_fds)

    def test_shell_escalate_client_handshake_run_matches_wrapper_handshake_sequence(self) -> None:
        calls: list[tuple[int, bytes, tuple[int, ...]]] = []

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> str:
            calls.append((handshake_client_fd, message, fds))
            return "sent"

        self.assertEqual(
            shell_escalate_client_handshake_run(
                17,
                env={"CODEX_ESCALATE_SOCKET": "42"},
                send_with_fds=fake_send_with_fds,
            ),
            "sent",
        )
        self.assertEqual(calls, [(42, b"\x00", (17,))])
        with self.assertRaisesRegex(RuntimeError, "failed to send handshake datagram"):
            shell_escalate_client_handshake_run(
                17,
                env={"CODEX_ESCALATE_SOCKET": "42"},
                send_with_fds=lambda _fd, _message, _fds: (_ for _ in ()).throw(OSError("send failed")),
            )

    def test_shell_escalate_client_send_handshake_wraps_send_with_fds(self) -> None:
        calls: list[tuple[bytes, tuple[int, ...]]] = []

        def fake_send_with_fds(message: bytes, fds: tuple[int, ...]) -> str:
            calls.append((message, fds))
            return "sent"

        self.assertEqual(
            shell_escalate_client_send_handshake(22, send_with_fds=fake_send_with_fds),
            "sent",
        )
        self.assertEqual(calls, [(b"\x00", (22,))])
        with self.assertRaisesRegex(RuntimeError, "failed to send handshake datagram"):
            shell_escalate_client_send_handshake(
                22,
                send_with_fds=lambda _message, _fds: (_ for _ in ()).throw(OSError("send failed")),
            )

    def test_shell_escalate_request_from_client_uses_workdir_and_filtered_env(self) -> None:
        request = shell_escalate_request_from_client(
            "bin/tool",
            ["tool", "--flag"],
            workdir="/work",
            env={
                "A": "B",
                "CODEX_ESCALATE_SOCKET": "42",
                "EXEC_WRAPPER": "/tmp/exec-wrapper",
            },
        )

        self.assertEqual(
            request,
            ShellEscalateRequest("bin/tool", ("tool", "--flag"), Path("/work"), {"A": "B"}),
        )
        with self.assertRaises(TypeError):
            shell_escalate_request_from_client("bin/tool", [object()], workdir="/work", env={})
        with self.assertRaises(TypeError):
            shell_escalate_request_from_client("bin/tool", ["tool"], workdir="/work", env={"A": 1})

    def test_apply_patch_runtime_boundaries_shape_keys_and_permission_payload(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/apply_patch.rs
        # Rust tests: approval_keys_include_environment_id,
        # permission_request_payload_uses_apply_patch_hook_name_and_aliases,
        # sandbox_cwd_uses_patch_action_cwd, and
        # wants_no_sandbox_approval_granular_respects_sandbox_flag.
        class Env:
            environment_id = "local"

        class Action:
            patch = "*** Begin Patch\n*** End Patch"
            cwd = Path("/repo")

        req = ApplyPatchRequest(
            turn_environment=Env(),
            action=Action(),
            file_paths=(Path("a.txt"),),
            changes={Path("a.txt"): FileChange.add("after")},
            exec_approval_requirement=ExecApprovalRequirement.needs_approval(),
        )

        self.assertEqual(apply_patch_approval_keys(req)[0].environment_id, "local")
        self.assertEqual(apply_patch_permission_request_payload(req).tool_input["command"], Action.patch)
        self.assertEqual(apply_patch_permission_request_payload(req).tool_name.name, "apply_patch")
        self.assertEqual(apply_patch_permission_request_payload(req).tool_name.matcher_aliases, ("Write", "Edit"))
        self.assertEqual(apply_patch_sandbox_cwd(req), Path("/repo"))
        self.assertFalse(apply_patch_wants_no_sandbox_approval(AskForApproval.NEVER))
        self.assertTrue(apply_patch_wants_no_sandbox_approval(AskForApproval.ON_FAILURE))
        self.assertTrue(apply_patch_wants_no_sandbox_approval(AskForApproval.ON_REQUEST))
        self.assertTrue(apply_patch_wants_no_sandbox_approval(AskForApproval.UNLESS_TRUSTED))
        self.assertFalse(
            apply_patch_wants_no_sandbox_approval(
                GranularApprovalConfig(
                    sandbox_approval=False,
                    rules=True,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                )
            )
        )
        self.assertTrue(
            apply_patch_wants_no_sandbox_approval(
                GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=True,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                )
            )
        )

    def test_apply_patch_file_system_sandbox_context_uses_active_attempt(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/apply_patch.rs
        # Rust test: file_system_sandbox_context_uses_active_attempt.
        class Env:
            environment_id = "local"

        class Action:
            patch = "*** Begin Patch\n*** End Patch"
            cwd = Path("/repo")

        read_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path("/tmp/allowed")),
            FileSystemAccessMode.READ,
        )
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions((read_entry,)),
            network=NetworkPermissions(enabled=True),
        )
        req = ApplyPatchRequest(
            turn_environment=Env(),
            action=Action(),
            file_paths=(Path("a.txt"),),
            changes={},
            exec_approval_requirement=ExecApprovalRequirement.skip(),
            additional_permissions=additional,
        )
        permissions = PermissionProfile.from_runtime_permissions(
            FileSystemSandboxPolicy.default(),
            NetworkSandboxPolicy.RESTRICTED,
        )
        attempt = SandboxAttempt(
            sandbox=SandboxType.MACOS_SEATBELT,
            permissions=permissions,
            enforce_managed_network=False,
            manager=object(),
            sandbox_cwd=Path("/sandbox"),
            use_legacy_landlock=True,
            windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
            windows_sandbox_private_desktop=True,
        )

        context = apply_patch_file_system_sandbox_context_for_attempt(req, attempt)

        self.assertIsInstance(context, ApplyPatchFileSystemSandboxContext)
        self.assertEqual(context.cwd, Path("/sandbox"))
        self.assertTrue(context.use_legacy_landlock)
        self.assertTrue(context.windows_sandbox_private_desktop)
        self.assertEqual(context.windows_sandbox_level, WindowsSandboxLevel.RESTRICTED_TOKEN)
        self.assertEqual(context.permissions.network_sandbox_policy(), NetworkSandboxPolicy.ENABLED)
        self.assertIn(read_entry, context.permissions.file_system_sandbox_policy().entries)

    def test_apply_patch_no_sandbox_attempt_has_no_file_system_context(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/apply_patch.rs
        # Rust test: no_sandbox_attempt_has_no_file_system_context.
        class Env:
            environment_id = "local"

        class Action:
            patch = "*** Begin Patch\n*** End Patch"
            cwd = Path("/repo")

        req = ApplyPatchRequest(
            turn_environment=Env(),
            action=Action(),
            file_paths=(Path("a.txt"),),
            changes={},
            exec_approval_requirement=ExecApprovalRequirement.skip(),
        )
        attempt = SandboxAttempt(
            sandbox=SandboxType.NONE,
            permissions=PermissionProfile.disabled(),
            enforce_managed_network=False,
            manager=object(),
            sandbox_cwd=Path("/sandbox"),
        )

        self.assertIsNone(apply_patch_file_system_sandbox_context_for_attempt(req, attempt))

    def test_effective_file_system_policy_merges_additional_entries_like_rust(self) -> None:
        base_entry = FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.root()),
            FileSystemAccessMode.READ,
        )
        write_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path("/tmp/allowed")),
            FileSystemAccessMode.WRITE,
        )
        base_policy = FileSystemSandboxPolicy.restricted((base_entry, write_entry))
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions((write_entry,))
        )

        effective = effective_file_system_sandbox_policy(base_policy, additional)

        self.assertEqual(effective.entries, (base_entry, write_entry))

    def test_effective_file_system_policy_ignores_additional_entries_for_non_restricted_policies(self) -> None:
        write_entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path("/tmp/allowed")),
            FileSystemAccessMode.WRITE,
        )
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions((write_entry,))
        )

        self.assertEqual(
            effective_file_system_sandbox_policy(FileSystemSandboxPolicy.unrestricted(), additional),
            FileSystemSandboxPolicy.unrestricted(),
        )
        self.assertEqual(
            effective_file_system_sandbox_policy(FileSystemSandboxPolicy.external_sandbox(), additional),
            FileSystemSandboxPolicy.external_sandbox(),
        )

    def test_effective_file_system_policy_merges_glob_scan_depth_like_rust(self) -> None:
        base_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        additional_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.env"),
            FileSystemAccessMode.DENY,
        )
        base_policy = FileSystemSandboxPolicy(
            FileSystemSandboxKind.RESTRICTED,
            (base_deny,),
            glob_scan_max_depth=2,
        )
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions(
                (additional_deny,),
                glob_scan_max_depth=4,
            )
        )

        effective = effective_file_system_sandbox_policy(base_policy, additional)

        self.assertEqual(effective.glob_scan_max_depth, 4)

    def test_effective_file_system_policy_preserves_unbounded_glob_scan_like_rust(self) -> None:
        base_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        additional_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.env"),
            FileSystemAccessMode.DENY,
        )
        base_policy = FileSystemSandboxPolicy(
            FileSystemSandboxKind.RESTRICTED,
            (base_deny,),
            glob_scan_max_depth=None,
        )
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions(
                (additional_deny,),
                glob_scan_max_depth=4,
            )
        )

        effective = effective_file_system_sandbox_policy(base_policy, additional)

        self.assertIsNone(effective.glob_scan_max_depth)

    def test_shell_runtime_boundaries_shape_keys_payload_and_network_spec(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell.rs
        # Behavior anchors: Approvable<ShellRequest>::approval_keys,
        # exec_approval_requirement, permission_request_payload,
        # sandbox_permissions, and ToolRuntime<ShellRequest>::network_approval_spec.
        approval_requirement = ExecApprovalRequirement.needs_approval()
        req = ShellRequest(
            command=("/bin/bash", "-lc", "echo ok"),
            shell_type=ShellType.BASH,
            hook_command="echo ok",
            cwd=Path("/repo"),
            timeout_ms=None,
            cancellation_token=None,
            env={},
            explicit_env_overrides={},
            network=object(),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            additional_permissions=None,
            justification="because",
            exec_approval_requirement=approval_requirement,
        )

        key = shell_approval_keys(req)[0]
        self.assertEqual(key.command, ("echo", "ok"))
        self.assertEqual(key.cwd, Path("/repo"))
        self.assertEqual(key.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(key.additional_permissions)
        self.assertIs(req.exec_approval_requirement, approval_requirement)
        self.assertEqual(shell_permission_request_payload(req).tool_input["command"], "echo ok")
        self.assertEqual(shell_permission_request_payload(req).tool_input["description"], "because")
        self.assertFalse(req.additional_permissions_preapproved)
        self.assertEqual(req.approval_sandbox_permissions(), SandboxPermissions.USE_DEFAULT)
        spec = shell_network_approval_spec(req, call_id="call-1", tool_name=ToolName.plain("shell_command"))
        self.assertIsInstance(spec, CanonicalNetworkApprovalSpec)
        self.assertEqual(spec.mode, NetworkApprovalMode.IMMEDIATE)
        self.assertEqual(spec.command, "echo ok")
        self.assertIsInstance(spec.trigger, GuardianNetworkAccessTrigger)
        self.assertIs(type(spec.trigger), CanonicalGuardianNetworkAccessTrigger)
        self.assertEqual(spec.trigger.call_id, "call-1")
        self.assertEqual(spec.trigger.tool_name, "shell_command")
        self.assertEqual(spec.trigger.command, req.command)
        self.assertEqual(spec.trigger.cwd, Path("/repo"))
        self.assertEqual(spec.trigger.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(spec.trigger.additional_permissions)
        self.assertEqual(spec.trigger.justification, "because")
        self.assertIsNone(spec.trigger.tty)
        service = NetworkApprovalService()
        active = begin_network_approval(service, "turn-1", True, spec, registration_id="shell-network")
        self.assertIsNotNone(active)
        self.assertIn("shell-network", service.active_calls)
        self.assertEqual(ShellRuntimeBackend.SHELL_COMMAND_CLASSIC.value, "shell_command_classic")

    def test_shell_runtime_approval_keys_canonicalize_shell_wrappers_for_cache(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell.rs
        # Rust helper source: codex-rs/core/src/command_canonicalization.rs
        # Rust tests: canonicalizes_word_only_shell_scripts_to_inner_command
        # and canonicalizes_heredoc_scripts_to_stable_script_key.
        approval_requirement = ExecApprovalRequirement.needs_approval()

        def request(command: tuple[str, ...]) -> ShellRequest:
            return ShellRequest(
                command=command,
                shell_type=ShellType.BASH,
                hook_command=command[-1],
                cwd=Path("/repo"),
                timeout_ms=None,
                cancellation_token=None,
                env={},
                explicit_env_overrides={},
                network=None,
                sandbox_permissions=SandboxPermissions.USE_DEFAULT,
                additional_permissions=None,
                justification=None,
                exec_approval_requirement=approval_requirement,
            )

        command_a = request(("/bin/bash", "-lc", "cargo test -p codex-core"))
        command_b = request(("bash", "-lc", "cargo   test   -p codex-core"))

        self.assertEqual(
            shell_approval_keys(command_a)[0].command,
            ("cargo", "test", "-p", "codex-core"),
        )
        self.assertEqual(shell_approval_keys(command_a)[0].command, shell_approval_keys(command_b)[0].command)

        script = "python3 <<'PY'\nprint('hello')\nPY"
        heredoc = request(("/bin/zsh", "-lc", script))

        self.assertEqual(
            shell_approval_keys(heredoc)[0].command,
            ("__codex_shell_script__", "-lc", script),
        )

    def test_unified_exec_runtime_boundaries_shape_keys_payload_and_deferred_network_spec(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/unified_exec.rs
        # Rust test: unified_exec_uses_the_trusted_sandbox_cwd.
        # Behavior anchors: Approvable<UnifiedExecRequest>::approval_keys,
        # exec_approval_requirement, permission_request_payload,
        # sandbox_permissions, sandbox_cwd, and
        # ToolRuntime<UnifiedExecRequest>::network_approval_spec.
        approval_requirement = ExecApprovalRequirement.skip()
        req = UnifiedExecRequest(
            command=("pwd",),
            shell_type=ShellType.SH,
            hook_command="pwd",
            process_id=42,
            cwd=Path("/repo"),
            sandbox_cwd=Path("/sandbox"),
            environment=object(),
            env={},
            exec_server_env_config=None,
            explicit_env_overrides={},
            network=object(),
            tty=True,
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            additional_permissions=None,
            justification=None,
            exec_approval_requirement=approval_requirement,
            additional_permissions_preapproved=True,
        )

        key = unified_exec_approval_keys(req)[0]
        self.assertEqual(key.command, req.command)
        self.assertEqual(key.cwd, Path("/repo"))
        self.assertTrue(key.tty)
        self.assertEqual(key.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(key.additional_permissions)
        self.assertIs(req.exec_approval_requirement, approval_requirement)
        self.assertTrue(req.additional_permissions_preapproved)
        self.assertEqual(req.approval_sandbox_permissions(), SandboxPermissions.USE_DEFAULT)
        self.assertEqual(unified_exec_permission_request_payload(req).tool_input["command"], "pwd")
        self.assertNotIn("description", unified_exec_permission_request_payload(req).tool_input)
        self.assertEqual(unified_exec_sandbox_cwd(req), Path("/sandbox"))
        spec = unified_exec_network_approval_spec(req, call_id="call-2", tool_name="unified_exec")
        self.assertIsInstance(spec, CanonicalNetworkApprovalSpec)
        self.assertEqual(spec.mode, NetworkApprovalMode.DEFERRED)
        self.assertEqual(spec.command, "pwd")
        self.assertIs(type(spec.trigger), CanonicalGuardianNetworkAccessTrigger)
        self.assertEqual(spec.trigger.call_id, "call-2")
        self.assertEqual(spec.trigger.tool_name, "unified_exec")
        self.assertEqual(spec.trigger.command, req.command)
        self.assertEqual(spec.trigger.cwd, Path("/repo"))
        self.assertEqual(spec.trigger.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(spec.trigger.additional_permissions)
        self.assertIsNone(spec.trigger.justification)
        self.assertTrue(spec.trigger.tty)
        service = NetworkApprovalService()
        active = begin_network_approval(service, "turn-2", True, spec, registration_id="unified-network")
        self.assertIsNotNone(active)
        self.assertIn("unified-network", service.active_calls)
        self.assertEqual(flat_tool_name(ToolName.namespaced("mcp__", "tool")), "mcp__tool")
        self.assertEqual(flat_tool_name("shell_command"), "shell_command")
        with self.assertRaises(TypeError):
            flat_tool_name(123)
        with self.assertRaises(TypeError):
            flat_tool_name("")

    def test_unified_exec_runtime_approval_keys_canonicalize_command_and_keep_tty_scope(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/unified_exec.rs
        # Rust helper source: codex-rs/core/src/command_canonicalization.rs
        # Behavior anchors: Approvable<UnifiedExecRequest>::approval_keys
        # uses canonicalize_command_for_approval and includes tty in the key.
        approval_requirement = ExecApprovalRequirement.needs_approval()

        def request(command: tuple[str, ...], *, tty: bool) -> UnifiedExecRequest:
            return UnifiedExecRequest(
                command=command,
                shell_type=ShellType.BASH,
                hook_command=command[-1],
                process_id=1000,
                cwd=Path("/repo"),
                sandbox_cwd=Path("/sandbox"),
                environment=object(),
                env={},
                exec_server_env_config=None,
                explicit_env_overrides={},
                network=None,
                tty=tty,
                sandbox_permissions=SandboxPermissions.USE_DEFAULT,
                additional_permissions=None,
                justification=None,
                exec_approval_requirement=approval_requirement,
            )

        plain_a = request(("/bin/bash", "-lc", "cargo test -p codex-core"), tty=True)
        plain_b = request(("bash", "-lc", "cargo   test   -p codex-core"), tty=True)
        non_tty = request(("bash", "-lc", "cargo   test   -p codex-core"), tty=False)

        self.assertEqual(
            unified_exec_approval_keys(plain_a)[0].command,
            ("cargo", "test", "-p", "codex-core"),
        )
        self.assertEqual(
            unified_exec_approval_keys(plain_a)[0].command,
            unified_exec_approval_keys(plain_b)[0].command,
        )
        self.assertTrue(unified_exec_approval_keys(plain_a)[0].tty)
        self.assertFalse(unified_exec_approval_keys(non_tty)[0].tty)
        self.assertNotEqual(
            unified_exec_approval_keys(plain_a)[0],
            unified_exec_approval_keys(non_tty)[0],
        )

    def test_unified_exec_options_combines_default_timeout_with_network_denial_cancellation(self) -> None:
        cancellation = CancellationToken()

        options = unified_exec_options(cancellation)

        self.assertIsInstance(options, UnifiedExecOptions)
        self.assertEqual(options.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertEqual(options.expiration.kind, ExecExpirationKind.TIMEOUT_OR_CANCELLATION)
        self.assertEqual(options.expiration.timeout_ms(), DEFAULT_EXEC_COMMAND_TIMEOUT_MS)
        self.assertIs(options.expiration.cancellation, cancellation)

    def test_unified_exec_direct_run_plan_preserves_process_manager_inputs(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/unified_exec.rs
        # Behavior anchor: UnifiedExecRuntime::run direct fallback passes the
        # request process id, tty flag, environment, copied
        # exec_server_env_config, sandbox command, unified options, and
        # NoopSpawnLifecycle into UnifiedExecProcessManager.
        cancellation = CancellationToken()
        env_config = object()
        environment = object()
        req = UnifiedExecRequest(
            command=("python", "-c", "print('ok')"),
            shell_type=ShellType.SH,
            hook_command="python -c print",
            process_id=77,
            cwd=Path("/repo"),
            sandbox_cwd=Path("/sandbox"),
            environment=environment,
            env={"BASE": "1"},
            exec_server_env_config=env_config,
            explicit_env_overrides={},
            network=None,
            tty=False,
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            additional_permissions=None,
            justification=None,
            exec_approval_requirement=ExecApprovalRequirement.skip(),
        )

        plan = unified_exec_direct_run_plan(
            req,
            network_denial_cancellation_token=cancellation,
        )

        self.assertIsInstance(plan, UnifiedExecDirectRunPlan)
        self.assertEqual(plan.process_id, 77)
        self.assertEqual(plan.sandbox_command.program, "python")
        self.assertEqual(plan.sandbox_command.args, ("-c", "print('ok')"))
        self.assertEqual(plan.sandbox_command.cwd, Path("/repo"))
        self.assertEqual(plan.sandbox_command.env["BASE"], "1")
        self.assertEqual(plan.options.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertIs(plan.options.expiration.cancellation, cancellation)
        self.assertFalse(plan.tty)
        self.assertIs(plan.environment, environment)
        self.assertIs(plan.exec_server_env_config, env_config)
        self.assertIsNone(plan.managed_network)
        self.assertEqual(plan.spawn_lifecycle, "noop")

    def test_unified_exec_empty_command_maps_to_missing_pty_line(self) -> None:
        with self.assertRaises(ToolRuntimeError) as ctx:
            build_unified_exec_sandbox_command((), "/repo", {})

        self.assertEqual(ctx.exception.error.message, "missing command line for PTY")

    def test_explicit_escalation_suppresses_runtime_network_specs(self) -> None:
        network = object()

        self.assertIsNone(managed_network_for_runtime(network, SandboxPermissions.REQUIRE_ESCALATED))
        self.assertIs(managed_network_for_runtime(network, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS), network)

    def test_zsh_fork_approval_sandbox_permissions_match_rust_downgrade(self) -> None:
        self.assertEqual(
            approval_sandbox_permissions(SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS, True),
            SandboxPermissions.USE_DEFAULT,
        )
        self.assertEqual(
            approval_sandbox_permissions(SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS, False),
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
        )
        self.assertEqual(
            approval_sandbox_permissions(SandboxPermissions.REQUIRE_ESCALATED, True),
            SandboxPermissions.REQUIRE_ESCALATED,
        )

    def test_shell_request_escalation_execution_matches_rust_cases(self) -> None:
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(write_roots=("/tmp/output",))
        )
        permission_profile = PermissionProfile.from_runtime_permissions(
            FileSystemSandboxPolicy.restricted(
                (
                    FileSystemSandboxEntry(FileSystemPath.explicit_path("/tmp/original/output"), FileSystemAccessMode.WRITE),
                    FileSystemSandboxEntry(FileSystemPath.explicit_path("/tmp/secret"), FileSystemAccessMode.DENY),
                )
            ),
            NetworkSandboxPolicy.RESTRICTED,
        )

        self.assertEqual(
            shell_request_escalation_execution(SandboxPermissions.USE_DEFAULT, permission_profile, None),
            ShellEscalationExecution.turn_default(),
        )
        self.assertEqual(
            shell_request_escalation_execution(SandboxPermissions.REQUIRE_ESCALATED, permission_profile, None),
            ShellEscalationExecution.unsandboxed(),
        )
        self.assertEqual(
            shell_request_escalation_execution(
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                permission_profile,
                additional,
            ),
            ShellEscalationExecution.permissions(permission_profile),
        )
        self.assertEqual(
            shell_request_escalation_execution(SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS, permission_profile, None),
            ShellEscalationExecution.turn_default(),
        )

    def test_shell_escalation_decision_after_review_matches_rust_prompt_outcomes(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()

        self.assertEqual(
            shell_escalation_decision_for_approved_review(False, execution),
            ShellEscalationDecision.run(),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(ReviewDecision.approved(), True, execution),
            ShellEscalationDecision.escalate(execution),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(
                ReviewDecision.network_policy_amendment_decision(
                    NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.ALLOW)
                ),
                False,
                execution,
            ),
            ShellEscalationDecision.run(),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(
                ReviewDecision.network_policy_amendment_decision(
                    NetworkPolicyAmendment("api.example.com", NetworkPolicyRuleAction.DENY)
                ),
                True,
                execution,
            ),
            ShellEscalationDecision.deny("User denied execution"),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(
                ReviewDecision.denied(),
                True,
                execution,
                rejection_message="nope",
            ),
            ShellEscalationDecision.deny("nope"),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(
                ReviewDecision.timed_out(),
                True,
                execution,
                guardian_timeout_message="timed out",
            ),
            ShellEscalationDecision.deny("timed out"),
        )
        self.assertEqual(
            shell_escalation_decision_after_review(ReviewDecision.abort(), True, execution),
            ShellEscalationDecision.deny("User cancelled execution"),
        )

    def test_shell_escalation_decision_for_policy_decision_matches_rust_process_decision(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()

        self.assertEqual(
            shell_escalation_decision_for_policy_decision("forbidden", False, execution),
            ShellEscalationDecision.deny("Execution forbidden by policy"),
        )
        self.assertEqual(
            shell_escalation_decision_for_policy_decision("allow", False, execution),
            ShellEscalationDecision.run(),
        )
        self.assertEqual(
            shell_escalation_decision_for_policy_decision("allow", True, execution),
            ShellEscalationDecision.escalate(execution),
        )
        self.assertEqual(
            shell_escalation_decision_for_policy_decision("prompt", False, execution),
            ShellEscalationDecision.prompt(),
        )
        self.assertEqual(
            shell_escalation_decision_for_policy_decision(
                "prompt",
                False,
                execution,
                prompt_rejection_reason=PROMPT_CONFLICT_REASON,
            ),
            ShellEscalationDecision.deny("Execution forbidden by policy"),
        )

    def test_shell_prepare_escalated_exec_matches_rust_branching(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellCommandExecutor::prepare_escalated_exec.
        default_profile = PermissionProfile.read_only()
        resolved_profile = PermissionProfile.workspace_write()
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(write_roots=("/tmp/output",))
        )
        calls: list[ShellPrepareSandboxedExecParams] = []

        def prepare_sandboxed_exec(params: ShellPrepareSandboxedExecParams) -> ShellPreparedExec:
            calls.append(params)
            return ShellPreparedExec(params.command, params.workdir, params.env, arg0="sandbox-arg0")

        unsandboxed = shell_prepare_escalated_exec(
            "/usr/bin/touch",
            ("touch", "/tmp/file"),
            "/work",
            {"A": "B"},
            ShellEscalationExecution.unsandboxed(),
            permission_profile=default_profile,
            prepare_sandboxed_exec=prepare_sandboxed_exec,
        )
        self.assertEqual(unsandboxed, ShellPreparedExec(("/usr/bin/touch", "/tmp/file"), Path("/work"), {"A": "B"}, arg0="touch"))
        self.assertEqual(calls, [])

        turn_default = shell_prepare_escalated_exec(
            "/usr/bin/touch",
            ("touch", "/tmp/file"),
            "/work",
            {"A": "B"},
            ShellEscalationExecution.turn_default(),
            permission_profile=default_profile,
            prepare_sandboxed_exec=prepare_sandboxed_exec,
        )
        self.assertEqual(turn_default.arg0, "sandbox-arg0")
        self.assertEqual(calls[-1].permission_profile, default_profile)
        self.assertIsNone(calls[-1].additional_permissions)

        shell_prepare_escalated_exec(
            "/usr/bin/touch",
            ("touch", "/tmp/file"),
            "/work",
            {"A": "B"},
            ShellEscalationExecution.permissions(additional),
            permission_profile=default_profile,
            prepare_sandboxed_exec=prepare_sandboxed_exec,
        )
        self.assertEqual(calls[-1].permission_profile, default_profile)
        self.assertEqual(calls[-1].additional_permissions, additional)

        shell_prepare_escalated_exec(
            "/usr/bin/touch",
            ("touch", "/tmp/file"),
            "/work",
            {"A": "B"},
            ShellEscalationExecution.permissions(resolved_profile),
            permission_profile=default_profile,
            prepare_sandboxed_exec=prepare_sandboxed_exec,
        )
        self.assertEqual(calls[-1].permission_profile, resolved_profile)
        self.assertIsNone(calls[-1].additional_permissions)

        with self.assertRaisesRegex(ValueError, r"intercepted exec request must contain argv\[0\]"):
            shell_prepare_escalated_exec(
                "/usr/bin/touch",
                (),
                "/work",
                {},
                ShellEscalationExecution.unsandboxed(),
                permission_profile=default_profile,
                prepare_sandboxed_exec=prepare_sandboxed_exec,
            )
        with self.assertRaises(TypeError):
            shell_prepare_escalated_exec_params(
                ("/usr/bin/touch", "/tmp/file"),
                "/work",
                {},
                ShellEscalationExecution.permissions("profile"),
                permission_profile=default_profile,
            )

    def test_shell_prepare_sandboxed_exec_matches_rust_transform_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellCommandExecutor::prepare_sandboxed_exec.
        profile = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED)
        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(write_roots=("/tmp/output",))
        )

        class FakeNetwork:
            def apply_to_env(self, env: dict[str, str]) -> None:
                env["NETWORK_APPLIED"] = "1"

        class FakeSandboxManager:
            def __init__(self) -> None:
                self.select_calls: list[tuple[object, ...]] = []
                self.transform_calls: list[ShellSandboxTransformRequest] = []

            def select_initial(
                self,
                file_system_policy: FileSystemSandboxPolicy,
                network_policy: NetworkSandboxPolicy,
                preference: str,
                windows_level: WindowsSandboxLevel,
                enforce_network: bool,
            ) -> SandboxType:
                self.select_calls.append(
                    (file_system_policy, network_policy, preference, windows_level, enforce_network)
                )
                return SandboxType.LINUX_SECCOMP

            def transform(self, request: ShellSandboxTransformRequest) -> SandboxExecRequest:
                self.transform_calls.append(request)
                return SandboxExecRequest(
                    command=("sandboxed", *request.command.args),
                    cwd=request.command.cwd,
                    env={**request.command.env, "SANDBOX": "1"},
                    network=request.network,
                    sandbox=request.sandbox,
                    windows_sandbox_level=request.windows_sandbox_level,
                    windows_sandbox_private_desktop=request.windows_sandbox_private_desktop,
                    permission_profile=request.permissions,
                    file_system_sandbox_policy=request.permissions.file_system_sandbox_policy(),
                    network_sandbox_policy=request.permissions.network_sandbox_policy(),
                    arg0="sandbox-arg0",
                )

        manager = FakeSandboxManager()
        context = ShellPrepareSandboxedExecContext(
            sandbox_policy_cwd=Path("/policy"),
            network=FakeNetwork(),
            codex_linux_sandbox_exe=Path("/tmp/codex-linux-sandbox"),
            use_legacy_landlock=True,
            windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
        )

        prepared = shell_prepare_sandboxed_exec(
            ShellPrepareSandboxedExecParams(
                command=("/usr/bin/touch", "/tmp/file"),
                workdir=Path("/work"),
                env={"A": "B"},
                permission_profile=profile,
                additional_permissions=additional,
            ),
            context,
            sandbox_manager=manager,
        )

        file_system_policy, network_policy = profile.to_runtime_permissions()
        self.assertEqual(
            manager.select_calls,
            [(file_system_policy, network_policy, "auto", WindowsSandboxLevel.RESTRICTED_TOKEN, True)],
        )
        request = manager.transform_calls[0]
        self.assertEqual(request.command, SandboxCommand("/usr/bin/touch", ("/tmp/file",), Path("/work"), {"A": "B"}, additional))
        self.assertEqual(request.permissions, profile)
        self.assertEqual(request.sandbox, SandboxType.LINUX_SECCOMP)
        self.assertTrue(request.enforce_managed_network)
        self.assertEqual(request.sandbox_policy_cwd, Path("/policy"))
        self.assertEqual(request.codex_linux_sandbox_exe, Path("/tmp/codex-linux-sandbox"))
        self.assertTrue(request.use_legacy_landlock)
        self.assertFalse(request.windows_sandbox_private_desktop)
        self.assertEqual(
            prepared,
            ShellPreparedExec(
                ("sandboxed", "/tmp/file"),
                Path("/work"),
                {"A": "B", "SANDBOX": "1", "NETWORK_APPLIED": "1"},
                arg0="sandbox-arg0",
            ),
        )
        with self.assertRaisesRegex(ValueError, "prepared command must not be empty"):
            shell_prepare_sandboxed_exec(
                ShellPrepareSandboxedExecParams((), Path("/work"), {}, profile),
                context,
                sandbox_manager=manager,
            )

    def test_shell_escalate_action_from_decision_matches_rust_wire_actions(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()

        self.assertEqual(shell_escalate_action_from_decision(ShellEscalationDecision.run()), ShellEscalateAction.run())
        self.assertEqual(
            shell_escalate_action_from_decision(ShellEscalationDecision.escalate(execution)),
            ShellEscalateAction.escalate(),
        )
        self.assertEqual(
            shell_escalate_action_from_decision(ShellEscalationDecision.deny("blocked")),
            ShellEscalateAction.deny("blocked"),
        )
        self.assertEqual(
            shell_escalate_action_from_decision(ShellEscalationDecision.deny()),
            ShellEscalateAction.deny(),
        )
        self.assertEqual(ShellEscalateAction.deny("blocked").to_mapping(), {"type": "deny", "reason": "blocked"})
        self.assertEqual(ShellEscalateAction.from_mapping({"type": "escalate"}), ShellEscalateAction.escalate())
        response = ShellEscalateResponse(ShellEscalateAction.deny("blocked"))
        self.assertEqual(response.to_mapping(), {"action": {"type": "deny", "reason": "blocked"}})
        self.assertEqual(ShellEscalateResponse.from_mapping(response.to_mapping()), response)
        self.assertEqual(
            ShellEscalateResponse.from_mapping({"action": {"type": "run"}}),
            ShellEscalateResponse(ShellEscalateAction.run()),
        )
        with self.assertRaisesRegex(TypeError, "shell escalate action must be a mapping"):
            ShellEscalateResponse.from_mapping({"action": "run"})
        with self.assertRaisesRegex(TypeError, "shell escalate action must be a mapping"):
            ShellEscalateResponse.from_mapping({})
        with self.assertRaises(ValueError):
            shell_escalate_action_from_decision(ShellEscalationDecision.prompt())
        with self.assertRaisesRegex(ValueError, "unknown shell escalate action type"):
            ShellEscalateAction.from_mapping({"type": "maybe"})
        with self.assertRaisesRegex(TypeError, "shell escalate action must be a mapping"):
            ShellEscalateAction.from_mapping(object())

    def test_shell_escalate_request_matches_rust_wire_shape(self) -> None:
        request = ShellEscalateRequest("/bin/sh", ["/bin/sh", "-lc", "echo ok"], "/work", {"A": "B"})

        self.assertEqual(request.file, Path("/bin/sh"))
        self.assertEqual(request.argv, ("/bin/sh", "-lc", "echo ok"))
        self.assertEqual(request.workdir, Path("/work"))
        self.assertEqual(request.env, {"A": "B"})
        self.assertEqual(
            request.to_mapping(),
            {"file": "/bin/sh", "argv": ["/bin/sh", "-lc", "echo ok"], "workdir": "/work", "env": {"A": "B"}},
        )
        self.assertEqual(ShellEscalateRequest.from_mapping(request.to_mapping()), request)
        with self.assertRaises(TypeError):
            ShellEscalateRequest("/bin/sh", [object()], "/work", {})
        with self.assertRaises(TypeError):
            ShellEscalateRequest("/bin/sh", ["/bin/sh"], "/work", {"A": 1})
        with self.assertRaises(TypeError):
            ShellEscalateRequest.from_mapping(object())

    def test_shell_escalate_policy_input_from_request_resolves_program_against_workdir(self) -> None:
        request = ShellEscalateRequest("bin/tool", ["tool", "--flag"], "/work", {"A": "B"})

        self.assertEqual(
            shell_escalate_policy_input_from_request(request),
            ShellEscalatePolicyInput(Path("/work/bin/tool"), ("tool", "--flag"), Path("/work")),
        )
        self.assertEqual(
            shell_escalate_policy_input_from_request(
                {"file": "/bin/sh", "argv": ["/bin/sh"], "workdir": "/work", "env": {"A": "B"}}
            ),
            ShellEscalatePolicyInput(Path("/bin/sh"), ("/bin/sh",), Path("/work")),
        )
        with self.assertRaises(TypeError):
            ShellEscalatePolicyInput("/bin/sh", [object()], "/work")
        with self.assertRaises(TypeError):
            shell_escalate_policy_input_from_request(object())

    def test_shell_escalate_decision_for_request_calls_policy_with_resolved_inputs(self) -> None:
        calls: list[tuple[Path, tuple[str, ...], Path]] = []

        def determine_action(program: Path, argv: tuple[str, ...], workdir: Path) -> ShellEscalationDecision:
            calls.append((program, argv, workdir))
            return ShellEscalationDecision.run()

        request = ShellEscalateRequest("bin/tool", ["tool"], "/work", {"A": "B"})

        self.assertEqual(shell_escalate_decision_for_request(request, determine_action), ShellEscalationDecision.run())
        self.assertEqual(calls, [(Path("/work/bin/tool"), ("tool",), Path("/work"))])

        def bad_determine_action(program: Path, argv: tuple[str, ...], workdir: Path) -> str:
            return "run"

        with self.assertRaises(TypeError):
            shell_escalate_decision_for_request(request, bad_determine_action)

    def test_shell_escalate_response_from_decision_wraps_wire_action(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()

        self.assertEqual(
            shell_escalate_response_from_decision(ShellEscalationDecision.run()),
            ShellEscalateResponse(ShellEscalateAction.run()),
        )
        self.assertEqual(
            shell_escalate_response_from_decision(ShellEscalationDecision.escalate(execution)),
            ShellEscalateResponse(ShellEscalateAction.escalate()),
        )
        self.assertEqual(
            shell_escalate_response_from_decision(ShellEscalationDecision.deny("blocked")),
            ShellEscalateResponse(ShellEscalateAction.deny("blocked")),
        )
        self.assertEqual(
            shell_escalate_response_from_decision(ShellEscalationDecision.deny()).to_mapping(),
            {"action": {"type": "deny", "reason": None}},
        )
        with self.assertRaises(ValueError):
            shell_escalate_response_from_decision(ShellEscalationDecision.prompt())

    def test_shell_escalate_server_plan_from_decision_preserves_execution_branch(self) -> None:
        execution = ShellEscalationExecution.permissions("profile")

        self.assertEqual(
            shell_escalate_server_plan_from_decision(ShellEscalationDecision.run()),
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.run())),
        )
        self.assertEqual(
            shell_escalate_server_plan_from_decision(ShellEscalationDecision.escalate(execution)),
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.escalate()), execution=execution),
        )
        self.assertEqual(
            shell_escalate_server_plan_from_decision(ShellEscalationDecision.deny("blocked")),
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.deny("blocked"))),
        )
        self.assertEqual(
            ShellEscalateServerPlan({"action": {"type": "run"}}),
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.run())),
        )
        with self.assertRaises(ValueError):
            shell_escalate_server_plan_from_decision(ShellEscalationDecision.prompt())
        with self.assertRaises(TypeError):
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.escalate()))
        with self.assertRaises(ValueError):
            ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.run()), execution=execution)

    def test_shell_escalate_server_plan_send_response_returns_escalate_execution(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()
        sent: list[ShellEscalateResponse] = []

        def send_response(response: ShellEscalateResponse) -> None:
            sent.append(response)

        run_plan = ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.run()))
        self.assertIsNone(shell_escalate_server_plan_send_response(run_plan, send_response))
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.run()))

        escalate_plan = ShellEscalateServerPlan(
            ShellEscalateResponse(ShellEscalateAction.escalate()),
            execution=execution,
        )
        self.assertEqual(shell_escalate_server_plan_send_response(escalate_plan, send_response), execution)
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.escalate()))

        deny_plan = ShellEscalateServerPlan(ShellEscalateResponse(ShellEscalateAction.deny("blocked")))
        self.assertIsNone(shell_escalate_server_plan_send_response(deny_plan, send_response))
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.deny("blocked")))
        with self.assertRaises(TypeError):
            shell_escalate_server_plan_send_response(object(), send_response)

    def test_shell_escalate_server_decision_send_response_composes_decision_branch(self) -> None:
        execution = ShellEscalationExecution.turn_default()
        sent: list[ShellEscalateResponse] = []

        def send_response(response: ShellEscalateResponse) -> None:
            sent.append(response)

        self.assertIsNone(shell_escalate_server_decision_send_response(ShellEscalationDecision.run(), send_response))
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.run()))

        self.assertEqual(
            shell_escalate_server_decision_send_response(
                ShellEscalationDecision.escalate(execution),
                send_response,
            ),
            execution,
        )
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.escalate()))

        self.assertIsNone(
            shell_escalate_server_decision_send_response(
                ShellEscalationDecision.deny("blocked"),
                send_response,
            )
        )
        self.assertEqual(sent[-1], ShellEscalateResponse(ShellEscalateAction.deny("blocked")))
        with self.assertRaises(ValueError):
            shell_escalate_server_decision_send_response(ShellEscalationDecision.prompt(), send_response)

    def test_shell_escalate_server_continue_after_response_runs_super_exec_branch(self) -> None:
        execution = ShellEscalationExecution.unsandboxed()
        received: list[str] = []
        prepared_calls: list[ShellEscalationExecution] = []
        sent_results: list[ShellSuperExecResult] = []

        def receive_super_exec() -> tuple[ShellSuperExecMessage, tuple[int, ...]]:
            received.append("receive")
            return ShellSuperExecMessage((0,)), (10,)

        def prepare_exec(received_execution: ShellEscalationExecution) -> ShellPreparedExec:
            prepared_calls.append(received_execution)
            return ShellPreparedExec(["/bin/sh"], Path("/work"), {})

        class FakeChild:
            def poll(self) -> int:
                return 5

            def wait(self) -> int:
                return 5

            def kill(self) -> None:
                raise AssertionError("completed child should not be killed")

        def popen_factory(**kwargs: object) -> FakeChild:
            return FakeChild()

        def send_result(result: ShellSuperExecResult) -> None:
            sent_results.append(result)

        result = shell_escalate_server_continue_after_response(
            execution,
            receive_super_exec=receive_super_exec,
            prepare_exec=prepare_exec,
            send_result=send_result,
            popen_factory=popen_factory,
            poll_interval=0,
        )

        self.assertEqual(result, ShellSuperExecResult(5))
        self.assertEqual(received, ["receive"])
        self.assertEqual(prepared_calls, [execution])
        self.assertEqual(sent_results, [ShellSuperExecResult(5)])
        self.assertIsNone(
            shell_escalate_server_continue_after_response(
                None,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )
        )
        with self.assertRaises(TypeError):
            shell_escalate_server_continue_after_response(
                object(),
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )

    def test_shell_escalate_server_decision_run_composes_response_and_continue(self) -> None:
        sent_responses: list[ShellEscalateResponse] = []
        sent_results: list[ShellSuperExecResult] = []
        prepared_calls: list[ShellEscalationExecution] = []

        def send_response(response: ShellEscalateResponse) -> None:
            sent_responses.append(response)

        def receive_super_exec() -> tuple[ShellSuperExecMessage, tuple[int, ...]]:
            return ShellSuperExecMessage((0,)), (10,)

        def prepare_exec(execution: ShellEscalationExecution) -> ShellPreparedExec:
            prepared_calls.append(execution)
            return ShellPreparedExec(["/bin/sh"], Path("/work"), {})

        class FakeChild:
            def poll(self) -> int:
                return 9

            def wait(self) -> int:
                return 9

            def kill(self) -> None:
                raise AssertionError("completed child should not be killed")

        def popen_factory(**kwargs: object) -> FakeChild:
            return FakeChild()

        def send_result(result: ShellSuperExecResult) -> None:
            sent_results.append(result)

        self.assertIsNone(
            shell_escalate_server_decision_run(
                ShellEscalationDecision.run(),
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )
        )
        self.assertEqual(sent_responses[-1], ShellEscalateResponse(ShellEscalateAction.run()))
        self.assertEqual(sent_results, [])

        execution = ShellEscalationExecution.turn_default()
        self.assertEqual(
            shell_escalate_server_decision_run(
                ShellEscalationDecision.escalate(execution),
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
                popen_factory=popen_factory,
                poll_interval=0,
            ),
            ShellSuperExecResult(9),
        )
        self.assertEqual(sent_responses[-1], ShellEscalateResponse(ShellEscalateAction.escalate()))
        self.assertEqual(prepared_calls, [execution])
        self.assertEqual(sent_results, [ShellSuperExecResult(9)])

        self.assertIsNone(
            shell_escalate_server_decision_run(
                ShellEscalationDecision.deny("blocked"),
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )
        )
        self.assertEqual(sent_responses[-1], ShellEscalateResponse(ShellEscalateAction.deny("blocked")))
        with self.assertRaises(ValueError):
            shell_escalate_server_decision_run(
                ShellEscalationDecision.prompt(),
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )

    def test_shell_escalate_server_request_run_preserves_request_field_flow(self) -> None:
        request = ShellEscalateRequest("bin/tool", ["tool"], "/work", {"A": "B"})
        execution = ShellEscalationExecution.permissions("profile")
        policy_calls: list[tuple[Path, tuple[str, ...], Path]] = []
        prepare_calls: list[tuple[Path, tuple[str, ...], Path, dict[str, str], ShellEscalationExecution]] = []
        sent_responses: list[ShellEscalateResponse] = []
        sent_results: list[ShellSuperExecResult] = []

        def determine_action(program: Path, argv: tuple[str, ...], workdir: Path) -> ShellEscalationDecision:
            policy_calls.append((program, argv, workdir))
            return ShellEscalationDecision.escalate(execution)

        def send_response(response: ShellEscalateResponse) -> None:
            sent_responses.append(response)

        def receive_super_exec() -> tuple[ShellSuperExecMessage, tuple[int, ...]]:
            return ShellSuperExecMessage((0,)), (10,)

        def prepare_exec(
            program: Path,
            argv: tuple[str, ...],
            workdir: Path,
            env: dict[str, str],
            received_execution: ShellEscalationExecution,
        ) -> ShellPreparedExec:
            prepare_calls.append((program, argv, workdir, env, received_execution))
            return ShellPreparedExec(["/bin/sh"], workdir, env)

        class FakeChild:
            def poll(self) -> int:
                return 6

            def wait(self) -> int:
                return 6

            def kill(self) -> None:
                raise AssertionError("completed child should not be killed")

        def popen_factory(**kwargs: object) -> FakeChild:
            return FakeChild()

        def send_result(result: ShellSuperExecResult) -> None:
            sent_results.append(result)

        self.assertEqual(
            shell_escalate_server_request_run(
                request,
                determine_action=determine_action,
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
                popen_factory=popen_factory,
                poll_interval=0,
            ),
            ShellSuperExecResult(6),
        )
        self.assertEqual(policy_calls, [(Path("/work/bin/tool"), ("tool",), Path("/work"))])
        self.assertEqual(
            prepare_calls,
            [(Path("/work/bin/tool"), ("tool",), Path("/work"), {"A": "B"}, execution)],
        )
        self.assertEqual(sent_responses, [ShellEscalateResponse(ShellEscalateAction.escalate())])
        self.assertEqual(sent_results, [ShellSuperExecResult(6)])

        def run_policy(program: Path, argv: tuple[str, ...], workdir: Path) -> ShellEscalationDecision:
            return ShellEscalationDecision.run()

        self.assertIsNone(
            shell_escalate_server_request_run(
                request,
                determine_action=run_policy,
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=prepare_exec,
                send_result=send_result,
            )
        )

        def bad_prepare(
            program: Path,
            argv: tuple[str, ...],
            workdir: Path,
            env: dict[str, str],
            received_execution: ShellEscalationExecution,
        ) -> str:
            return "bad"

        with self.assertRaises(TypeError):
            shell_escalate_server_request_run(
                request,
                determine_action=determine_action,
                send_response=send_response,
                receive_super_exec=receive_super_exec,
                prepare_exec=bad_prepare,
                send_result=send_result,
                popen_factory=popen_factory,
                poll_interval=0,
            )

    def test_shell_escalate_client_action_from_response_matches_client_branches(self) -> None:
        self.assertEqual(
            shell_escalate_client_action_from_response(ShellEscalateResponse(ShellEscalateAction.run())),
            ShellEscalateClientAction.run(),
        )
        self.assertEqual(
            shell_escalate_client_action_from_response({"action": {"type": "escalate"}}),
            ShellEscalateClientAction.escalate(),
        )
        self.assertEqual(
            shell_escalate_client_action_from_response(
                ShellEscalateResponse(ShellEscalateAction.deny("blocked"))
            ),
            ShellEscalateClientAction.deny("blocked"),
        )
        self.assertEqual(
            shell_escalate_client_action_from_response(ShellEscalateResponse(ShellEscalateAction.deny())),
            ShellEscalateClientAction("deny", exit_code=1, message="Execution denied"),
        )
        self.assertEqual(ShellEscalateClientAction.deny("blocked").exit_code, 1)
        self.assertEqual(ShellEscalateClientAction.deny("blocked").message, "Execution denied: blocked")
        with self.assertRaises(ValueError):
            ShellEscalateClientAction("run", exit_code=1)
        with self.assertRaises(TypeError):
            ShellEscalateClientAction.deny(123)
        with self.assertRaisesRegex(TypeError, "shell escalate response must be a mapping"):
            shell_escalate_client_action_from_response(object())

    def test_shell_local_execv_plan_matches_client_run_branch_boundaries(self) -> None:
        plan = shell_local_execv_plan("/bin/sh", ["/bin/sh", "-lc", "echo ok"])

        self.assertEqual(plan, ShellLocalExecvPlan("/bin/sh", ("/bin/sh", "-lc", "echo ok")))
        self.assertEqual(ShellLocalExecvPlan("/bin/sh", ["/bin/sh"]).argv, ("/bin/sh",))
        with self.assertRaisesRegex(ValueError, "NUL in file"):
            shell_local_execv_plan("/bin/sh\0bad", ["/bin/sh"])
        with self.assertRaisesRegex(ValueError, "NUL in argv"):
            shell_local_execv_plan("/bin/sh", ["/bin/sh", "bad\0arg"])
        with self.assertRaises(TypeError):
            shell_local_execv_plan(123, ["/bin/sh"])
        with self.assertRaises(TypeError):
            shell_local_execv_plan("/bin/sh", [object()])

    def test_shell_local_execv_run_calls_execv_with_validated_plan(self) -> None:
        calls: list[tuple[str, tuple[str, ...]]] = []

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            calls.append((file, argv))
            return "replaced"

        plan = shell_local_execv_plan("/bin/sh", ["/bin/sh", "-lc", "echo ok"])

        self.assertEqual(shell_local_execv_run(plan, execv=fake_execv), "replaced")
        self.assertEqual(calls, [("/bin/sh", ("/bin/sh", "-lc", "echo ok"))])
        with self.assertRaises(TypeError):
            shell_local_execv_run(object())

    def test_shell_escalate_client_plan_from_response_composes_client_branches(self) -> None:
        run_plan = shell_escalate_client_plan_from_response(
            ShellEscalateResponse(ShellEscalateAction.run()),
            "/bin/sh",
            ["/bin/sh", "-lc", "echo ok"],
        )
        self.assertEqual(
            run_plan,
            ShellEscalateClientPlan(
                ShellEscalateClientAction.run(),
                local_execv=ShellLocalExecvPlan("/bin/sh", ("/bin/sh", "-lc", "echo ok")),
            ),
        )

        escalate_plan = shell_escalate_client_plan_from_response(
            {"action": {"type": "escalate"}},
            "/bin/sh",
            ["/bin/sh"],
            destination_fds=(10, 11, 12),
        )
        self.assertEqual(
            escalate_plan,
            ShellEscalateClientPlan(
                ShellEscalateClientAction.escalate(),
                super_exec=ShellSuperExecMessage((10, 11, 12)),
            ),
        )

        deny_plan = shell_escalate_client_plan_from_response(
            ShellEscalateResponse(ShellEscalateAction.deny("blocked")),
            "/bin/sh",
            ["/bin/sh"],
        )
        self.assertEqual(deny_plan, ShellEscalateClientPlan(ShellEscalateClientAction.deny("blocked")))
        with self.assertRaisesRegex(ValueError, "NUL in file"):
            shell_escalate_client_plan_from_response(ShellEscalateResponse(ShellEscalateAction.run()), "bad\0file", [])
        with self.assertRaisesRegex(TypeError, "shell escalate response must be a mapping"):
            shell_escalate_client_plan_from_response(object(), "/bin/sh", ["/bin/sh"])
        with self.assertRaisesRegex(TypeError, "fds must be an integer file descriptor"):
            shell_escalate_client_plan_from_response(
                {"action": {"type": "escalate"}},
                "/bin/sh",
                ["/bin/sh"],
                destination_fds=("bad",),
            )
        with self.assertRaises(TypeError):
            ShellEscalateClientPlan(ShellEscalateClientAction.run())
        with self.assertRaises(ValueError):
            ShellEscalateClientPlan(ShellEscalateClientAction.deny(), local_execv=ShellLocalExecvPlan("/bin/sh", ()))

    def test_shell_escalate_client_plan_run_executes_planned_client_branch(self) -> None:
        execv_calls: list[tuple[str, tuple[str, ...]]] = []

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            execv_calls.append((file, argv))
            return "execv-called"

        run_plan = ShellEscalateClientPlan(
            ShellEscalateClientAction.run(),
            local_execv=ShellLocalExecvPlan("/bin/sh", ("/bin/sh",)),
        )
        self.assertEqual(shell_escalate_client_plan_run(run_plan, execv=fake_execv), "execv-called")
        self.assertEqual(execv_calls, [("/bin/sh", ("/bin/sh",))])

        super_exec_calls: list[tuple[ShellSuperExecMessage | None, tuple[int, ...]]] = []

        def fake_super_exec(message: ShellSuperExecMessage | None, transferred_fds: tuple[int, ...]) -> ShellSuperExecResult:
            super_exec_calls.append((message, transferred_fds))
            return ShellSuperExecResult(42)

        def fake_dup(fd: int) -> int:
            return fd + 100

        escalate_plan = ShellEscalateClientPlan(
            ShellEscalateClientAction.escalate(),
            super_exec=ShellSuperExecMessage((0, 1, 2)),
        )
        self.assertEqual(
            shell_escalate_client_plan_run(
                escalate_plan,
                super_exec=fake_super_exec,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            42,
        )
        self.assertEqual(super_exec_calls, [(ShellSuperExecMessage((0, 1, 2)), (100, 101, 102))])

        split_calls: list[tuple[ShellSuperExecMessage, tuple[int, ...]] | tuple[str]] = []

        def fake_super_exec_send_with_fds(message: ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            split_calls.append((message, transferred_fds))

        def fake_super_exec_receive_result() -> ShellSuperExecResult:
            split_calls.append(("receive",))
            return ShellSuperExecResult(43)

        self.assertEqual(
            shell_escalate_client_plan_run(
                escalate_plan,
                super_exec_send_with_fds=fake_super_exec_send_with_fds,
                super_exec_receive_result=fake_super_exec_receive_result,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            43,
        )
        self.assertEqual(split_calls, [(ShellSuperExecMessage((0, 1, 2)), (100, 101, 102)), ("receive",)])

        class FakeStderr:
            def __init__(self) -> None:
                self.text = ""

            def write(self, value: str) -> None:
                self.text += value

        stderr = FakeStderr()
        deny_plan = ShellEscalateClientPlan(ShellEscalateClientAction.deny("blocked"))
        self.assertEqual(shell_escalate_client_plan_run(deny_plan, stderr=stderr), 1)
        self.assertEqual(stderr.text, "Execution denied: blocked\n")

        super_exec_split_calls: list[Any] = []

        def send_escalate_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            super_exec_split_calls.append(("request", request))
            return ShellEscalateResponse(ShellEscalateAction.escalate())

        def fake_super_exec_send_with_fds(
            value_client: object,
            message: ShellSuperExecMessage,
            transferred_fds: tuple[int, ...],
        ) -> None:
            super_exec_split_calls.append(("super_exec_send", value_client, message, transferred_fds))

        def fake_super_exec_receive_result(value_client: object) -> ShellSuperExecResult:
            super_exec_split_calls.append(("super_exec_receive", value_client))
            return ShellSuperExecResult(56)

        def fake_dup(fd: int) -> int:
            return fd + 40

        client = object()
        plan = ShellEscalateClientWrapperPlan(
            ShellEscalateClientSocketPair(object(), client, 41, 42),
            ShellEscalateClientHandshakePlan(42, b"\0", (17,)),
        )

        def fake_send_with_fds(_fd: int, _message: bytes, _fds: tuple[int, ...]) -> None:
            return None

        payload = json.dumps({"fds": [7, 8, 9]}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload

        self.assertEqual(
            shell_escalate_client_wrapper_plan_run(
                plan,
                "/bin/sh",
                ["/bin/sh"],
                send_with_fds=fake_send_with_fds,
                send_request=send_escalate_request,
                workdir="/work",
                env={},
                destination_fds=(7, 8, 9),
                super_exec_send_with_fds=fake_super_exec_send_with_fds,
                super_exec_receive_result=fake_super_exec_receive_result,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            56,
        )
        self.assertEqual(
            super_exec_split_calls,
            [
                ("request", ShellEscalateRequest("/bin/sh", ("/bin/sh",), Path("/work"), {})),
                ("super_exec_send", client, framed_payload, (40, 41, 42)),
                ("super_exec_receive", client),
            ],
        )
        with self.assertRaisesRegex(
            TypeError, "super-exec execution requires super_exec or split super_exec callbacks"
        ):
            shell_escalate_client_plan_run(escalate_plan)
        with self.assertRaisesRegex(
            TypeError,
            "super_exec_send_with_fds and super_exec_receive_result must be both provided",
        ):
            shell_escalate_client_plan_run(
                escalate_plan,
                super_exec_send_with_fds=lambda *_args: None,
            )
        with self.assertRaisesRegex(
            TypeError,
            "super_exec_send_with_fds and super_exec_receive_result must be both provided",
        ):
            shell_escalate_client_plan_run(
                escalate_plan,
                super_exec_receive_result=lambda: ShellSuperExecResult(44),
            )
        with self.assertRaises(TypeError):
            shell_escalate_client_plan_run(object())

    def test_shell_escalate_client_response_run_composes_response_to_execution(self) -> None:
        execv_calls: list[tuple[str, tuple[str, ...]]] = []

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            execv_calls.append((file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_response_run(
                {"action": {"type": "run"}},
                "/bin/sh",
                ["/bin/sh"],
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(execv_calls, [("/bin/sh", ("/bin/sh",))])

        super_exec_calls: list[tuple[ShellSuperExecMessage | None, tuple[int, ...]]] = []

        def fake_super_exec(message: ShellSuperExecMessage | None, transferred_fds: tuple[int, ...]) -> dict[str, int]:
            super_exec_calls.append((message, transferred_fds))
            return {"exit_code": 17}

        def fake_dup(fd: int) -> int:
            return fd + 10

        self.assertEqual(
            shell_escalate_client_response_run(
                ShellEscalateResponse(ShellEscalateAction.escalate()),
                "/bin/sh",
                ["/bin/sh"],
                destination_fds=(7, 8, 9),
                super_exec=fake_super_exec,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            17,
        )
        self.assertEqual(super_exec_calls, [(ShellSuperExecMessage((7, 8, 9)), (10, 11, 12))])

        class FakeStderr:
            def __init__(self) -> None:
                self.text = ""

            def write(self, value: str) -> None:
                self.text += value

        stderr = FakeStderr()
        self.assertEqual(
            shell_escalate_client_response_run(
                ShellEscalateResponse(ShellEscalateAction.deny()),
                "/bin/sh",
                ["/bin/sh"],
                stderr=stderr,
            ),
            1,
        )
        self.assertEqual(stderr.text, "Execution denied\n")

    def test_shell_escalate_client_request_run_sends_request_then_runs_response(self) -> None:
        sent_requests: list[ShellEscalateRequest] = []
        execv_calls: list[tuple[str, tuple[str, ...]]] = []

        def send_run_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            sent_requests.append(request)
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            execv_calls.append((file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_request_run(
                "bin/tool",
                ["tool"],
                send_request=send_run_request,
                workdir="/work",
                env={"A": "B", "CODEX_ESCALATE_SOCKET": "42"},
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(sent_requests, [ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {"A": "B"})])
        self.assertEqual(execv_calls, [("bin/tool", ("tool",))])

        super_exec_calls: list[tuple[ShellSuperExecMessage | None, tuple[int, ...]]] = []

        def send_escalate_request(request: ShellEscalateRequest) -> dict[str, dict[str, str]]:
            return {"action": {"type": "escalate"}}

        def fake_super_exec(message: ShellSuperExecMessage | None, transferred_fds: tuple[int, ...]) -> ShellSuperExecResult:
            super_exec_calls.append((message, transferred_fds))
            return ShellSuperExecResult(21)

        def fake_dup(fd: int) -> int:
            return fd + 20

        self.assertEqual(
            shell_escalate_client_request_run(
                "/bin/sh",
                ["/bin/sh"],
                send_request=send_escalate_request,
                workdir="/work",
                env={},
                destination_fds=(7, 8, 9),
                super_exec=fake_super_exec,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            21,
        )
        self.assertEqual(super_exec_calls, [(ShellSuperExecMessage((7, 8, 9)), (20, 21, 22))])

    def test_shell_escalate_client_request_exchange_matches_send_receive_contexts(self) -> None:
        request = ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {"A": "B"})
        sent_requests: list[ShellEscalateRequest] = []

        def fake_send_request(value: ShellEscalateRequest) -> None:
            sent_requests.append(value)

        def fake_receive_response() -> dict[str, dict[str, str]]:
            return {"action": {"type": "run"}}

        self.assertEqual(
            shell_escalate_client_request_exchange(
                request,
                send_request=fake_send_request,
                receive_response=fake_receive_response,
            ),
            ShellEscalateResponse(ShellEscalateAction.run()),
        )
        self.assertEqual(sent_requests, [request])
        with self.assertRaisesRegex(RuntimeError, "failed to send EscalateRequest"):
            shell_escalate_client_request_exchange(
                request,
                send_request=lambda _request: (_ for _ in ()).throw(OSError("send failed")),
            )
        with self.assertRaisesRegex(RuntimeError, "failed to receive EscalateResponse"):
            shell_escalate_client_request_exchange(
                request,
                send_request=fake_send_request,
                receive_response=lambda: (_ for _ in ()).throw(OSError("receive failed")),
            )

    def test_shell_escalate_client_request_exchange_passes_client_to_split_socket_callbacks(self) -> None:
        request = ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {"A": "B"})
        client = object()
        calls: list[Any] = []

        def fake_send_request(value_client: object, value_request: ShellEscalateRequest) -> None:
            calls.append(("send", value_client, value_request))

        def fake_receive_response(value_client: object) -> ShellEscalateResponse:
            calls.append(("receive", value_client))
            return ShellEscalateResponse(ShellEscalateAction.run())

        self.assertEqual(
            shell_escalate_client_request_exchange(
                request,
                send_request=fake_send_request,
                receive_response=fake_receive_response,
                client=client,
            ),
            ShellEscalateResponse(ShellEscalateAction.run()),
        )
        self.assertEqual(calls, [("send", client, request), ("receive", client)])

    def test_shell_escalate_client_request_run_sends_split_request_response_with_client(self) -> None:
        calls: list[Any] = []
        client = object()

        def fake_send_request(value_client: object, request: ShellEscalateRequest) -> ShellEscalateResponse:
            calls.append(("request", value_client, request))
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_receive_response(value_client: object) -> ShellEscalateResponse:
            calls.append(("receive", value_client))
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            calls.append(("execv", file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_request_run(
                "bin/tool",
                ["tool"],
                workdir="/work",
                send_request=fake_send_request,
                receive_response=fake_receive_response,
                client=client,
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(
            calls,
            [
                ("request", client, ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {})),
                ("receive", client),
                ("execv", "bin/tool", ("tool",)),
            ],
        )

    def test_shell_escalate_client_wrapper_run_sends_handshake_before_request(self) -> None:
        calls: list[Any] = []

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        def fake_send_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            calls.append(("request", request))
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            calls.append(("execv", file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_wrapper_run(
                "bin/tool",
                ["tool"],
                server_socket_fd=17,
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                workdir="/work",
                env={"A": "B", "CODEX_ESCALATE_SOCKET": "42", "EXEC_WRAPPER": "/tmp/exec-wrapper"},
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(
            calls,
            [
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {"A": "B"})),
                ("execv", "bin/tool", ("tool",)),
            ],
        )

    def test_shell_escalate_client_wrapper_run_supports_split_request_receive(self) -> None:
        calls: list[Any] = []

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        def fake_send_request(request: ShellEscalateRequest) -> None:
            calls.append(("request", request))

        def fake_receive_response() -> ShellEscalateResponse:
            calls.append(("receive",))
            return ShellEscalateResponse(ShellEscalateAction.deny("blocked"))

        class FakeStderr:
            def __init__(self) -> None:
                self.text = ""

            def write(self, value: str) -> None:
                self.text += value

        stderr = FakeStderr()
        self.assertEqual(
            shell_escalate_client_wrapper_run(
                "/bin/sh",
                ["/bin/sh"],
                server_socket_fd=17,
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                receive_response=fake_receive_response,
                workdir="/work",
                env={"CODEX_ESCALATE_SOCKET": "42"},
                stderr=stderr,
            ),
            1,
        )
        self.assertEqual(
            calls,
            [
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("/bin/sh", ("/bin/sh",), Path("/work"), {})),
                ("receive",),
            ],
        )
        self.assertEqual(stderr.text, "Execution denied: blocked\n")

    def test_shell_escalate_client_wrapper_run_supports_split_super_exec_exchange(self) -> None:
        calls: list[Any] = []

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        def fake_send_request(request: ShellEscalateRequest) -> None:
            calls.append(("request", request))

        def fake_receive_response() -> ShellEscalateResponse:
            calls.append(("receive_response",))
            return ShellEscalateResponse(ShellEscalateAction.escalate())

        def fake_super_exec_send_with_fds(message: ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            calls.append(("super_exec_send", message, transferred_fds))

        def fake_super_exec_receive_result() -> ShellSuperExecResult:
            calls.append(("super_exec_receive",))
            return ShellSuperExecResult(55)

        def fake_dup(fd: int) -> int:
            return fd + 30

        self.assertEqual(
            shell_escalate_client_wrapper_run(
                "/bin/sh",
                ["/bin/sh"],
                server_socket_fd=17,
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                receive_response=fake_receive_response,
                workdir="/work",
                env={"CODEX_ESCALATE_SOCKET": "42"},
                destination_fds=(7, 8, 9),
                super_exec_send_with_fds=fake_super_exec_send_with_fds,
                super_exec_receive_result=fake_super_exec_receive_result,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            55,
        )
        self.assertEqual(
            calls,
            [
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("/bin/sh", ("/bin/sh",), Path("/work"), {})),
                ("receive_response",),
                ("super_exec_send", ShellSuperExecMessage((7, 8, 9)), (30, 31, 32)),
                ("super_exec_receive",),
            ],
        )

    def test_shell_escalate_client_wrapper_plan_run_sends_planned_handshake_before_request(self) -> None:
        calls: list[Any] = []
        client = object()
        plan = ShellEscalateClientWrapperPlan(
            ShellEscalateClientSocketPair(object(), client, 17, 18),
            ShellEscalateClientHandshakePlan(42, b"\x00", (17,)),
        )

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        self.assertIs(
            shell_escalate_client_wrapper_plan_send_handshake(plan, send_with_fds=fake_send_with_fds),
            client,
        )
        self.assertEqual(calls, [("handshake", 42, b"\x00", (17,))])
        calls.clear()
        with self.assertRaises(TypeError):
            shell_escalate_client_wrapper_plan_send_handshake(object(), send_with_fds=fake_send_with_fds)

        def fake_send_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            calls.append(("request", request))
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            calls.append(("execv", file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_wrapper_plan_run(
                plan,
                "bin/tool",
                ["tool"],
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                workdir="/work",
                env={"A": "B"},
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(
            calls,
            [
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {"A": "B"})),
                ("execv", "bin/tool", ("tool",)),
            ],
        )
        with self.assertRaises(TypeError):
            shell_escalate_client_wrapper_plan_run(
                object(),
                "bin/tool",
                ["tool"],
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
            )

        split_calls: list[Any] = []

        def fake_split_send_request(value_client: object, request: ShellEscalateRequest) -> None:
            split_calls.append(("request", value_client, request))

        def fake_split_receive_response(value_client: object) -> ShellEscalateResponse:
            split_calls.append(("receive", value_client))
            return ShellEscalateResponse(ShellEscalateAction.deny("blocked"))

        class FakeStderr:
            def __init__(self) -> None:
                self.text = ""

            def write(self, value: str) -> None:
                self.text += value

        stderr = FakeStderr()
        self.assertEqual(
            shell_escalate_client_wrapper_plan_run(
                plan,
                "bin/tool",
                ["tool"],
                send_with_fds=fake_send_with_fds,
                send_request=fake_split_send_request,
                receive_response=fake_split_receive_response,
                workdir="/work",
                env={},
                stderr=stderr,
            ),
            1,
        )
        self.assertEqual(
            split_calls,
            [
                ("request", client, ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {})),
                ("receive", client),
            ],
        )
        self.assertEqual(stderr.text, "Execution denied: blocked\n")

    def test_shell_escalate_client_wrapper_plan_run_supports_split_super_exec_exchange(self) -> None:
        calls: list[Any] = []
        client = object()
        plan = ShellEscalateClientWrapperPlan(
            ShellEscalateClientSocketPair(object(), client, 17, 18),
            ShellEscalateClientHandshakePlan(42, b"\x00", (17,)),
        )

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        def fake_send_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            calls.append(("request", request))
            return ShellEscalateResponse(ShellEscalateAction.escalate())

        def fake_super_exec_send_with_fds(
            value_client: object,
            value_payload: bytes,
            value_transferred_fds: tuple[int, ...],
        ) -> None:
            calls.append(("super_exec_send", value_client, value_payload, value_transferred_fds))

        def fake_super_exec_receive_result(value_client: object) -> bytes:
            calls.append(("super_exec_receive", value_client))
            message = json.dumps({"exit_code": 77}).encode("utf-8")
            return len(message).to_bytes(4, "little") + message

        def fake_dup(fd: int) -> int:
            return fd + 30

        expected_payload = json.dumps({"fds": [7, 8, 9]}).encode("utf-8")
        expected_framed = len(expected_payload).to_bytes(4, "little") + expected_payload

        self.assertEqual(
            shell_escalate_client_wrapper_plan_run(
                plan,
                "/bin/sh",
                ["/bin/sh"],
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                workdir="/work",
                destination_fds=(7, 8, 9),
                super_exec_send_with_fds=fake_super_exec_send_with_fds,
                super_exec_receive_result=fake_super_exec_receive_result,
                stdio=(0, 1, 2),
                dup=fake_dup,
            ),
            77,
        )
        self.assertEqual(
            calls,
            [
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("/bin/sh", ("/bin/sh",), Path("/work"), {})),
                ("super_exec_send", client, expected_framed, (30, 31, 32)),
                ("super_exec_receive", client),
            ],
        )

    def test_shell_escalate_client_wrapper_run_with_socket_pair_creates_pair_before_handshake(self) -> None:
        calls: list[Any] = []

        class FakeSocket:
            def __init__(self, name: str, fd: int) -> None:
                self.name = name
                self.fd = fd

            def fileno(self) -> int:
                calls.append(("fileno", self.name))
                return self.fd

        server = FakeSocket("server", 17)
        client = FakeSocket("client", 18)

        def fake_pair_factory() -> tuple[FakeSocket, FakeSocket]:
            calls.append(("pair",))
            return server, client

        def fake_send_with_fds(handshake_client_fd: int, message: bytes, fds: tuple[int, ...]) -> None:
            calls.append(("handshake", handshake_client_fd, message, fds))

        def fake_send_request(request: ShellEscalateRequest) -> ShellEscalateResponse:
            calls.append(("request", request))
            return ShellEscalateResponse(ShellEscalateAction.run())

        def fake_execv(file: str, argv: tuple[str, ...]) -> str:
            calls.append(("execv", file, argv))
            return "execv-called"

        self.assertEqual(
            shell_escalate_client_wrapper_run_with_socket_pair(
                "bin/tool",
                ["tool"],
                send_with_fds=fake_send_with_fds,
                send_request=fake_send_request,
                pair_factory=fake_pair_factory,
                workdir="/work",
                env={"CODEX_ESCALATE_SOCKET": "42"},
                execv=fake_execv,
            ),
            "execv-called",
        )
        self.assertEqual(
            calls,
            [
                ("pair",),
                ("fileno", "server"),
                ("fileno", "client"),
                ("handshake", 42, b"\x00", (17,)),
                ("request", ShellEscalateRequest("bin/tool", ("tool",), Path("/work"), {})),
                ("execv", "bin/tool", ("tool",)),
            ],
        )

    def test_shell_super_exec_message_and_result_match_rust_wire_shape(self) -> None:
        message = ShellSuperExecMessage((0, 1, 2))

        self.assertEqual(message.to_mapping(), {"fds": [0, 1, 2]})
        self.assertEqual(ShellSuperExecMessage.from_mapping(message.to_mapping()), message)
        self.assertEqual(ShellSuperExecMessage.from_mapping({"fds": []}), ShellSuperExecMessage())

        result = ShellSuperExecResult(7)
        self.assertEqual(result.to_mapping(), {"exit_code": 7})
        self.assertEqual(ShellSuperExecResult.from_mapping(result.to_mapping()), result)

        with self.assertRaises(TypeError):
            ShellSuperExecMessage.from_mapping({"fds": "not-fds"})
        with self.assertRaises(TypeError):
            ShellSuperExecMessage((True,))
        with self.assertRaises(TypeError):
            ShellSuperExecResult(True)

    def test_shell_super_exec_client_helpers_match_escalate_branch(self) -> None:
        self.assertEqual(SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS, (0, 1, 2))
        self.assertEqual(
            shell_super_exec_message_for_escalate_action(ShellEscalateAction.escalate()),
            ShellSuperExecMessage((0, 1, 2)),
        )
        self.assertEqual(
            shell_super_exec_message_for_escalate_action({"type": "escalate"}, destination_fds=(10, 11, 12)),
            ShellSuperExecMessage((10, 11, 12)),
        )
        self.assertIsNone(shell_super_exec_message_for_escalate_action(ShellEscalateAction.run()))
        self.assertIsNone(shell_super_exec_message_for_escalate_action(ShellEscalateAction.deny("blocked")))
        self.assertEqual(shell_super_exec_exit_code_from_result(ShellSuperExecResult(13)), 13)
        self.assertEqual(shell_super_exec_exit_code_from_result({"exit_code": 14}), 14)
        with self.assertRaisesRegex(TypeError, "shell escalate action must be a mapping"):
            shell_super_exec_message_for_escalate_action(object())

    def test_shell_super_exec_exit_code_from_result_rejects_missing_or_invalid_exit_code(self) -> None:
        with self.assertRaisesRegex(TypeError, "shell super exec result must be a mapping"):
            shell_super_exec_exit_code_from_result(None)

        with self.assertRaisesRegex(TypeError, "exit_code must be an integer"):
            shell_super_exec_exit_code_from_result({})

        with self.assertRaisesRegex(TypeError, "exit_code must be an integer"):
            shell_super_exec_exit_code_from_result({"exit_code": None})

    def test_shell_super_exec_exchange_exit_code_matches_send_receive_boundary(self) -> None:
        calls: list[tuple[ShellSuperExecMessage, tuple[int, ...]]] = []

        def fake_exchange(message: ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> dict[str, int]:
            calls.append((message, transferred_fds))
            return {"exit_code": 33}

        self.assertEqual(
            shell_super_exec_exchange_exit_code(
                {"fds": [0, 1, 2]},
                [10, 11, 12],
                exchange=fake_exchange,
            ),
            33,
        )
        self.assertEqual(calls, [(ShellSuperExecMessage((0, 1, 2)), (10, 11, 12))])

    def test_shell_super_exec_exchange_exit_code_rejects_invalid_result_type(self) -> None:
        def fake_exchange(_message: ShellSuperExecMessage, _transferred_fds: tuple[int, ...]) -> str:
            return "bad-result"

        with self.assertRaisesRegex(TypeError, "shell super exec result must be a mapping"):
            shell_super_exec_exchange_exit_code(
                {"fds": [0, 1, 2]},
                (),
                exchange=fake_exchange,
            )

    def test_shell_super_exec_exchange_exit_code_rejects_invalid_exit_code_shape(self) -> None:
        def fake_exchange(_message: ShellSuperExecMessage, _transferred_fds: tuple[int, ...]) -> dict[str, str]:
            return {"exit_code": "oops"}

        with self.assertRaisesRegex(TypeError, "exit_code must be an integer"):
            shell_super_exec_exchange_exit_code(
                ShellSuperExecMessage((0, 1, 2)),
                (3, 4),
                exchange=fake_exchange,
            )

    def test_shell_super_exec_exchange_exit_code_propagates_exchange_failure(self) -> None:
        def fake_exchange(_message: ShellSuperExecMessage, _transferred_fds: tuple[int, ...]) -> dict[str, int]:
            raise OSError("exchange failed")

        with self.assertRaisesRegex(OSError, "exchange failed"):
            shell_super_exec_exchange_exit_code(
                {"fds": [0, 1, 2]},
                (10,),
                exchange=fake_exchange,
            )

    def test_shell_escalate_client_plan_run_split_super_exec_with_client_forwards_client_and_payload(self) -> None:
        plan = ShellEscalateClientPlan(
            ShellEscalateClientAction.escalate(),
            super_exec=ShellSuperExecMessage((7, 8, 9)),
        )
        client = object()
        calls: list[tuple[str, object, bytes, tuple[int, ...]] | tuple[str, object]] = []
        payload = json.dumps({"fds": [7, 8, 9]}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload

        def fake_send_with_fds(
            value_client: object,
            message: bytes | ShellSuperExecMessage,
            transferred_fds: tuple[int, ...],
        ) -> None:
            calls.append(("send", value_client, bytes(message), transferred_fds))

        def fake_receive_result(value_client: object) -> dict[str, int]:
            calls.append(("receive", value_client))
            return {"exit_code": 77}

        self.assertEqual(
            shell_escalate_client_plan_run(
                plan,
                super_exec_send_with_fds=fake_send_with_fds,
                super_exec_receive_result=fake_receive_result,
                super_exec_client=client,
                stdio=(0, 1, 2),
                dup=lambda fd: fd,
            ),
            77,
        )
        self.assertEqual(calls, [("send", client, framed_payload, (0, 1, 2)), ("receive", client)])

    def test_shell_escalate_client_plan_run_escalate_exchange_propagates_invalid_result(self) -> None:
        plan = ShellEscalateClientPlan(
            ShellEscalateClientAction.escalate(),
            super_exec=ShellSuperExecMessage((7, 8, 9)),
        )

        with self.assertRaisesRegex(TypeError, "shell super exec result must be a mapping"):
            shell_escalate_client_plan_run(
                plan,
                super_exec=lambda _message, _fds: "bad-result",
            )

    def test_shell_super_exec_send_receive_exit_code_matches_split_socket_boundary(self) -> None:
        payload = json.dumps({"fds": [0, 1, 2]}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload
        calls: list[tuple[ShellSuperExecMessage | bytes, tuple[int, ...]] | tuple[str]] = []

        def fake_send_with_fds(message: bytes | ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            calls.append((bytes(message), transferred_fds))

        def fake_receive_result() -> dict[str, int]:
            calls.append(("receive",))
            return {"exit_code": 44}

        self.assertEqual(
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                [10, 11, 12],
                send_with_fds=fake_send_with_fds,
                receive_result=fake_receive_result,
            ),
            44,
        )
        self.assertEqual(
            calls,
            [
                (framed_payload, (10, 11, 12)),
                ("receive",),
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "failed to send SuperExecMessage"):
            shell_super_exec_send_receive_exit_code(
                ShellSuperExecMessage((0,)),
                (10,),
                send_with_fds=lambda _message, _fds: (_ for _ in ()).throw(OSError("send failed")),
                receive_result=fake_receive_result,
            )

        client = object()
        client_calls: list[Any] = []

        def fake_client_send_with_fds(
            value_client: object,
            message: bytes | ShellSuperExecMessage,
            transferred_fds: tuple[int, ...],
        ) -> None:
            client_calls.append(("send", value_client, bytes(message), transferred_fds))

        def fake_client_receive_result(value_client: object) -> ShellSuperExecResult:
            client_calls.append(("receive", value_client))
            return ShellSuperExecResult(45)

        self.assertEqual(
            shell_super_exec_send_receive_exit_code(
                ShellSuperExecMessage((0,)),
                (10,),
                send_with_fds=fake_client_send_with_fds,
                receive_result=fake_client_receive_result,
                client=client,
            ),
            45,
        )
        self.assertEqual(
            client_calls,
            [
                (
                    "send",
                    client,
                    ShellSuperExecMessage((0,)).to_framed_payload(),
                    (10,),
                ),
                ("receive", client),
            ],
        )

    def test_shell_super_exec_send_receive_exit_code_parses_socket_result_payload(self) -> None:
        client = object()
        calls: list[tuple[str, object] | tuple[str, object, bytes, tuple[int, ...]] | tuple[str, object]] = []
        result_payload = json.dumps({"exit_code": 77}).encode("utf-8")
        payload = json.dumps({"fds": [0, 1, 2]}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload

        def send_with_fds(value_client: object, payload: bytes, transferred_fds: tuple[int, ...]) -> None:
            if not isinstance(payload, (bytes, bytearray, memoryview)):
                raise TypeError("data must be bytes")
            calls.append(("send", value_client, bytes(payload), transferred_fds))
            data = json.loads(shell_socket_extract_length_prefixed_payload(bytes(payload)).decode("utf-8"))
            self.assertEqual(data, {"fds": [0, 1, 2]})

        def receive_result(value_client: object) -> tuple[bytes, tuple[int, ...]]:
            calls.append(("receive", value_client))
            return result_payload, (123,)

        self.assertEqual(
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (10, 11, 12),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
                client=client,
            ),
            77,
        )
        self.assertEqual(
            calls,
            [
                (
                    "send",
                    client,
                    ShellSuperExecMessage((0, 1, 2)).to_framed_payload(),
                    (10, 11, 12),
                ),
                ("receive", client),
            ],
        )

    def test_shell_super_exec_send_receive_exit_code_parses_length_prefixed_socket_payload(self) -> None:
        client = object()
        calls: list[tuple[str, object] | tuple[str, object, bytes, tuple[int, ...]] | tuple[str, object]] = []
        payload = json.dumps({"exit_code": 79}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload

        def send_with_fds(value_client: object, message: bytes, transferred_fds: tuple[int, ...]) -> None:
            calls.append(("send", value_client, bytes(message), transferred_fds))
            data = json.loads(shell_socket_extract_length_prefixed_payload(bytes(message)).decode("utf-8"))
            self.assertEqual(data, {"fds": [0, 1, 2]})

        def receive_result(value_client: object) -> tuple[bytes, tuple[int, ...]]:
            calls.append(("receive", value_client))
            return framed_payload, (123,)

        self.assertEqual(
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (10, 11, 12),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
                client=client,
            ),
            79,
        )
        self.assertEqual(
            calls,
            [
                (
                    "send",
                    client,
                    ShellSuperExecMessage((0, 1, 2)).to_framed_payload(),
                    (10, 11, 12),
                ),
                ("receive", client),
            ],
        )

    def test_shell_super_exec_send_receive_exit_code_falls_back_on_type_signature_mismatch(self) -> None:
        client = object()
        calls: list[tuple[str, object] | tuple[str, object, bytes, tuple[int, ...]] | tuple[str, object]] = []
        payload = json.dumps({"fds": [0, 1, 2]}).encode("utf-8")
        framed_payload = len(payload).to_bytes(4, "little") + payload

        def send_with_fds(
            value_client: object,
            payload: object,
            transferred_fds: tuple[int, ...],
        ) -> None:
            if isinstance(payload, (bytes, bytearray, memoryview)):
                calls.append(("send-reject", value_client, bytes(payload), transferred_fds))
                raise TypeError("custom arg type mismatch")
            calls.append(("send-ok", value_client, payload, transferred_fds))

        def receive_result(value_client: object) -> dict[str, int]:
            calls.append(("receive", value_client))
            return {"exit_code": 78}

        self.assertEqual(
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (10, 11, 12),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
                client=client,
            ),
            78,
        )
        self.assertEqual(
            calls,
            [
                (
                    "send-reject",
                    client,
                    json.dumps({"fds": [0, 1, 2]}).encode("utf-8"),
                    (10, 11, 12),
                ),
                (
                    "send-reject",
                    client,
                    framed_payload,
                    (10, 11, 12),
                ),
                (
                    "send-ok",
                    client,
                    ShellSuperExecMessage((0, 1, 2)),
                    (10, 11, 12),
                ),
                ("receive", client),
            ],
        )

    def test_shell_super_exec_send_receive_exit_code_rejects_invalid_json_result_payload(self) -> None:
        calls: list[str] = []

        def send_with_fds(message: bytes | ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            calls.append("send")

        def receive_result() -> bytes:
            return b"not-json"

        with self.assertRaises(ValueError):
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
            )
        self.assertEqual(calls, ["send"])

    def test_shell_super_exec_send_receive_exit_code_rejects_tuple_with_invalid_json_length_prefixed_payload(
        self,
    ) -> None:
        payload = json.dumps({"fds": [0, 1, 2]}).encode("utf-8")

        def send_with_fds(message: bytes | ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            return None

        def receive_result() -> tuple[bytes, tuple[int, ...]]:
            return payload, (7,)

        with self.assertRaisesRegex(TypeError, "exit_code must be an integer"):
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
            )

    def test_shell_super_exec_send_receive_exit_code_rejects_non_mapping_result(self) -> None:
        def send_with_fds(message: bytes | ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            return None

        def receive_result() -> tuple[str, tuple[int, ...]]:
            return "exit", ()

        with self.assertRaisesRegex(
            TypeError, "shell super exec result must be a mapping"
        ):
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
            )

    def test_shell_super_exec_send_receive_exit_code_propagates_receive_result_failure(self) -> None:
        def send_with_fds(message: bytes | ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            return None

        def receive_result() -> dict[str, int]:
            raise OSError("receive failed")

        with self.assertRaisesRegex(OSError, "receive failed"):
            shell_super_exec_send_receive_exit_code(
                {"fds": [0, 1, 2]},
                (),
                send_with_fds=send_with_fds,
                receive_result=receive_result,
            )

    def test_shell_super_exec_duplicate_fd_for_transfer_matches_client_boundary(self) -> None:
        seen: list[int] = []

        class FakeFile:
            def fileno(self) -> int:
                return 8

        def fake_dup(fd: int) -> int:
            seen.append(fd)
            return 88

        self.assertEqual(
            shell_super_exec_duplicate_fd_for_transfer(FakeFile(), "stdin", dup=fake_dup),
            88,
        )
        self.assertEqual(seen, [8])
        with self.assertRaisesRegex(OSError, "failed to duplicate stdout for escalation transfer"):
            shell_super_exec_duplicate_fd_for_transfer(
                1,
                "stdout",
                dup=lambda _fd: (_ for _ in ()).throw(OSError("dup failed")),
            )
        with self.assertRaises(TypeError):
            shell_super_exec_duplicate_fd_for_transfer(True, "stderr", dup=fake_dup)

    def test_shell_super_exec_stdio_transfer_fds_matches_client_send_shape(self) -> None:
        seen: list[int] = []

        class FakeFile:
            def __init__(self, fd: int) -> None:
                self.fd = fd

            def fileno(self) -> int:
                return self.fd

        def fake_dup(fd: int) -> int:
            seen.append(fd)
            return fd + 100

        self.assertEqual(
            shell_super_exec_stdio_transfer_fds(
                (FakeFile(0), FakeFile(1), FakeFile(2)),
                dup=fake_dup,
            ),
            (100, 101, 102),
        )
        self.assertEqual(seen, [0, 1, 2])
        with self.assertRaisesRegex(ValueError, "stdio and names must contain the same number of entries"):
            shell_super_exec_stdio_transfer_fds((FakeFile(0),), names=("stdin", "stdout"), dup=fake_dup)

    def test_shell_super_exec_server_helpers_match_fd_and_status_boundaries(self) -> None:
        message = ShellSuperExecMessage((0, 1, 2))

        self.assertEqual(shell_super_exec_fd_pairs(message, (10, 11, 12)), ((0, 10), (1, 11), (2, 12)))
        self.assertEqual(shell_super_exec_fd_pairs({"fds": [3]}, [99]), ((3, 99),))
        with self.assertRaisesRegex(
            ValueError,
            "mismatched number of fds in SuperExecMessage: 2 in the message, 1 from the control message",
        ):
            shell_super_exec_fd_pairs(ShellSuperExecMessage((0, 1)), (10,))

        self.assertEqual(shell_super_exec_result_from_exit_status(23), ShellSuperExecResult(23))
        self.assertEqual(shell_super_exec_result_from_exit_status(None), ShellSuperExecResult(127))
        with self.assertRaises(TypeError):
            shell_super_exec_result_from_exit_status(True)

    def test_shell_prepared_exec_helpers_match_server_command_boundaries(self) -> None:
        prepared = ShellPreparedExec(["/bin/sh", "-lc", "echo ok"], "/tmp", {"A": "B"})

        self.assertEqual(prepared.command, ("/bin/sh", "-lc", "echo ok"))
        self.assertEqual(prepared.cwd, Path("/tmp"))
        self.assertEqual(prepared.env, {"A": "B"})
        self.assertEqual(shell_prepared_exec_program_and_args(prepared), ("/bin/sh", ("-lc", "echo ok")))
        self.assertEqual(shell_prepared_exec_effective_arg0("/bin/sh", None), "/bin/sh")
        self.assertEqual(shell_prepared_exec_effective_arg0("/bin/sh", "custom-sh"), "custom-sh")

        with self.assertRaisesRegex(ValueError, "prepared escalated command must not be empty"):
            shell_prepared_exec_program_and_args(ShellPreparedExec((), Path("/tmp"), {}))
        with self.assertRaises(TypeError):
            ShellPreparedExec(["/bin/sh"], Path("/tmp"), {"A": 1})
        with self.assertRaises(TypeError):
            shell_prepared_exec_effective_arg0("/bin/sh", 123)

    def test_shell_super_exec_spawn_plan_matches_server_command_configuration(self) -> None:
        prepared = ShellPreparedExec(["/bin/sh", "-lc", "echo ok"], "/work", {"A": "B"}, arg0="custom-sh")

        plan = shell_super_exec_spawn_plan(prepared, ShellSuperExecMessage((0, 1, 2)), (10, 11, 12))

        self.assertEqual(
            plan,
            ShellSuperExecSpawnPlan(
                program="/bin/sh",
                args=("-lc", "echo ok"),
                arg0="custom-sh",
                cwd=Path("/work"),
                env={"A": "B"},
                fd_pairs=((0, 10), (1, 11), (2, 12)),
            ),
        )
        self.assertTrue(plan.stdio_null)
        self.assertTrue(plan.kill_on_drop)
        self.assertEqual(
            shell_super_exec_spawn_plan(
                ShellPreparedExec(["/bin/sh"], Path("/work"), {}),
                {"fds": [0]},
                [10],
            ).arg0,
            "/bin/sh",
        )
        with self.assertRaisesRegex(ValueError, "prepared escalated command must not be empty"):
            shell_super_exec_spawn_plan(ShellPreparedExec((), Path("/work"), {}), ShellSuperExecMessage(), ())
        with self.assertRaisesRegex(ValueError, "mismatched number of fds in SuperExecMessage"):
            shell_super_exec_spawn_plan(prepared, ShellSuperExecMessage((0, 1)), (10,))

    def test_shell_super_exec_subprocess_spec_preserves_executable_and_arg0_split(self) -> None:
        plan = ShellSuperExecSpawnPlan(
            program="/bin/sh",
            args=("-lc", "echo ok"),
            arg0="custom-sh",
            cwd="/work",
            env={"A": "B"},
            fd_pairs=((0, 10),),
        )

        spec = shell_super_exec_subprocess_spec(plan)

        self.assertEqual(
            spec,
            ShellSuperExecSubprocessSpec(
                executable="/bin/sh",
                argv=("custom-sh", "-lc", "echo ok"),
                cwd=Path("/work"),
                env={"A": "B"},
                fd_pairs=((0, 10),),
            ),
        )
        self.assertTrue(spec.stdio_null)
        self.assertTrue(spec.kill_on_cancel)

        with self.assertRaises(TypeError):
            shell_super_exec_subprocess_spec(object())
        with self.assertRaises(ValueError):
            ShellSuperExecSubprocessSpec("/bin/sh", (), Path("/work"), {}, ())
        with self.assertRaises(TypeError):
            ShellSuperExecSubprocessSpec("/bin/sh", ("sh",), Path("/work"), {}, ((0, True),))

    def test_shell_super_exec_popen_kwargs_match_null_stdio_and_dup2_preexec(self) -> None:
        spec = ShellSuperExecSubprocessSpec(
            executable="/bin/sh",
            argv=("custom-sh", "-lc", "echo ok"),
            cwd="/work",
            env={"A": "B"},
            fd_pairs=((0, 10), (1, 11), (2, 12)),
        )

        kwargs = shell_super_exec_popen_kwargs(spec)

        self.assertEqual(kwargs["args"], ("custom-sh", "-lc", "echo ok"))
        self.assertEqual(kwargs["executable"], "/bin/sh")
        self.assertEqual(kwargs["cwd"], Path("/work"))
        self.assertEqual(kwargs["env"], {"A": "B"})
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        with patch("pycodex.core.tools.runtimes.os.dup2") as dup2:
            kwargs["preexec_fn"]()
        self.assertEqual(
            [call.args for call in dup2.call_args_list],
            [(10, 0), (11, 1), (12, 2)],
        )

        no_null = shell_super_exec_popen_kwargs(
            ShellSuperExecSubprocessSpec("/bin/sh", ("sh",), Path("/work"), {}, (), stdio_null=False)
        )
        self.assertNotIn("stdin", no_null)
        self.assertNotIn("stdout", no_null)
        self.assertNotIn("stderr", no_null)
        with self.assertRaises(TypeError):
            shell_super_exec_popen_kwargs(object())
        with self.assertRaises(TypeError):
            shell_super_exec_dup2_preexec_fn(((0, True),))

    def test_shell_super_exec_run_subprocess_waits_or_kills_on_cancellation(self) -> None:
        class FakeChild:
            def __init__(self, poll_result: int | None, wait_result: int) -> None:
                self.poll_result = poll_result
                self.wait_result = wait_result
                self.killed = False

            def poll(self) -> int | None:
                return self.poll_result

            def wait(self) -> int:
                return self.wait_result

            def kill(self) -> None:
                self.killed = True

        launched: list[dict[str, object]] = []
        completed_child = FakeChild(7, 7)

        def completed_factory(**kwargs: object) -> FakeChild:
            launched.append(kwargs)
            return completed_child

        spec = ShellSuperExecSubprocessSpec("/bin/sh", ("sh",), Path("/work"), {}, ())
        self.assertEqual(
            shell_super_exec_run_subprocess(spec, popen_factory=completed_factory, poll_interval=0),
            ShellSuperExecResult(7),
        )
        self.assertFalse(completed_child.killed)
        self.assertEqual(launched[0]["args"], ("sh",))
        self.assertEqual(launched[0]["executable"], "/bin/sh")

        token = CancellationToken()
        token.cancel()
        cancelled_child = FakeChild(None, 143)

        def cancelled_factory(**kwargs: object) -> FakeChild:
            return cancelled_child

        self.assertEqual(
            shell_super_exec_run_subprocess(
                spec,
                cancellation_tokens=(token,),
                popen_factory=cancelled_factory,
                poll_interval=0,
            ),
            ShellSuperExecResult(143),
        )
        self.assertTrue(cancelled_child.killed)
        with self.assertRaises(TypeError):
            shell_super_exec_run_subprocess(object())
        with self.assertRaises(TypeError):
            shell_super_exec_run_subprocess(spec, cancellation_tokens=(object(),))

    def test_shell_super_exec_run_prepared_composes_server_escalate_branch(self) -> None:
        class FakeChild:
            def poll(self) -> int:
                return 0

            def wait(self) -> int:
                return 0

            def kill(self) -> None:
                raise AssertionError("completed child should not be killed")

        launched: list[dict[str, object]] = []

        def factory(**kwargs: object) -> FakeChild:
            launched.append(kwargs)
            return FakeChild()

        result = shell_super_exec_run_prepared(
            ShellPreparedExec(["/bin/sh", "-lc", "echo ok"], "/work", {"A": "B"}, arg0="custom-sh"),
            ShellSuperExecMessage((0, 1)),
            (10, 11),
            popen_factory=factory,
            poll_interval=0,
        )

        self.assertEqual(result, ShellSuperExecResult(0))
        self.assertEqual(launched[0]["args"], ("custom-sh", "-lc", "echo ok"))
        self.assertEqual(launched[0]["executable"], "/bin/sh")
        self.assertEqual(launched[0]["cwd"], Path("/work"))
        self.assertEqual(launched[0]["env"], {"A": "B"})
        with patch("pycodex.core.tools.runtimes.os.dup2") as dup2:
            launched[0]["preexec_fn"]()
        self.assertEqual([call.args for call in dup2.call_args_list], [(10, 0), (11, 1)])

        with self.assertRaisesRegex(ValueError, "prepared escalated command must not be empty"):
            shell_super_exec_run_prepared(ShellPreparedExec((), Path("/work"), {}), ShellSuperExecMessage(), ())
        with self.assertRaisesRegex(ValueError, "mismatched number of fds in SuperExecMessage"):
            shell_super_exec_run_prepared(
                ShellPreparedExec(["/bin/sh"], Path("/work"), {}),
                ShellSuperExecMessage((0, 1)),
                (10,),
            )

    def test_execve_prompt_policy_rejection_reasons_match_rust(self) -> None:
        self.assertEqual(
            execve_prompt_is_rejected_by_policy(AskForApproval.NEVER, DecisionSource.PREFIX_RULE),
            PROMPT_CONFLICT_REASON,
        )
        self.assertEqual(
            execve_prompt_is_rejected_by_policy(
                GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=False,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                ),
                DecisionSource.PREFIX_RULE,
            ),
            REJECT_RULES_APPROVAL_REASON,
        )
        self.assertEqual(
            execve_prompt_is_rejected_by_policy(
                GranularApprovalConfig(
                    sandbox_approval=False,
                    rules=True,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                ),
                DecisionSource.UNMATCHED_COMMAND_FALLBACK,
            ),
            REJECT_SANDBOX_APPROVAL_REASON,
        )

    def test_extract_shell_script_accepts_wrapped_commands_and_preserves_login(self) -> None:
        self.assertEqual(
            extract_shell_script(("/bin/zsh", "-lc", "echo hi")),
            ParsedShellCommand("/bin/zsh", "echo hi", True),
        )
        self.assertEqual(
            extract_shell_script(("/usr/bin/env", "A=1", "/bin/zsh", "-c", "pwd")),
            ParsedShellCommand("/bin/zsh", "pwd", False),
        )
        with self.assertRaises(ToolRuntimeError):
            extract_shell_script(("sandbox-exec", "-fc", "echo no"))

    def test_join_program_and_map_exec_result_match_rust_output_mapping(self) -> None:
        self.assertEqual(join_program_and_argv("/tmp/tool", ("./tool", "--flag")), ("/tmp/tool", "--flag"))
        output = map_exec_result(
            SandboxType.NONE,
            ExecResult(exit_code=0, stdout="out", stderr="err", output="outerr"),
        )

        self.assertEqual(output.stdout.text, "out")
        self.assertEqual(output.stderr.text, "err")
        self.assertEqual(output.aggregated_output.text, "outerr")

    def test_commands_for_intercepted_exec_policy_parses_plain_shell_wrappers(self) -> None:
        candidate = commands_for_intercepted_exec_policy(
            "/bin/bash",
            ("not-bash", "-lc", "git status && pwd"),
        )

        self.assertEqual(candidate.commands, (("git", "status"), ("pwd",)))
        self.assertFalse(candidate.used_complex_parsing)

    def test_commands_for_intercepted_exec_policy_falls_back_to_outer_command(self) -> None:
        candidate = commands_for_intercepted_exec_policy(
            "/tmp/tool",
            ("./tool", "--flag", "value"),
        )

        self.assertEqual(candidate.commands, (("/tmp/tool", "--flag", "value"),))
        self.assertFalse(candidate.used_complex_parsing)

    def test_evaluate_intercepted_exec_policy_uses_wrapper_command_when_parsing_disabled(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Rust test: evaluate_intercepted_exec_policy_uses_wrapper_command_when_shell_wrapper_parsing_disabled.
        evaluation = evaluate_intercepted_exec_policy(
            (ExecPolicyPrefixRule.new(("npm", "publish"), "prompt"),),
            "/bin/zsh",
            ("zsh", "-lc", "npm publish"),
            _intercepted_exec_context(enable_shell_wrapper_parsing=False),
        )

        self.assertIs(evaluation.decision, Decision.ALLOW)
        self.assertEqual(
            evaluation.matched_rules,
            (
                {
                    "heuristicsRuleMatch": {
                        "command": ["/bin/zsh", "-lc", "npm publish"],
                        "decision": "allow",
                    }
                },
            ),
        )
        self.assertFalse(decision_driven_by_policy(evaluation.matched_rules, evaluation.decision))

    def test_evaluate_intercepted_exec_policy_matches_inner_commands_when_enabled(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Rust test: evaluate_intercepted_exec_policy_matches_inner_shell_commands_when_enabled.
        evaluation = evaluate_intercepted_exec_policy(
            (ExecPolicyPrefixRule.new(("npm", "publish"), "prompt"),),
            "/bin/bash",
            ("bash", "-lc", "npm publish"),
            _intercepted_exec_context(enable_shell_wrapper_parsing=True),
        )

        self.assertIs(evaluation.decision, Decision.PROMPT)
        self.assertEqual(
            evaluation.matched_rules,
            (
                {
                    "prefixRuleMatch": {
                        "matchedPrefix": ["npm", "publish"],
                        "decision": "prompt",
                    }
                },
            ),
        )
        self.assertTrue(decision_driven_by_policy(evaluation.matched_rules, evaluation.decision))

    def test_evaluate_intercepted_exec_policy_uses_host_executable_mappings(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Rust tests: intercepted_exec_policy_uses_host_executable_mappings and
        # intercepted_exec_policy_rejects_disallowed_host_executable_mapping.
        policy = {
            "rules": (ExecPolicyPrefixRule.new(("git", "status"), "prompt"),),
            "host_executables": {"git": ("/usr/bin/git",)},
        }

        matched = evaluate_intercepted_exec_policy(
            policy,
            "/usr/bin/git",
            ("git", "status"),
            _intercepted_exec_context(enable_shell_wrapper_parsing=False),
        )
        self.assertIs(matched.decision, Decision.PROMPT)
        self.assertEqual(matched.matched_rules[0]["prefixRuleMatch"]["resolvedProgram"], "/usr/bin/git")
        self.assertTrue(decision_driven_by_policy(matched.matched_rules, matched.decision))

        disallowed = evaluate_intercepted_exec_policy(
            policy,
            "/opt/homebrew/bin/git",
            ("git", "status"),
            _intercepted_exec_context(enable_shell_wrapper_parsing=False),
        )
        self.assertIs(disallowed.decision, Decision.ALLOW)
        self.assertEqual(disallowed.matched_rules[0]["heuristicsRuleMatch"]["command"][0], "/opt/homebrew/bin/git")
        self.assertFalse(decision_driven_by_policy(disallowed.matched_rules, disallowed.decision))

    def test_evaluate_intercepted_exec_policy_treats_preapproved_additional_permissions_as_default(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Rust test: intercepted_exec_policy_treats_preapproved_additional_permissions_as_default.
        preapproved = evaluate_intercepted_exec_policy(
            (),
            "/usr/bin/printf",
            ("printf", "hello"),
            _intercepted_exec_context(
                permission_profile=PermissionProfile.workspace_write(),
                sandbox_permissions=approval_sandbox_permissions(
                    SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                    True,
                ),
            ),
        )
        fresh_request = evaluate_intercepted_exec_policy(
            (),
            "/usr/bin/printf",
            ("printf", "hello"),
            _intercepted_exec_context(
                permission_profile=PermissionProfile.workspace_write(),
                sandbox_permissions=SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            ),
        )

        self.assertIs(preapproved.decision, Decision.ALLOW)
        self.assertIs(fresh_request.decision, Decision.PROMPT)

    def test_shell_escalation_policy_plan_matches_rust_determine_action_branching(self) -> None:
        # Rust source: codex-rs/core/src/tools/runtimes/shell/unix_escalation.rs
        # Behavior anchor: CoreShellActionProvider::determine_action selects
        # needs_escalation, DecisionSource, and EscalationExecution before
        # delegating to process_decision.
        profile = PermissionProfile.workspace_write()
        prefix_rule_evaluation = InterceptedExecPolicyEvaluation(
            Decision.ALLOW,
            (
                {
                    "prefixRuleMatch": {
                        "matchedPrefix": ["npm", "publish"],
                        "decision": "allow",
                    }
                },
            ),
        )

        prefix_plan = shell_escalation_policy_plan(
            prefix_rule_evaluation,
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            permission_profile=profile,
        )

        self.assertEqual(
            prefix_plan,
            ShellEscalationPolicyPlan(
                decision=Decision.ALLOW,
                decision_source=DecisionSource.PREFIX_RULE,
                needs_escalation=True,
                escalation_execution=ShellEscalationExecution.unsandboxed(),
            ),
        )

        heuristic_evaluation = InterceptedExecPolicyEvaluation(
            Decision.ALLOW,
            ({"heuristicsRuleMatch": {"command": ["touch", "file"], "decision": "allow"}},),
        )
        require_escalated = shell_escalation_policy_plan(
            heuristic_evaluation,
            sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
            permission_profile=profile,
        )
        self.assertEqual(require_escalated.decision_source, DecisionSource.UNMATCHED_COMMAND_FALLBACK)
        self.assertTrue(require_escalated.needs_escalation)
        self.assertEqual(require_escalated.escalation_execution, ShellEscalationExecution.unsandboxed())

        additional = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(write_roots=("/tmp/out",))
        )
        with_additional = shell_escalation_policy_plan(
            heuristic_evaluation,
            sandbox_permissions=SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            permission_profile=profile,
            prompt_permissions=additional,
        )
        self.assertFalse(with_additional.needs_escalation)
        self.assertEqual(with_additional.decision_source, DecisionSource.UNMATCHED_COMMAND_FALLBACK)
        self.assertEqual(with_additional.escalation_execution, ShellEscalationExecution.permissions(profile))
        self.assertEqual(with_additional.prompt_permissions, additional)

    def test_map_exec_result_preserves_output_on_sandbox_denied(self) -> None:
        with self.assertRaises(ToolRuntimeError) as ctx:
            map_exec_result(
                SandboxType.LINUX_SECCOMP,
                ExecResult(
                    exit_code=1,
                    stdout="stdout detail",
                    stderr="permission denied",
                    output="aggregate detail",
                ),
            )

        error = ctx.exception.error
        self.assertEqual(error.type, "codex")
        self.assertEqual(error.error["sandbox"], "denied")
        self.assertIsNone(error.error["network_policy_decision"])
        output = error.error["output"]
        self.assertEqual(output.exit_code, 1)
        self.assertEqual(output.stdout.text, "stdout detail")
        self.assertEqual(output.stderr.text, "permission denied")
        self.assertEqual(output.aggregated_output.text, "aggregate detail")

    def test_map_exec_result_preserves_output_on_timeout(self) -> None:
        with self.assertRaises(ToolRuntimeError) as ctx:
            map_exec_result(
                SandboxType.LINUX_SECCOMP,
                ExecResult(
                    exit_code=124,
                    stdout="partial stdout",
                    stderr="partial stderr",
                    output="partial aggregate",
                    timed_out=True,
                ),
            )

        error = ctx.exception.error
        self.assertEqual(error.type, "codex")
        self.assertEqual(error.error["sandbox"], "timeout")
        output = error.error["output"]
        self.assertTrue(output.timed_out)
        self.assertEqual(output.stdout.text, "partial stdout")
        self.assertEqual(output.stderr.text, "partial stderr")
        self.assertEqual(output.aggregated_output.text, "partial aggregate")

    def test_build_sandbox_command_splits_program_and_args(self) -> None:
        command = build_sandbox_command(["/bin/echo", "ok"], "/repo", {"A": "B"})

        self.assertEqual(command, SandboxCommand("/bin/echo", ("ok",), Path("/repo"), {"A": "B"}))

    def test_build_sandbox_command_rejects_empty_args(self) -> None:
        with self.assertRaises(ToolRuntimeError) as ctx:
            build_sandbox_command([], "/repo", {})

        self.assertIn("command args are empty", str(ctx.exception))
        self.assertEqual(ctx.exception.error.message, "command args are empty")

    def test_exec_env_for_escalated_permissions_removes_codex_proxy_only_when_active(self) -> None:
        env = {
            "CUSTOM": "kept",
            PROXY_ACTIVE_ENV_KEY: "1",
            "HTTP_PROXY": "http://codex.proxy",
            "GIT_SSH_COMMAND": "codex-proxy-git-ssh --proxy",
        }

        cleaned = exec_env_for_sandbox_permissions(env, SandboxPermissions.REQUIRE_ESCALATED, target_os="darwin")

        self.assertEqual(cleaned, {"CUSTOM": "kept"})
        self.assertEqual(env["HTTP_PROXY"], "http://codex.proxy")
        self.assertEqual(env["GIT_SSH_COMMAND"], "codex-proxy-git-ssh --proxy")

    def test_exec_env_for_escalated_permissions_keeps_codex_git_ssh_proxy_on_non_macos(self) -> None:
        env = {
            "CUSTOM": "kept",
            PROXY_ACTIVE_ENV_KEY: "1",
            "HTTP_PROXY": "http://codex.proxy",
            "GIT_SSH_COMMAND": "codex-proxy-git-ssh --proxy",
        }

        cleaned = exec_env_for_sandbox_permissions(env, SandboxPermissions.REQUIRE_ESCALATED, target_os="linux")

        self.assertEqual(
            cleaned,
            {"CUSTOM": "kept", "GIT_SSH_COMMAND": "codex-proxy-git-ssh --proxy"},
        )

    def test_exec_env_for_escalated_permissions_keeps_user_proxy_without_active_marker(self) -> None:
        env = {
            "CUSTOM": "kept",
            "HTTP_PROXY": "http://user.proxy",
            "GIT_SSH_COMMAND": "ssh -i key",
        }

        cleaned = exec_env_for_sandbox_permissions(env, SandboxPermissions.REQUIRE_ESCALATED)

        self.assertEqual(cleaned["HTTP_PROXY"], "http://user.proxy")
        self.assertEqual(cleaned["GIT_SSH_COMMAND"], "ssh -i key")
        self.assertEqual(cleaned["CUSTOM"], "kept")

    def test_exec_env_for_default_permissions_keeps_proxy_env(self) -> None:
        env = {key: "value" for key in PROXY_ENV_KEYS}

        self.assertEqual(exec_env_for_sandbox_permissions(env, SandboxPermissions.USE_DEFAULT), env)

    def test_powershell_no_profile_injected_for_elevated_windows_sandbox(self) -> None:
        rewritten = disable_powershell_profile_for_elevated_windows_sandbox(
            ("powershell.exe", "-Command", "Write-Output ok"),
            ShellType.POWERSHELL,
            SandboxType.WINDOWS_RESTRICTED_TOKEN,
            WindowsSandboxLevel.ELEVATED,
        )

        self.assertEqual(rewritten, ("powershell.exe", "-NoProfile", "-Command", "Write-Output ok"))

    def test_powershell_no_profile_preserves_existing_flag_and_non_matching_cases(self) -> None:
        existing = ("pwsh.exe", "-NoProfile", "-Command", "Write-Output ok")
        self.assertEqual(
            disable_powershell_profile_for_elevated_windows_sandbox(
                existing,
                ShellType.POWERSHELL,
                SandboxType.WINDOWS_RESTRICTED_TOKEN,
                WindowsSandboxLevel.ELEVATED,
            ),
            existing,
        )
        bash = ("/bin/bash", "-lc", "echo ok")
        self.assertEqual(
            disable_powershell_profile_for_elevated_windows_sandbox(
                bash,
                ShellType.BASH,
                SandboxType.WINDOWS_RESTRICTED_TOKEN,
                WindowsSandboxLevel.ELEVATED,
            ),
            bash,
        )

    def test_shell_snapshot_wraps_shell_lc_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path = root / "snapshot.sh"
            snapshot_path.write_text("# Snapshot file\n")
            shell = Shell(ShellType.ZSH, Path("/bin/zsh"), ShellSnapshot(snapshot_path, root))

            rewritten = maybe_wrap_shell_lc_with_snapshot(
                ("/bin/bash", "-lc", "echo hello"),
                shell,
                root,
                {},
                {},
            )

        self.assertEqual(rewritten[0], str(Path("/bin/zsh")))
        self.assertEqual(rewritten[1], "-c")
        self.assertIn("if . '", rewritten[2])
        self.assertIn("exec '/bin/bash' -c 'echo hello'", rewritten[2])

    def test_shell_snapshot_wrap_preserves_trailing_args_and_thread_id_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot_path = root / "snapshot.sh"
            snapshot_path.write_text("# Snapshot file\n")
            shell = Shell(ShellType.BASH, Path("/bin/bash"), ShellSnapshot(snapshot_path, root))

            rewritten = maybe_wrap_shell_lc_with_snapshot(
                ("/bin/zsh", "-lc", "printf '%s' \"$0\"", "arg0"),
                shell,
                root,
                {"BAD-NAME": "ignored"},
                {CODEX_THREAD_ID_ENV_VAR: "thread-1"},
            )

        self.assertIn("__CODEX_SNAPSHOT_OVERRIDE_SET_0", rewritten[2])
        self.assertIn(CODEX_THREAD_ID_ENV_VAR, rewritten[2])
        self.assertIn("exec '/bin/zsh' -c 'printf '\"'\"'%s'\"'\"' \"$0\"' 'arg0'", rewritten[2])

    def test_shell_snapshot_wrap_skips_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "other"
            other.mkdir()
            snapshot_path = root / "snapshot.sh"
            snapshot_path.write_text("# Snapshot file\n")
            shell = Shell(ShellType.SH, Path("/bin/sh"), ShellSnapshot(snapshot_path, root))
            command = ("/bin/bash", "-lc", "echo hello")

            self.assertEqual(maybe_wrap_shell_lc_with_snapshot(command, shell, other, {}, {}), command)
            self.assertEqual(maybe_wrap_shell_lc_with_snapshot(command, shell, root, {}, {}, is_windows=True), command)

    def test_override_exports_and_shell_quoting_match_rust_helpers(self) -> None:
        captures, restores = build_override_exports_for_keys("__TEST", ("A", "B"))

        self.assertIn('__TEST_SET_0="${A+x}"', captures)
        self.assertIn('export B="${__TEST_1}"', restores)
        self.assertTrue(is_valid_shell_variable_name("_A1"))
        self.assertFalse(is_valid_shell_variable_name("1A"))
        self.assertEqual(shell_single_quote("echo 'hello'"), """echo '"'"'hello'"'"'""")
        self.assertTrue(isinstance(CODEX_PROXY_GIT_SSH_COMMAND_MARKER, str))


def _intercepted_exec_context(
    *,
    permission_profile: PermissionProfile | None = None,
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT,
    enable_shell_wrapper_parsing: bool = False,
) -> InterceptedExecPolicyContext:
    return InterceptedExecPolicyContext(
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=permission_profile or PermissionProfile.read_only(),
        file_system_sandbox_policy=FileSystemSandboxPolicy.restricted(()),
        sandbox_cwd=Path("/work"),
        sandbox_permissions=sandbox_permissions,
        enable_shell_wrapper_parsing=enable_shell_wrapper_parsing,
    )


if __name__ == "__main__":
    unittest.main()
