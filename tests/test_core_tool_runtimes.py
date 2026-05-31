import socket
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

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
    NetworkApprovalMode,
    ParsedShellCommand,
    PROMPT_CONFLICT_REASON,
    REJECT_RULES_APPROVAL_REASON,
    REJECT_SANDBOX_APPROVAL_REASON,
    SHELL_ESCALATE_HANDSHAKE_MESSAGE,
    SHELL_SOCKET_MAX_FDS_PER_MESSAGE,
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
    ShellEscalateServerPlan,
    ShellLocalExecvPlan,
    ShellPreparedExec,
    ShellSuperExecMessage,
    ShellSuperExecResult,
    ShellSuperExecSpawnPlan,
    ShellSuperExecSubprocessSpec,
    SandboxCommand,
    SandboxType,
    ToolRuntimeError,
    UnifiedExecOptions,
    UnifiedExecRequest,
    approval_sandbox_permissions,
    apply_patch_approval_keys,
    apply_patch_file_system_sandbox_context_for_attempt,
    apply_patch_permission_request_payload,
    apply_patch_sandbox_cwd,
    apply_patch_wants_no_sandbox_approval,
    build_override_exports_for_keys,
    build_sandbox_command,
    build_unified_exec_sandbox_command,
    commands_for_intercepted_exec_policy,
    disable_powershell_profile_for_elevated_windows_sandbox,
    exec_env_for_sandbox_permissions,
    execve_prompt_is_rejected_by_policy,
    extract_shell_script,
    effective_file_system_sandbox_policy,
    is_valid_shell_variable_name,
    join_program_and_argv,
    map_exec_result,
    managed_network_for_runtime,
    maybe_wrap_shell_lc_with_snapshot,
    shell_prepared_exec_effective_arg0,
    shell_prepared_exec_program_and_args,
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
    shell_network_approval_spec,
    shell_escalation_decision_after_review,
    shell_escalation_decision_for_approved_review,
    shell_escalation_decision_for_policy_decision,
    shell_request_escalation_execution,
    shell_permission_request_payload,
    shell_single_quote,
    shell_socket_sendmsg_with_fds,
    shell_socket_validate_fds_for_message,
    unified_exec_approval_keys,
    unified_exec_network_approval_spec,
    unified_exec_options,
    unified_exec_permission_request_payload,
    unified_exec_sandbox_cwd,
)
from pycodex.core import SandboxAttempt
from pycodex.core import DEFAULT_EXEC_COMMAND_TIMEOUT_MS, ExecCapturePolicy, ExecExpirationKind
from pycodex.core.exec import CancellationToken
from pycodex.core.tool_runtimes import flat_tool_name
from pycodex.protocol import (
    AskForApproval,
    CODEX_THREAD_ID_ENV_VAR,
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
    ToolName,
    WindowsSandboxLevel,
)


class ToolRuntimesTests(unittest.TestCase):
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
        self.assertTrue(apply_patch_wants_no_sandbox_approval(AskForApproval.ON_REQUEST))
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

    def test_apply_patch_file_system_sandbox_context_uses_active_attempt(self) -> None:
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
            exec_approval_requirement=ExecApprovalRequirement.needs_approval(),
        )

        self.assertEqual(shell_approval_keys(req)[0].command, req.command)
        self.assertEqual(shell_permission_request_payload(req).tool_input["description"], "because")
        self.assertFalse(req.additional_permissions_preapproved)
        self.assertEqual(req.approval_sandbox_permissions(), SandboxPermissions.USE_DEFAULT)
        spec = shell_network_approval_spec(req, call_id="call-1", tool_name=ToolName.plain("shell_command"))
        self.assertEqual(spec.mode, NetworkApprovalMode.IMMEDIATE)
        self.assertEqual(spec.command, "echo ok")
        self.assertIsInstance(spec.trigger, GuardianNetworkAccessTrigger)
        self.assertIsNone(spec.trigger.tty)
        self.assertEqual(ShellRuntimeBackend.SHELL_COMMAND_CLASSIC.value, "shell_command_classic")

    def test_unified_exec_runtime_boundaries_shape_keys_payload_and_deferred_network_spec(self) -> None:
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
            exec_approval_requirement=ExecApprovalRequirement.skip(),
            additional_permissions_preapproved=True,
        )

        self.assertTrue(unified_exec_approval_keys(req)[0].tty)
        self.assertTrue(req.additional_permissions_preapproved)
        self.assertEqual(req.approval_sandbox_permissions(), SandboxPermissions.USE_DEFAULT)
        self.assertEqual(unified_exec_permission_request_payload(req).tool_input["command"], "pwd")
        self.assertEqual(unified_exec_sandbox_cwd(req), Path("/sandbox"))
        spec = unified_exec_network_approval_spec(req, call_id="call-2", tool_name="unified_exec")
        self.assertEqual(spec.mode, NetworkApprovalMode.DEFERRED)
        self.assertTrue(spec.trigger.tty)
        self.assertEqual(flat_tool_name(ToolName.namespaced("mcp__", "tool")), "mcp__tool")
        self.assertEqual(flat_tool_name("shell_command"), "shell_command")
        with self.assertRaises(TypeError):
            flat_tool_name(123)
        with self.assertRaises(TypeError):
            flat_tool_name("")

    def test_unified_exec_options_combines_default_timeout_with_network_denial_cancellation(self) -> None:
        cancellation = CancellationToken()

        options = unified_exec_options(cancellation)

        self.assertIsInstance(options, UnifiedExecOptions)
        self.assertEqual(options.capture_policy, ExecCapturePolicy.SHELL_TOOL)
        self.assertEqual(options.expiration.kind, ExecExpirationKind.TIMEOUT_OR_CANCELLATION)
        self.assertEqual(options.expiration.timeout_ms(), DEFAULT_EXEC_COMMAND_TIMEOUT_MS)
        self.assertIs(options.expiration.cancellation, cancellation)

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
        with self.assertRaises(ValueError):
            shell_escalate_action_from_decision(ShellEscalationDecision.prompt())

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
                ("super_exec_send", client, ShellSuperExecMessage((7, 8, 9)), (40, 41, 42)),
                ("super_exec_receive", client),
            ],
        )
        with self.assertRaises(NotImplementedError):
            shell_escalate_client_plan_run(escalate_plan)
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

    def test_shell_super_exec_send_receive_exit_code_matches_split_socket_boundary(self) -> None:
        calls: list[tuple[ShellSuperExecMessage, tuple[int, ...]] | tuple[str]] = []

        def fake_send_with_fds(message: ShellSuperExecMessage, transferred_fds: tuple[int, ...]) -> None:
            calls.append((message, transferred_fds))

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
        self.assertEqual(calls, [(ShellSuperExecMessage((0, 1, 2)), (10, 11, 12)), ("receive",)])
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
            message: ShellSuperExecMessage,
            transferred_fds: tuple[int, ...],
        ) -> None:
            client_calls.append(("send", value_client, message, transferred_fds))

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
            [("send", client, ShellSuperExecMessage((0,)), (10,)), ("receive", client)],
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
        with patch("pycodex.core.tool_runtimes.os.dup2") as dup2:
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
        with patch("pycodex.core.tool_runtimes.os.dup2") as dup2:
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


if __name__ == "__main__":
    unittest.main()
