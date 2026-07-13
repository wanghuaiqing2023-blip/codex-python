from __future__ import annotations

import io
import os
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.tools.sandboxing import SandboxAttempt
from pycodex.core.tools.runtimes import UnifiedExecRuntime
from pycodex.core.unified_exec import UnifiedExecError, UnifiedExecProcessManager
from pycodex.protocol import (
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    NetworkPermissions,
    PermissionProfile,
    WindowsSandboxLevel,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows sandbox routing")


class _CompletedPopen:
    def __init__(self, output: bytes = b"native-unified") -> None:
        self.stdin = None
        self.stdout = io.BytesIO(output)
        self.stderr = None
        self.returncode = 0

    def poll(self):
        return 0

    def terminate(self):
        raise AssertionError("completed process should not be terminated")


def _request(attempt: SandboxAttempt) -> SimpleNamespace:
    request = SimpleNamespace(
        command=("cmd.exe", "/c", "echo native-unified"),
        process_id=1000,
        yield_time_ms=1000,
        max_output_tokens=None,
        cwd=Path.cwd(),
        environment={},
        hook_command="echo native-unified",
        tty=False,
        truncation_policy=None,
    )
    request._sandbox_attempt = attempt
    return request


def _attempt(level: WindowsSandboxLevel) -> SandboxAttempt:
    return SandboxAttempt(
        sandbox=SandboxType.WINDOWS_RESTRICTED_TOKEN,
        permissions=PermissionProfile.read_only(),
        enforce_managed_network=False,
        manager=SimpleNamespace(transform=lambda *_args, **_kwargs: None),
        sandbox_cwd=Path.cwd(),
        windows_sandbox_level=level,
        windows_sandbox_private_desktop=True,
    )


def test_unified_exec_windows_attempt_uses_native_session_spawner(monkeypatch) -> None:
    import pycodex.windows_sandbox as windows_sandbox

    observed: dict[str, object] = {}

    def fake_spawn(*args, **kwargs):
        observed["args"] = args
        observed["kwargs"] = kwargs
        return _CompletedPopen()

    monkeypatch.setattr(windows_sandbox, "spawn_windows_sandbox_popen", fake_spawn)
    manager = UnifiedExecProcessManager()
    output = manager.exec_command(_request(_attempt(WindowsSandboxLevel.RESTRICTED_TOKEN)))
    assert b"native-unified" in output.raw_output
    assert observed["kwargs"]["stdin_open"] is False
    assert observed["kwargs"]["tty"] is False
    assert observed["kwargs"]["use_private_desktop"] is True


def test_unified_exec_windows_attempt_with_disabled_level_never_falls_back(monkeypatch) -> None:
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback")))
    manager = UnifiedExecProcessManager()
    with pytest.raises(UnifiedExecError, match="refusing unrestricted fallback"):
        manager.exec_command(_request(_attempt(WindowsSandboxLevel.DISABLED)))


def test_unified_runtime_projects_additional_permissions_into_native_attempt() -> None:
    captured: dict[str, object] = {}

    class Manager:
        def exec_command(self, request):
            captured["attempt"] = request._sandbox_attempt
            return "ok"

    manager_request = SimpleNamespace()
    runtime = UnifiedExecRuntime(Manager(), manager_request)
    req = SimpleNamespace(
        additional_permissions=AdditionalPermissionProfile(
            network=NetworkPermissions(enabled=True)
        )
    )
    result = asyncio.run(runtime.run(req, _attempt(WindowsSandboxLevel.RESTRICTED_TOKEN), None))
    assert result == "ok"
    effective = captured["attempt"].permissions
    assert effective.network_sandbox_policy().is_enabled()


def test_unified_exec_forwards_effective_deny_paths_to_native_spawner(monkeypatch, tmp_path: Path) -> None:
    # Rust owners: core::unified_exec::process_manager and windows-sandbox::spawn_prep.
    import pycodex.windows_sandbox.elevated as elevated

    denied = tmp_path / "secret"
    profile = PermissionProfile.read_only()
    additional = AdditionalPermissionProfile(
        file_system=FileSystemPermissions(
            (FileSystemSandboxEntry(FileSystemPath.explicit_path(denied), FileSystemAccessMode.DENY),)
        )
    )
    observed: dict[str, object] = {}

    def fake_spawn(*args, **kwargs):
        observed.update(kwargs)
        return _CompletedPopen()

    monkeypatch.setattr(elevated, "spawn_elevated_popen", fake_spawn)
    attempt = _attempt(WindowsSandboxLevel.ELEVATED)
    attempt = SandboxAttempt(
        sandbox=attempt.sandbox,
        permissions=profile,
        enforce_managed_network=attempt.enforce_managed_network,
        manager=attempt.manager,
        sandbox_cwd=tmp_path,
        windows_sandbox_level=attempt.windows_sandbox_level,
        windows_sandbox_private_desktop=attempt.windows_sandbox_private_desktop,
    )
    request = _request(attempt)
    runtime = UnifiedExecRuntime(UnifiedExecProcessManager(), request)
    req = SimpleNamespace(additional_permissions=additional)

    asyncio.run(runtime.run(req, attempt, None))

    assert observed["additional_deny_read_paths"] == (denied.resolve(),)
