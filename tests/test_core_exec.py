import asyncio
import sys
from datetime import timedelta

import pytest

from pycodex import core as core_exports
from pycodex.core.exec import (
    DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
    EXEC_OUTPUT_MAX_BYTES,
    EXEC_TIMEOUT_EXIT_CODE,
    EXIT_CODE_SIGNAL_BASE,
    IO_DRAIN_TIMEOUT_MS,
    TIMEOUT_CODE,
    CancellationToken,
    ExecCapturePolicy,
    ExecExpiration,
    ExecExpirationKind,
    ExecExpirationOutcome,
    ExecParams,
    ExecRequest,
    ExecSandboxDenied,
    ExecSandboxSignal,
    ExecSandboxTimeout,
    RawExecToolCallOutput,
    RawOutputExecutionPlan,
    WindowsSandboxFilesystemOverrides,
    aggregate_output,
    append_capped,
    cancel_when_either,
    exec_params_from_request,
    extract_create_process_as_user_error_code,
    finalize_exec_result,
    is_likely_sandbox_denied,
    raw_output_execution_plan,
    raw_output_from_windows_sandbox_capture,
    read_output,
    resolve_windows_elevated_filesystem_overrides,
    resolve_windows_restricted_token_filesystem_overrides,
    run_raw_exec_subprocess,
    select_process_exec_tool_sandbox_type,
    should_use_windows_restricted_token_sandbox,
    unsupported_windows_restricted_token_sandbox_reason,
    unified_exec_sandbox_denial_message,
    windows_sandbox_uses_elevated_backend,
    windows_sandbox_spawn_failure_metric_tags,
    windowsapps_path_kind,
)
from pycodex.core.sandbox_tags import SandboxType, get_platform_sandbox
from pycodex.core.spawn import CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR
from pycodex.utils.string import approx_token_count
from pycodex.core.unified_exec import UNIFIED_EXEC_OUTPUT_MAX_TOKENS
from pycodex.protocol import (
    ExecToolCallOutput,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    SandboxPolicy,
    StreamOutput,
    WindowsSandboxLevel,
)


class AsyncChunkReader:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.reads = 0

    async def read(self, _size):
        self.reads += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_capture_policy_matches_shell_tool_defaults():
    assert ExecCapturePolicy.SHELL_TOOL.retained_bytes_cap() == EXEC_OUTPUT_MAX_BYTES
    assert ExecCapturePolicy.FULL_BUFFER.retained_bytes_cap() is None
    assert ExecCapturePolicy.SHELL_TOOL.uses_expiration() is True
    assert ExecCapturePolicy.FULL_BUFFER.uses_expiration() is False


def test_full_buffer_capture_policy_disables_caps_and_exec_expiration():
    # Rust test: codex-rs/core/src/exec_tests.rs::full_buffer_capture_policy_disables_caps_and_exec_expiration.
    assert ExecCapturePolicy.FULL_BUFFER.retained_bytes_cap() is None
    assert ExecCapturePolicy.FULL_BUFFER.io_drain_timeout() == timedelta(milliseconds=IO_DRAIN_TIMEOUT_MS)
    assert ExecCapturePolicy.FULL_BUFFER.uses_expiration() is False


def test_windows_proxy_enforcement_uses_elevated_backend():
    # Rust source: codex-rs/core/src/exec.rs::windows_sandbox_uses_elevated_backend.
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_proxy_enforcement_uses_elevated_backend.
    assert windows_sandbox_uses_elevated_backend(WindowsSandboxLevel.RESTRICTED_TOKEN, False) is False
    assert windows_sandbox_uses_elevated_backend(WindowsSandboxLevel.RESTRICTED_TOKEN, True) is True
    assert windows_sandbox_uses_elevated_backend(WindowsSandboxLevel.ELEVATED, False) is True
    assert windows_sandbox_uses_elevated_backend("elevated", False) is True
    with pytest.raises(TypeError, match="proxy_enforced must be a bool"):
        windows_sandbox_uses_elevated_backend(WindowsSandboxLevel.ELEVATED, 1)


def test_extract_create_process_as_user_error_code_matches_rust_marker():
    # Rust source: codex-rs/core/src/exec.rs::extract_create_process_as_user_error_code.
    assert extract_create_process_as_user_error_code("CreateProcessAsUserW failed: 2147942402: nope") == "2147942402"
    assert extract_create_process_as_user_error_code("prefix CreateProcessAsUserW failed: 5 denied") == "5"
    assert extract_create_process_as_user_error_code("CreateProcessAsUserW failed: denied") is None
    assert extract_create_process_as_user_error_code("CreateProcessW failed: 5") is None


def test_windowsapps_path_kind_matches_rust_substrings():
    # Rust source: codex-rs/core/src/exec.rs::windowsapps_path_kind.
    assert windowsapps_path_kind(r"C:\Program Files\WindowsApps\Package\tool.exe") == "windowsapps_package"
    assert (
        windowsapps_path_kind(r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe")
        == "windowsapps_alias"
    )
    assert windowsapps_path_kind(r"D:\Other\WindowsApps\tool.exe") == "windowsapps_other"
    assert windowsapps_path_kind(r"C:\Tools\tool.exe") == "other"


def test_windows_sandbox_spawn_failure_metric_tags_match_rust_shape():
    # Rust source: codex-rs/core/src/exec.rs::record_windows_sandbox_spawn_failure.
    tags = windows_sandbox_spawn_failure_metric_tags(
        r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\Python.EXE",
        WindowsSandboxLevel.ELEVATED,
        "CreateProcessAsUserW failed: 740: elevation required",
    )

    assert tags == (
        ("error_code", "740"),
        ("path_kind", "windowsapps_alias"),
        ("exe", "python.exe"),
        ("level", "elevated"),
    )
    assert (
        windows_sandbox_spawn_failure_metric_tags(
            None,
            WindowsSandboxLevel.RESTRICTED_TOKEN,
            "CreateProcessAsUserW failed: 5",
        )
        == (
            ("error_code", "5"),
            ("path_kind", "other"),
            ("exe", "unknown"),
            ("level", "legacy"),
        )
    )
    assert (
        windows_sandbox_spawn_failure_metric_tags(
            r"C:\Program Files\WindowsApps\tool.exe",
            WindowsSandboxLevel.RESTRICTED_TOKEN,
            "not a CreateProcessAsUserW failure",
        )
        is None
    )


def test_windows_restricted_token_skips_external_sandbox_policies():
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_skips_external_sandbox_policies.
    policy = SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED)
    file_system_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy(policy)

    assert (
        should_use_windows_restricted_token_sandbox("windows_sandbox", policy, file_system_policy)
        is False
    )


def test_windows_restricted_token_runs_for_legacy_restricted_policies():
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_runs_for_legacy_restricted_policies.
    policy = SandboxPolicy.new_read_only_policy()
    file_system_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy(policy)

    assert (
        should_use_windows_restricted_token_sandbox("windows_sandbox", policy, file_system_policy)
        is True
    )


def test_windows_restricted_token_allows_legacy_restricted_policies(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_allows_legacy_restricted_policies.
    policy = SandboxPolicy.new_read_only_policy()
    file_system_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy(policy)

    assert (
        unsupported_windows_restricted_token_sandbox_reason(
            "windows_sandbox",
            policy,
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
            tmp_path,
            WindowsSandboxLevel.RESTRICTED_TOKEN,
        )
        is None
    )


def test_windows_restricted_token_allows_legacy_workspace_write_policies(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_allows_legacy_workspace_write_policies.
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy(policy)

    assert (
        unsupported_windows_restricted_token_sandbox_reason(
            "windows_sandbox",
            policy,
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
            tmp_path,
            WindowsSandboxLevel.RESTRICTED_TOKEN,
        )
        is None
    )


def test_windows_elevated_allows_split_restricted_read_policies(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_allows_split_restricted_read_policies.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.read_only(network_access=False)
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    assert (
        unsupported_windows_restricted_token_sandbox_reason(
            "windows_sandbox",
            policy,
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
            tmp_path,
            WindowsSandboxLevel.ELEVATED,
        )
        is None
    )


def test_windows_elevated_supports_split_restricted_read_roots(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_supports_split_restricted_read_roots.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.read_only(network_access=False)
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    overrides = resolve_windows_elevated_filesystem_overrides(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        True,
    )

    assert overrides is not None
    assert overrides.read_roots_override == (docs.resolve(),)
    assert overrides.read_roots_include_platform_defaults is False
    assert overrides.write_roots_override is None
    assert overrides.additional_deny_read_paths == ()
    assert overrides.additional_deny_write_paths == ()


def test_windows_elevated_supports_split_write_read_carveouts(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_supports_split_write_read_carveouts.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    overrides = resolve_windows_elevated_filesystem_overrides(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        True,
    )

    assert overrides is not None
    assert overrides.read_roots_override is None
    assert overrides.read_roots_include_platform_defaults is False
    assert overrides.write_roots_override is None
    assert overrides.additional_deny_read_paths == ()
    assert overrides.additional_deny_write_paths == (docs.resolve(),)


def test_windows_elevated_supports_unreadable_split_carveouts(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_supports_unreadable_split_carveouts.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(blocked),
                FileSystemAccessMode.DENY,
            ),
        )
    )

    overrides = resolve_windows_elevated_filesystem_overrides(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        True,
    )

    assert overrides is not None
    assert overrides.read_roots_override is None
    assert overrides.read_roots_include_platform_defaults is False
    assert overrides.write_roots_override is None
    assert overrides.additional_deny_read_paths == (blocked.resolve(),)
    assert overrides.additional_deny_write_paths == (blocked.resolve(),)


def test_windows_elevated_supports_unreadable_globs(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_supports_unreadable_globs.
    secret = tmp_path / "app" / ".env"
    secret.parent.mkdir()
    secret.write_text("secret", encoding="utf-8")
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern("**/*.env"),
                FileSystemAccessMode.DENY,
            ),
        )
    )

    overrides = resolve_windows_elevated_filesystem_overrides(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        True,
    )

    assert overrides is not None
    assert overrides.read_roots_override is None
    assert overrides.read_roots_include_platform_defaults is False
    assert overrides.write_roots_override is None
    assert overrides.additional_deny_read_paths == (secret.resolve(),)
    assert overrides.additional_deny_write_paths == ()


def test_windows_elevated_rejects_reopened_writable_descendants(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_elevated_rejects_reopened_writable_descendants.
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(nested),
                FileSystemAccessMode.WRITE,
            ),
        )
    )

    reason = unsupported_windows_restricted_token_sandbox_reason(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        WindowsSandboxLevel.ELEVATED,
    )

    assert (
        reason
        == "windows elevated sandbox cannot reopen writable descendants under read-only carveouts directly; "
        "refusing to run unsandboxed"
    )


def test_windows_restricted_token_rejects_split_only_filesystem_policies(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_rejects_split_only_filesystem_policies.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    reason = unsupported_windows_restricted_token_sandbox_reason(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    assert (
        reason
        == "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; "
        "refusing to run unsandboxed"
    )


def test_windows_restricted_token_rejects_root_write_read_only_carveouts(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_rejects_root_write_read_only_carveouts.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    reason = unsupported_windows_restricted_token_sandbox_reason(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    assert (
        reason
        == "windows unelevated restricted-token sandbox cannot enforce split writable root sets directly; "
        "refusing to run unsandboxed"
    )


def test_windows_restricted_token_supports_full_read_split_write_read_carveouts(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_supports_full_read_split_write_read_carveouts.
    docs = tmp_path / "docs"
    docs.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(docs),
                FileSystemAccessMode.READ,
            ),
        )
    )

    overrides = resolve_windows_restricted_token_filesystem_overrides(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    assert overrides is not None
    assert overrides.read_roots_override is None
    assert overrides.read_roots_include_platform_defaults is False
    assert overrides.write_roots_override is None
    assert overrides.additional_deny_read_paths == ()
    assert overrides.additional_deny_write_paths == (docs.resolve(),)


def test_windows_restricted_token_rejects_unreadable_split_carveouts(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_rejects_unreadable_split_carveouts.
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    policy = SandboxPolicy.workspace_write(
        (),
        network_access=False,
        exclude_tmpdir_env_var=True,
        exclude_slash_tmp=True,
    )
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.READ,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            ),
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(blocked),
                FileSystemAccessMode.DENY,
            ),
        )
    )

    with pytest.raises(ValueError) as exc_info:
        resolve_windows_restricted_token_filesystem_overrides(
            "windows_sandbox",
            policy,
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
            tmp_path,
            WindowsSandboxLevel.RESTRICTED_TOKEN,
        )

    assert (
        str(exc_info.value)
        == "windows unelevated restricted-token sandbox cannot enforce deny-read restrictions directly; "
        "refusing to run unsandboxed"
    )


def test_windows_restricted_token_rejects_network_only_restrictions(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::windows_restricted_token_rejects_network_only_restrictions.
    policy = SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED)
    file_system_policy = FileSystemSandboxPolicy.unrestricted()

    reason = unsupported_windows_restricted_token_sandbox_reason(
        "windows_sandbox",
        policy,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
        WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    assert (
        reason
        == "windows sandbox backend cannot enforce file_system=Unrestricted, network=Restricted, "
        "legacy_policy=ExternalSandbox { network_access: Restricted }; refusing to run unsandboxed"
    )


def test_windows_restricted_token_helpers_are_exported_from_core():
    assert (
        core_exports.resolve_windows_elevated_filesystem_overrides
        is resolve_windows_elevated_filesystem_overrides
    )
    assert (
        core_exports.resolve_windows_restricted_token_filesystem_overrides
        is resolve_windows_restricted_token_filesystem_overrides
    )
    assert core_exports.select_process_exec_tool_sandbox_type is select_process_exec_tool_sandbox_type
    assert core_exports.should_use_windows_restricted_token_sandbox is should_use_windows_restricted_token_sandbox
    assert (
        core_exports.unsupported_windows_restricted_token_sandbox_reason
        is unsupported_windows_restricted_token_sandbox_reason
    )
    assert core_exports.read_output is read_output


def test_process_exec_tool_call_uses_platform_sandbox_for_network_only_restrictions():
    # Rust test: codex-rs/core/src/exec_tests.rs::process_exec_tool_call_uses_platform_sandbox_for_network_only_restrictions.
    expected = get_platform_sandbox(False) or SandboxType.NONE

    assert (
        select_process_exec_tool_sandbox_type(
            FileSystemSandboxPolicy.unrestricted(),
            NetworkSandboxPolicy.RESTRICTED,
            WindowsSandboxLevel.DISABLED,
            False,
        )
        is expected
    )


def test_exec_request_defaults_match_rust_constructor_shape(tmp_path):
    # Rust source: codex-rs/core/src/sandboxing/mod.rs::ExecRequest::new.
    request = ExecRequest(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        env={"A": "1"},
        capture_policy="full_buffer",
        sandbox="seccomp",
        windows_sandbox_level="disabled",
        windows_sandbox_private_desktop=False,
    )

    assert request.command == ("python", "-c", "print('ok')")
    assert request.cwd == tmp_path
    assert request.env == {"A": "1"}
    assert request.capture_policy is ExecCapturePolicy.FULL_BUFFER
    assert request.sandbox is SandboxType.LINUX_SECCOMP
    assert request.windows_sandbox_policy_cwd == tmp_path
    assert request.windows_sandbox_level is WindowsSandboxLevel.DISABLED
    assert request.network_sandbox_policy is NetworkSandboxPolicy.ENABLED
    assert request.windows_sandbox_filesystem_overrides is None


def test_exec_params_from_request_preserves_execute_exec_request_fields(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::execute_exec_request.
    expiration = ExecExpiration.timeout_after(timedelta(milliseconds=250))
    request = ExecRequest(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        env={"A": "1"},
        network={"proxy": "managed"},
        expiration=expiration,
        capture_policy=ExecCapturePolicy.FULL_BUFFER,
        sandbox=SandboxType.WINDOWS_RESTRICTED_TOKEN,
        windows_sandbox_policy_cwd=tmp_path / "sandbox-cwd",
        windows_sandbox_level=WindowsSandboxLevel.ELEVATED,
        windows_sandbox_private_desktop=True,
        network_sandbox_policy=NetworkSandboxPolicy.RESTRICTED,
        arg0="python-real",
    )

    params = exec_params_from_request(request)

    assert params.command == request.command
    assert params.cwd == request.cwd
    assert params.env == request.env
    assert params.network == request.network
    assert params.expiration is expiration
    assert params.capture_policy is ExecCapturePolicy.FULL_BUFFER
    assert params.windows_sandbox_level is WindowsSandboxLevel.ELEVATED
    assert params.windows_sandbox_private_desktop is True
    assert params.arg0 == "python-real"
    assert params.justification is None
    assert params.sandbox_permissions is None


def test_raw_output_execution_plan_routes_non_windows_to_exec(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::get_raw_output_result.
    params = ExecParams(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=250)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    plan = raw_output_execution_plan(
        params,
        SandboxType.WINDOWS_RESTRICTED_TOKEN,
        tmp_path,
        target_os="linux",
    )

    assert isinstance(plan, RawOutputExecutionPlan)
    assert plan.backend == "exec"
    assert plan.timeout_ms is None
    assert plan.use_windows_elevated_backend is False


def test_raw_output_execution_plan_routes_windows_restricted_token_to_windows_sandbox(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::get_raw_output_result and ::exec_windows_sandbox.
    overrides = WindowsSandboxFilesystemOverrides(additional_deny_write_paths=(tmp_path / "readonly",))
    params = ExecParams(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        network={"proxy": "managed"},
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=250)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
        windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    plan = raw_output_execution_plan(
        params,
        SandboxType.WINDOWS_RESTRICTED_TOKEN,
        tmp_path / "sandbox-cwd",
        overrides,
        target_os="win32",
    )

    assert plan.backend == "windows_sandbox"
    assert plan.timeout_ms == 250
    assert plan.proxy_enforced is True
    assert plan.use_windows_elevated_backend is True
    assert plan.windows_sandbox_policy_cwd == tmp_path / "sandbox-cwd"
    assert plan.windows_sandbox_filesystem_overrides is overrides


def test_raw_output_execution_plan_disables_windows_timeout_for_full_buffer(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::exec_windows_sandbox timeout_ms branch.
    params = ExecParams(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=1)),
        capture_policy=ExecCapturePolicy.FULL_BUFFER,
        windows_sandbox_level=WindowsSandboxLevel.RESTRICTED_TOKEN,
    )

    plan = raw_output_execution_plan(
        params,
        SandboxType.WINDOWS_RESTRICTED_TOKEN,
        tmp_path,
        target_os="win32",
    )

    assert plan.backend == "windows_sandbox"
    assert plan.timeout_ms is None
    assert plan.proxy_enforced is False
    assert plan.use_windows_elevated_backend is False


def test_raw_output_from_windows_sandbox_capture_caps_shell_streams():
    # Rust source: codex-rs/core/src/exec.rs::exec_windows_sandbox capture conversion.
    raw = raw_output_from_windows_sandbox_capture(
        exit_code=7,
        stdout=b"a" * (EXEC_OUTPUT_MAX_BYTES + 3),
        stderr=b"b" * (EXEC_OUTPUT_MAX_BYTES + 5),
        timed_out=True,
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    assert raw.exit_code == 7
    assert len(raw.stdout.text) == EXEC_OUTPUT_MAX_BYTES
    assert len(raw.stderr.text) == EXEC_OUTPUT_MAX_BYTES
    assert len(raw.aggregated_output.text) == EXEC_OUTPUT_MAX_BYTES
    assert raw.aggregated_output.text.startswith(b"a" * (EXEC_OUTPUT_MAX_BYTES // 3))
    assert raw.aggregated_output.text.endswith(b"b" * (EXEC_OUTPUT_MAX_BYTES - (EXEC_OUTPUT_MAX_BYTES // 3)))
    assert raw.timed_out is True


def test_raw_output_from_windows_sandbox_capture_retains_full_buffer_streams():
    # Rust source: codex-rs/core/src/exec.rs::exec_windows_sandbox capture conversion.
    stdout = b"a" * (EXEC_OUTPUT_MAX_BYTES + 3)
    stderr = b"b" * 5

    raw = raw_output_from_windows_sandbox_capture(
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        capture_policy=ExecCapturePolicy.FULL_BUFFER,
    )

    assert raw.exit_code == 0
    assert raw.stdout.text == stdout
    assert raw.stderr.text == stderr
    assert raw.aggregated_output.text == stdout + stderr
    assert raw.timed_out is False


def test_run_raw_exec_subprocess_captures_stdout_stderr_and_after_spawn(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::exec and ::consume_output.
    spawned = []
    params = ExecParams(
        command=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('out'); sys.stderr.write('err')",
        ),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(seconds=5)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    raw = asyncio.run(run_raw_exec_subprocess(params, after_spawn=lambda: spawned.append(True)))

    assert spawned == [True]
    assert raw.exit_code == 0
    assert raw.stdout.text == b"out"
    assert raw.stderr.text == b"err"
    assert raw.aggregated_output.text == b"outerr"
    assert raw.timed_out is False


def test_run_raw_exec_subprocess_applies_restricted_network_env(tmp_path):
    # Rust source: codex-rs/core/src/spawn.rs::spawn_child_async.
    params = ExecParams(
        command=(
            sys.executable,
            "-c",
            (
                "import os, sys; "
                f"sys.stdout.write(os.getenv({CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR!r}, ''))"
            ),
        ),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(seconds=5)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    raw = asyncio.run(run_raw_exec_subprocess(params, NetworkSandboxPolicy.RESTRICTED))

    assert raw.exit_code == 0
    assert raw.stdout.text == b"1"
    assert raw.timed_out is False


def test_run_raw_exec_subprocess_applies_managed_network_env(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::exec applies NetworkProxy::apply_to_env before spawn.
    class ManagedNetwork:
        def apply_to_env(self, env):
            env["PYCODEX_MANAGED_NETWORK_TEST"] = "managed"

    params = ExecParams(
        command=(
            sys.executable,
            "-c",
            "import os, sys; sys.stdout.write(os.getenv('PYCODEX_MANAGED_NETWORK_TEST', ''))",
        ),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(seconds=5)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
        network=ManagedNetwork(),
    )

    raw = asyncio.run(run_raw_exec_subprocess(params))

    assert raw.exit_code == 0
    assert raw.stdout.text == b"managed"
    assert raw.timed_out is False


def test_run_raw_exec_subprocess_times_out_shell_tool(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::consume_output timed-out branch.
    params = ExecParams(
        command=(sys.executable, "-c", "import time; time.sleep(5)"),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=20)),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    raw = asyncio.run(run_raw_exec_subprocess(params))

    assert raw.exit_code == EXIT_CODE_SIGNAL_BASE + TIMEOUT_CODE
    assert raw.timed_out is True
    with pytest.raises(ExecSandboxTimeout) as exc_info:
        finalize_exec_result(raw, "none", timedelta(milliseconds=20))
    assert exc_info.value.output.exit_code == EXEC_TIMEOUT_EXIT_CODE


def test_run_raw_exec_subprocess_respects_cancellation_token(tmp_path):
    # Rust test: codex-rs/core/src/exec_tests.rs::process_exec_tool_call_respects_cancellation_token.
    cancel_token = CancellationToken()
    params = ExecParams(
        command=(sys.executable, "-c", "import time; time.sleep(5)"),
        cwd=tmp_path,
        expiration=ExecExpiration.cancellation(cancel_token),
        capture_policy=ExecCapturePolicy.SHELL_TOOL,
    )

    raw = asyncio.run(run_raw_exec_subprocess(params, after_spawn=cancel_token.cancel))

    assert raw.exit_code == 1
    assert raw.timed_out is False


def test_run_raw_exec_subprocess_full_buffer_ignores_expiration_and_keeps_output(tmp_path):
    # Rust tests: exec_full_buffer_capture_ignores_expiration and
    # process_exec_tool_call_preserves_full_buffer_capture_policy.
    byte_count = EXEC_OUTPUT_MAX_BYTES + 128
    params = ExecParams(
        command=(sys.executable, "-c", f"import sys; sys.stdout.write('a' * {byte_count})"),
        cwd=tmp_path,
        expiration=ExecExpiration.timeout_after(timedelta(milliseconds=1)),
        capture_policy=ExecCapturePolicy.FULL_BUFFER,
    )

    raw = asyncio.run(run_raw_exec_subprocess(params))

    assert raw.exit_code == 0
    assert raw.timed_out is False
    assert len(raw.stdout.text) == byte_count
    assert raw.aggregated_output.text == b"a" * byte_count


def test_exec_expiration_from_optional_timeout():
    assert ExecExpiration.from_timeout_ms(None).timeout_ms() == DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    assert ExecExpiration.from_timeout_ms(250).timeout_ms() == 250


def test_exec_expiration_timeout_ms_matches_rust_variants():
    # Rust source: codex-rs/core/src/exec.rs::ExecExpiration::timeout_ms.
    token = CancellationToken()

    assert ExecExpiration.timeout_after(timedelta(milliseconds=125)).timeout_ms() == 125
    assert ExecExpiration.default_timeout().timeout_ms() == DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    assert ExecExpiration.cancellation(token).timeout_ms() is None
    assert ExecExpiration.timeout_or_cancellation(timedelta(milliseconds=250), token).timeout_ms() == 250


def test_exec_expiration_with_cancellation_preserves_timeout_ms():
    # Rust source: codex-rs/core/src/exec.rs::ExecExpiration::with_cancellation.
    token = CancellationToken()

    timeout = ExecExpiration.timeout_after(timedelta(milliseconds=125)).with_cancellation(token)
    default_timeout = ExecExpiration.default_timeout().with_cancellation(token)

    assert timeout.kind is ExecExpirationKind.TIMEOUT_OR_CANCELLATION
    assert timeout.timeout_ms() == 125
    assert timeout.cancellation is token
    assert default_timeout.kind is ExecExpirationKind.TIMEOUT_OR_CANCELLATION
    assert default_timeout.timeout_ms() == DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    assert default_timeout.cancellation is token


def test_exec_expiration_rejects_negative_timeout_durations():
    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration.timeout_after(timedelta(milliseconds=-1))

    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration.timeout_or_cancellation(timedelta(milliseconds=-1), CancellationToken())

    with pytest.raises(ValueError, match="timeout must be non-negative"):
        ExecExpiration(ExecExpiration.kind if False else ExecExpirationKind.TIMEOUT, timeout=timedelta(milliseconds=-1))


def test_cancel_when_either_is_lazy_and_observes_either_parent():
    first = CancellationToken()
    second = CancellationToken()

    combined = cancel_when_either(first, second)

    assert combined.is_cancelled() is False
    second.cancel()
    assert combined.is_cancelled() is True
    asyncio.run(combined.cancelled())


def test_cancelling_combined_token_waiter_reaps_parent_waiters():
    # Rust source: codex-rs/core/src/exec.rs::cancel_when_either. Dropping the
    # selected future must also drop both unselected cancellation futures.
    async def scenario() -> None:
        combined = cancel_when_either(CancellationToken(), CancellationToken())
        waiter = asyncio.create_task(combined.cancelled())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        await asyncio.sleep(0)

        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        assert pending == []

    asyncio.run(scenario())


def test_exec_expiration_with_cancellation_can_combine_without_running_loop():
    first = CancellationToken()
    second = CancellationToken()

    expiration = ExecExpiration.cancellation(first).with_cancellation(second)

    assert expiration.timeout_ms() is None
    assert expiration.cancellation is not None
    assert expiration.cancellation.is_cancelled() is False
    first.cancel()
    assert expiration.cancellation.is_cancelled() is True


def test_natural_process_exit_reaps_combined_expiration_waiters(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::consume_output. Tokio select drops
    # the expiration future when the process exits first; asyncio must reap the
    # equivalent timeout and cancellation tasks explicitly.
    async def scenario() -> None:
        expiration = ExecExpiration.default_timeout().with_cancellation(
            cancel_when_either(CancellationToken(), CancellationToken())
        )
        params = ExecParams(
            command=(sys.executable, "-c", "print('ok')"),
            cwd=tmp_path,
            expiration=expiration,
            capture_policy=ExecCapturePolicy.SHELL_TOOL,
        )

        raw = await run_raw_exec_subprocess(params)
        assert raw.exit_code == 0
        await asyncio.sleep(0)

        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        assert pending == []

    asyncio.run(scenario())


def test_timeout_or_cancellation_prefers_pre_cancelled_token():
    token = CancellationToken()
    token.cancel()
    expiration = ExecExpiration.timeout_or_cancellation(timedelta(seconds=60), token)

    assert asyncio.run(expiration.wait_with_outcome()) is ExecExpirationOutcome.CANCELLED


def test_append_capped_stops_at_limit():
    data = bytearray(b"ab")

    append_capped(data, b"cdef", 4)

    assert bytes(data) == b"abcd"


def test_read_output_limits_retained_bytes_for_shell_capture():
    # Rust test: codex-rs/core/src/exec_tests.rs::read_output_limits_retained_bytes_for_shell_capture.
    reader = AsyncChunkReader((b"a" * EXEC_OUTPUT_MAX_BYTES, b"b" * 128))

    output = asyncio.run(read_output(reader, None, False, EXEC_OUTPUT_MAX_BYTES))

    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES
    assert output.text == b"a" * EXEC_OUTPUT_MAX_BYTES
    assert reader.reads == 3


def test_read_output_retains_all_bytes_for_full_buffer_capture():
    # Rust test: codex-rs/core/src/exec_tests.rs::read_output_retains_all_bytes_for_full_buffer_capture.
    extra = b"b" * 128
    reader = AsyncChunkReader((b"a" * EXEC_OUTPUT_MAX_BYTES, extra))

    output = asyncio.run(read_output(reader, None, False, None))

    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES + len(extra)
    assert output.text == (b"a" * EXEC_OUTPUT_MAX_BYTES) + extra


def test_aggregate_output_rebalances_stdout_and_stderr():
    stdout = StreamOutput(b"abcdef")
    stderr = StreamOutput(b"123456789")

    output = aggregate_output(stdout, stderr, 9)

    assert output.text == b"abc123456"


def test_aggregate_output_prefers_stderr_on_contention():
    # Rust test: codex-rs/core/src/exec_tests.rs::aggregate_output_prefers_stderr_on_contention.
    stdout = StreamOutput(b"a" * EXEC_OUTPUT_MAX_BYTES)
    stderr = StreamOutput(b"b" * EXEC_OUTPUT_MAX_BYTES)

    output = aggregate_output(stdout, stderr, EXEC_OUTPUT_MAX_BYTES)

    stdout_cap = EXEC_OUTPUT_MAX_BYTES // 3
    stderr_cap = EXEC_OUTPUT_MAX_BYTES - stdout_cap
    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES
    assert output.text[:stdout_cap] == b"a" * stdout_cap
    assert output.text[stdout_cap:] == b"b" * stderr_cap


def test_aggregate_output_fills_remaining_capacity_with_stderr():
    # Rust test: codex-rs/core/src/exec_tests.rs::aggregate_output_fills_remaining_capacity_with_stderr.
    stdout_len = EXEC_OUTPUT_MAX_BYTES // 10
    stdout = StreamOutput(b"a" * stdout_len)
    stderr = StreamOutput(b"b" * EXEC_OUTPUT_MAX_BYTES)

    output = aggregate_output(stdout, stderr, EXEC_OUTPUT_MAX_BYTES)

    stderr_cap = EXEC_OUTPUT_MAX_BYTES - stdout_len
    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES
    assert output.text[:stdout_len] == b"a" * stdout_len
    assert output.text[stdout_len:] == b"b" * stderr_cap


def test_aggregate_output_rebalances_when_stderr_is_small():
    # Rust test: codex-rs/core/src/exec_tests.rs::aggregate_output_rebalances_when_stderr_is_small.
    stdout = StreamOutput(b"a" * EXEC_OUTPUT_MAX_BYTES)
    stderr = StreamOutput(b"b")

    output = aggregate_output(stdout, stderr, EXEC_OUTPUT_MAX_BYTES)

    stdout_len = EXEC_OUTPUT_MAX_BYTES - 1
    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES
    assert output.text[:stdout_len] == b"a" * stdout_len
    assert output.text[stdout_len:] == b"b"


def test_aggregate_output_keeps_stdout_then_stderr_when_under_cap():
    # Rust test: codex-rs/core/src/exec_tests.rs::aggregate_output_keeps_stdout_then_stderr_when_under_cap.
    output = aggregate_output(StreamOutput(b"aaaa"), StreamOutput(b"bbb"), EXEC_OUTPUT_MAX_BYTES)

    assert output.text == b"aaaabbb"
    assert output.truncated_after_lines is None


def test_aggregate_output_keeps_all_bytes_when_uncapped():
    # Rust test: codex-rs/core/src/exec_tests.rs::aggregate_output_keeps_all_bytes_when_uncapped.
    stdout = StreamOutput(b"a" * EXEC_OUTPUT_MAX_BYTES)
    stderr = StreamOutput(b"b" * EXEC_OUTPUT_MAX_BYTES)

    output = aggregate_output(stdout, stderr, None)

    assert len(output.text) == EXEC_OUTPUT_MAX_BYTES * 2
    assert output.text[:EXEC_OUTPUT_MAX_BYTES] == b"a" * EXEC_OUTPUT_MAX_BYTES
    assert output.text[EXEC_OUTPUT_MAX_BYTES:] == b"b" * EXEC_OUTPUT_MAX_BYTES


def test_finalize_exec_result_converts_bytes_and_timeout():
    raw = RawExecToolCallOutput(
        exit_code=0,
        stdout=StreamOutput(b"out"),
        stderr=StreamOutput(b"err"),
        aggregated_output=StreamOutput(b"outerr"),
        timed_out=True,
    )

    with pytest.raises(ExecSandboxTimeout) as exc_info:
        finalize_exec_result(raw, "linux_seccomp", timedelta(milliseconds=5))

    assert exc_info.value.output.exit_code == EXEC_TIMEOUT_EXIT_CODE
    assert exc_info.value.output.timed_out is True


def test_finalize_exec_result_reports_non_timeout_signal():
    raw = RawExecToolCallOutput(
        exit_code=None,
        signal=9,
        stdout=StreamOutput(b""),
        stderr=StreamOutput(b""),
        aggregated_output=StreamOutput(b""),
    )

    with pytest.raises(ExecSandboxSignal):
        finalize_exec_result(raw, "linux_seccomp", timedelta())


def test_likely_sandbox_denied_uses_keywords_and_rejects_command_not_found():
    denied = ExecToolCallOutput(exit_code=1, stderr=StreamOutput.new("operation not permitted"))
    command_not_found = ExecToolCallOutput(exit_code=127, stderr=StreamOutput.new("not found"))

    assert is_likely_sandbox_denied("linux_seccomp", denied) is True
    assert is_likely_sandbox_denied("linux_seccomp", command_not_found) is False


def test_sandbox_detection_requires_keywords():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_requires_keywords.
    output = ExecToolCallOutput(exit_code=1)

    assert is_likely_sandbox_denied("linux_seccomp", output) is False


def test_sandbox_detection_identifies_keyword_in_stderr():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_identifies_keyword_in_stderr.
    output = ExecToolCallOutput(exit_code=1, stderr=StreamOutput.new("Operation not permitted"))

    assert is_likely_sandbox_denied("linux_seccomp", output) is True


def test_sandbox_detection_respects_quick_reject_exit_codes():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_respects_quick_reject_exit_codes.
    output = ExecToolCallOutput(exit_code=127, stderr=StreamOutput.new("command not found"))

    assert is_likely_sandbox_denied("linux_seccomp", output) is False


def test_sandbox_detection_ignores_non_sandbox_mode():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_ignores_non_sandbox_mode.
    output = ExecToolCallOutput(exit_code=1, stderr=StreamOutput.new("Operation not permitted"))

    assert is_likely_sandbox_denied("none", output) is False


def test_sandbox_detection_ignores_network_policy_text_in_non_sandbox_mode():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_ignores_network_policy_text_in_non_sandbox_mode.
    output = ExecToolCallOutput(
        exit_code=0,
        aggregated_output=StreamOutput.new(
            'CODEX_NETWORK_POLICY_DECISION {"decision":"ask","reason":"not_allowed","source":"decider","protocol":"http","host":"google.com","port":80}'
        ),
    )

    assert is_likely_sandbox_denied("none", output) is False


def test_sandbox_detection_uses_aggregated_output():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_uses_aggregated_output.
    output = ExecToolCallOutput(
        exit_code=101,
        aggregated_output=StreamOutput.new("cargo failed: Read-only file system when writing target"),
    )

    assert is_likely_sandbox_denied("macos_seatbelt", output) is True


def test_sandbox_detection_ignores_network_policy_text_with_zero_exit_code():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_ignores_network_policy_text_with_zero_exit_code.
    output = ExecToolCallOutput(
        exit_code=0,
        aggregated_output=StreamOutput.new(
            'CODEX_NETWORK_POLICY_DECISION {"decision":"ask","source":"decider","protocol":"http","host":"google.com","port":80}'
        ),
    )

    assert is_likely_sandbox_denied("linux_seccomp", output) is False


def test_sandbox_detection_flags_sigsys_exit_code():
    # Rust test: codex-rs/core/src/exec_tests.rs::sandbox_detection_flags_sigsys_exit_code.
    output = ExecToolCallOutput(exit_code=EXIT_CODE_SIGNAL_BASE + 31)

    assert is_likely_sandbox_denied("linux_seccomp", output) is True


def test_finalize_exec_result_raises_denied_for_sandbox_keyword():
    raw = RawExecToolCallOutput(
        exit_code=1,
        stdout=StreamOutput(b""),
        stderr=StreamOutput(b"permission denied"),
        aggregated_output=StreamOutput(b"permission denied"),
    )

    with pytest.raises(ExecSandboxDenied):
        finalize_exec_result(raw, "linux_seccomp", timedelta())


def test_unified_exec_sandbox_denial_message_matches_process_boundary():
    assert unified_exec_sandbox_denial_message("none", True, 1, "permission denied") is None
    assert unified_exec_sandbox_denial_message("linux_seccomp", False, 1, "permission denied") is None
    assert unified_exec_sandbox_denial_message("linux_seccomp", True, 127, "not found") is None
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, 1, "permission denied")
        == "permission denied"
    )
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, None, "operation not permitted")
        == "operation not permitted"
    )


def test_unified_exec_sandbox_denial_message_falls_back_to_exit_code_when_empty():
    assert (
        unified_exec_sandbox_denial_message("linux_seccomp", True, EXIT_CODE_SIGNAL_BASE + 31, "")
        == "Process exited with code 159"
    )


def test_unified_exec_sandbox_denial_message_truncates_long_output():
    text = "permission denied\n" + ("x" * ((UNIFIED_EXEC_OUTPUT_MAX_TOKENS * 4) + 128))

    message = unified_exec_sandbox_denial_message("linux_seccomp", True, 1, text)

    assert message is not None
    assert message != text
    assert message.startswith("Total output lines: 2\n\n")
    assert "tokens truncated" in message
    assert approx_token_count(message) < approx_token_count(text)


def test_unified_exec_sandbox_denial_message_is_exported_from_core():
    assert core_exports.unified_exec_sandbox_denial_message is unified_exec_sandbox_denial_message
