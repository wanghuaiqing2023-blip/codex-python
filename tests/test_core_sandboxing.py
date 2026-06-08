import asyncio
import sys
from datetime import timedelta

import pytest

from pycodex.core.exec import ExecCapturePolicy, ExecExpiration
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.sandboxing import (
    ExecOptions,
    ExecRequest,
    SandboxExecRequest,
    compatibility_sandbox_policy,
    compatibility_sandbox_policy_for_permission_profile,
    execute_exec_request_with_after_spawn,
    from_sandbox_exec_request,
    new_exec_request,
)
from pycodex.core.spawn import CODEX_SANDBOX_ENV_VAR, CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPolicy,
    WindowsSandboxLevel,
)


def test_new_exec_request_matches_rust_constructor_runtime_permissions(tmp_path):
    # Rust source: codex-rs/core/src/sandboxing/mod.rs::ExecRequest::new.
    profile = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.RESTRICTED)
    expiration = ExecExpiration.timeout_after(timedelta(milliseconds=125))

    request = new_exec_request(
        ["python", "-c", "print('ok')"],
        tmp_path,
        {"A": "1"},
        None,
        expiration,
        ExecCapturePolicy.FULL_BUFFER,
        SandboxType.LINUX_SECCOMP,
        WindowsSandboxLevel.DISABLED,
        False,
        profile,
        "python-real",
    )

    assert isinstance(request, ExecRequest)
    assert request.command == ("python", "-c", "print('ok')")
    assert request.cwd == tmp_path
    assert request.env == {"A": "1"}
    assert request.expiration is expiration
    assert request.capture_policy is ExecCapturePolicy.FULL_BUFFER
    assert request.sandbox is SandboxType.LINUX_SECCOMP
    assert request.windows_sandbox_policy_cwd == tmp_path
    assert request.permission_profile is profile
    assert request.file_system_sandbox_policy == profile.file_system_sandbox_policy()
    assert request.network_sandbox_policy is NetworkSandboxPolicy.RESTRICTED
    assert request.windows_sandbox_filesystem_overrides is None
    assert request.arg0 == "python-real"


def test_core_root_exports_sandboxing_adapter_surface():
    # Rust source: codex-rs/core/src/lib.rs declares `pub mod sandboxing`.
    import pycodex.core as core

    assert core.ExecOptions is ExecOptions
    assert core.SandboxExecRequest is SandboxExecRequest
    assert core.new_exec_request is new_exec_request
    assert core.from_sandbox_exec_request is from_sandbox_exec_request
    assert core.execute_exec_request_with_after_spawn is execute_exec_request_with_after_spawn


def test_from_sandbox_exec_request_adds_network_disabled_env(tmp_path):
    # Rust source: codex-rs/core/src/sandboxing/mod.rs::ExecRequest::from_sandbox_exec_request.
    profile = PermissionProfile.read_only()
    file_system_policy, network_policy = profile.to_runtime_permissions()
    request = SandboxExecRequest(
        command=("python", "-c", "print('ok')"),
        cwd=tmp_path,
        env={"A": "1"},
        sandbox=SandboxType.LINUX_SECCOMP,
        windows_sandbox_level=WindowsSandboxLevel.DISABLED,
        windows_sandbox_private_desktop=True,
        permission_profile=profile,
        file_system_sandbox_policy=file_system_policy,
        network_sandbox_policy=network_policy,
        arg0="codex-linux-sandbox",
    )
    options = ExecOptions(
        ExecExpiration.timeout_after(timedelta(milliseconds=250)),
        ExecCapturePolicy.SHELL_TOOL,
    )

    exec_request = from_sandbox_exec_request(request, options, tmp_path / "policy-cwd")

    assert exec_request.command == request.command
    assert exec_request.cwd == tmp_path
    assert exec_request.env["A"] == "1"
    assert exec_request.env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] == "1"
    assert exec_request.expiration is options.expiration
    assert exec_request.capture_policy is ExecCapturePolicy.SHELL_TOOL
    assert exec_request.windows_sandbox_policy_cwd == tmp_path / "policy-cwd"
    assert exec_request.windows_sandbox_private_desktop is True
    assert exec_request.permission_profile is profile
    assert exec_request.file_system_sandbox_policy == file_system_policy
    assert exec_request.network_sandbox_policy is NetworkSandboxPolicy.RESTRICTED
    assert exec_request.arg0 == "codex-linux-sandbox"


def test_from_sandbox_exec_request_adds_macos_seatbelt_marker(monkeypatch, tmp_path):
    # Rust source: macOS-only branch in ExecRequest::from_sandbox_exec_request.
    monkeypatch.setattr(sys, "platform", "darwin")
    profile = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED)
    file_system_policy, network_policy = profile.to_runtime_permissions()

    exec_request = from_sandbox_exec_request(
        SandboxExecRequest(
            command=("echo", "ok"),
            cwd=tmp_path,
            sandbox=SandboxType.MACOS_SEATBELT,
            permission_profile=profile,
            file_system_sandbox_policy=file_system_policy,
            network_sandbox_policy=network_policy,
        ),
        ExecOptions(ExecExpiration.default_timeout(), ExecCapturePolicy.SHELL_TOOL),
        tmp_path,
    )

    assert exec_request.env[CODEX_SANDBOX_ENV_VAR] == "seatbelt"
    assert CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR not in exec_request.env


def test_compatibility_sandbox_policy_uses_permission_profile_legacy_policy(tmp_path):
    # Rust source: codex-sandboxing/src/manager.rs::compatibility_sandbox_policy_for_permission_profile.
    profile = PermissionProfile.disabled()
    request = new_exec_request(
        ("python", "-c", "print('ok')"),
        tmp_path,
        {},
        None,
        ExecExpiration.default_timeout(),
        ExecCapturePolicy.SHELL_TOOL,
        SandboxType.NONE,
        WindowsSandboxLevel.DISABLED,
        False,
        profile,
        None,
    )

    assert compatibility_sandbox_policy(request) == SandboxPolicy.danger_full_access()


def test_compatibility_sandbox_policy_falls_back_to_workspace_write(tmp_path):
    # Rust source: codex-sandboxing/src/manager.rs::compatibility_workspace_write_policy.
    outside = tmp_path.parent / "outside"
    file_system_policy = FileSystemSandboxPolicy.restricted(
        (
            FileSystemSandboxEntry(
                FileSystemPath.explicit_path(outside),
                FileSystemAccessMode.WRITE,
            ),
        )
    )
    profile = PermissionProfile.from_runtime_permissions(
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
    )

    policy = compatibility_sandbox_policy_for_permission_profile(
        profile,
        file_system_policy,
        NetworkSandboxPolicy.RESTRICTED,
        tmp_path,
    )

    assert policy.type == "workspace-write"
    assert outside in policy.writable_roots
    assert policy.network_access is False


def test_execute_exec_request_with_after_spawn_runs_projected_request(tmp_path):
    # Rust source: codex-rs/core/src/sandboxing/mod.rs::execute_exec_request_with_after_spawn.
    spawned = []
    request = new_exec_request(
        (sys.executable, "-c", "print('sandboxing-ok')"),
        tmp_path,
        {},
        None,
        ExecExpiration.timeout_after(timedelta(seconds=5)),
        ExecCapturePolicy.FULL_BUFFER,
        SandboxType.NONE,
        WindowsSandboxLevel.DISABLED,
        False,
        PermissionProfile.disabled(),
        None,
    )

    output = asyncio.run(
        execute_exec_request_with_after_spawn(
            request,
            after_spawn=lambda: spawned.append(True),
        )
    )

    assert spawned == [True]
    assert output.exit_code == 0
    assert output.stdout.text.strip() == "sandboxing-ok"


def test_execute_exec_request_streams_stdout_and_stderr_chunks(tmp_path):
    # Rust source: codex-rs/core/src/exec.rs::read_output via sandboxing execute path.
    chunks = []
    request = new_exec_request(
        (
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        ),
        tmp_path,
        {},
        None,
        ExecExpiration.timeout_after(timedelta(seconds=5)),
        ExecCapturePolicy.FULL_BUFFER,
        SandboxType.NONE,
        WindowsSandboxLevel.DISABLED,
        False,
        PermissionProfile.disabled(),
        None,
    )

    output = asyncio.run(
        execute_exec_request_with_after_spawn(
            request,
            stdout_stream=lambda chunk, is_stderr: chunks.append((chunk, is_stderr)),
        )
    )

    assert output.exit_code == 0
    assert output.stdout.text.strip() == "out"
    assert output.stderr.text.strip() == "err"
    assert (b"out\r\n" if sys.platform == "win32" else b"out\n", False) in chunks
    assert (b"err\r\n" if sys.platform == "win32" else b"err\n", True) in chunks


def test_execute_exec_request_rejects_non_callable_stdout_stream(tmp_path):
    request = new_exec_request(
        (sys.executable, "-c", "print('ok')"),
        tmp_path,
        {},
        None,
        ExecExpiration.default_timeout(),
        ExecCapturePolicy.FULL_BUFFER,
        SandboxType.NONE,
        WindowsSandboxLevel.DISABLED,
        False,
        PermissionProfile.disabled(),
        None,
    )

    with pytest.raises(TypeError, match="stdout_stream"):
        asyncio.run(execute_exec_request_with_after_spawn(request, stdout_stream=object()))
