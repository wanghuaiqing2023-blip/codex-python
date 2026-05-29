import tempfile
import unittest
from pathlib import Path

from pycodex.core import (
    CODEX_PROXY_GIT_SSH_COMMAND_MARKER,
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
    ShellRequest,
    Shell,
    ShellSnapshot,
    ShellType,
    ShellRuntimeBackend,
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
    disable_powershell_profile_for_elevated_windows_sandbox,
    exec_env_for_sandbox_permissions,
    execve_prompt_is_rejected_by_policy,
    extract_shell_script,
    flat_tool_name,
    is_valid_shell_variable_name,
    join_program_and_argv,
    map_exec_result,
    managed_network_for_runtime,
    maybe_wrap_shell_lc_with_snapshot,
    shell_approval_keys,
    shell_network_approval_spec,
    shell_permission_request_payload,
    shell_single_quote,
    unified_exec_approval_keys,
    unified_exec_network_approval_spec,
    unified_exec_options,
    unified_exec_permission_request_payload,
    unified_exec_sandbox_cwd,
)
from pycodex.core import SandboxAttempt
from pycodex.core import CancellationToken, DEFAULT_EXEC_COMMAND_TIMEOUT_MS, ExecCapturePolicy, ExecExpirationKind
from pycodex.protocol import (
    AskForApproval,
    CODEX_THREAD_ID_ENV_VAR,
    FileChange,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
    AdditionalPermissionProfile,
    FileSystemPermissions,
    SandboxPermissions,
    ToolName,
    WindowsSandboxLevel,
)


class ToolRuntimesTests(unittest.TestCase):
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
            FileSystemPath.path(Path("/tmp/allowed")),
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
        )

        self.assertTrue(unified_exec_approval_keys(req)[0].tty)
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

    def test_build_sandbox_command_splits_program_and_args(self) -> None:
        command = build_sandbox_command(["/bin/echo", "ok"], "/repo", {"A": "B"})

        self.assertEqual(command, SandboxCommand("/bin/echo", ("ok",), Path("/repo"), {"A": "B"}))

    def test_build_sandbox_command_rejects_empty_args(self) -> None:
        with self.assertRaises(ToolRuntimeError) as ctx:
            build_sandbox_command([], "/repo", {})

        self.assertIn("command args are empty", str(ctx.exception))
        self.assertEqual(ctx.exception.error.message, "command args are empty")

    def test_exec_env_for_escalated_permissions_removes_codex_proxy_only_when_active(self) -> None:
        env = {"CUSTOM": "kept", PROXY_ACTIVE_ENV_KEY: "1", "HTTP_PROXY": "http://codex.proxy"}

        cleaned = exec_env_for_sandbox_permissions(env, SandboxPermissions.REQUIRE_ESCALATED)

        self.assertEqual(cleaned, {"CUSTOM": "kept"})
        self.assertEqual(env["HTTP_PROXY"], "http://codex.proxy")

    def test_exec_env_for_escalated_permissions_keeps_user_proxy_without_active_marker(self) -> None:
        env = {"CUSTOM": "kept", "HTTP_PROXY": "http://user.proxy"}

        cleaned = exec_env_for_sandbox_permissions(env, SandboxPermissions.REQUIRE_ESCALATED)

        self.assertEqual(cleaned["HTTP_PROXY"], "http://user.proxy")
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

        self.assertEqual(rewritten[0], "/bin/zsh")
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
