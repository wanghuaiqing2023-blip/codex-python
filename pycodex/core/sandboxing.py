"""Core sandboxing adapter surface.

Rust source: ``codex/codex-rs/core/src/sandboxing/mod.rs``.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from pycodex.protocol import (
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPermissions,
    SandboxPolicy,
    WindowsSandboxLevel,
)

from .exec import (
    ExecParams,
    ExecCapturePolicy,
    ExecExpiration,
    ExecRequest,
    WindowsSandboxFilesystemOverrides,
    apply_network_to_env,
    exec_params_from_request,
    finalize_exec_result,
    resolve_windows_elevated_filesystem_overrides,
    resolve_windows_restricted_token_filesystem_overrides,
    run_raw_exec_subprocess,
    select_process_exec_tool_sandbox_type,
    windows_sandbox_uses_elevated_backend,
)
from .sandbox_tags import SandboxType
from .spawn import CODEX_SANDBOX_ENV_VAR, CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR
from .unified_exec import ExecServerEnvConfig


@dataclass(frozen=True, slots=True)
class ExecOptions:
    expiration: ExecExpiration
    capture_policy: ExecCapturePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.expiration, ExecExpiration):
            raise TypeError("expiration must be an ExecExpiration")
        if not isinstance(self.capture_policy, ExecCapturePolicy):
            object.__setattr__(self, "capture_policy", ExecCapturePolicy(self.capture_policy))


@dataclass(frozen=True, slots=True)
class SandboxExecRequest:
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    network: Any = None
    sandbox: SandboxType = SandboxType.NONE
    windows_sandbox_level: WindowsSandboxLevel | str = WindowsSandboxLevel.DISABLED
    windows_sandbox_private_desktop: bool = False
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.read_only)
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    network_sandbox_policy: NetworkSandboxPolicy | str = NetworkSandboxPolicy.RESTRICTED
    arg0: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, (str, bytes)) or not isinstance(self.command, tuple | list):
            raise TypeError("command must be a sequence of strings")
        command = tuple(self.command)
        if not all(isinstance(part, str) for part in command):
            raise TypeError("command must contain strings")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.env, Mapping):
            raise TypeError("env must be a mapping")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in self.env.items()):
            raise TypeError("env must contain string keys and values")
        object.__setattr__(self, "env", dict(self.env))
        if not isinstance(self.sandbox, SandboxType):
            object.__setattr__(self, "sandbox", SandboxType(str(self.sandbox)))
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(
                self,
                "windows_sandbox_level",
                WindowsSandboxLevel.parse(str(self.windows_sandbox_level)),
            )
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be a PermissionProfile")
        if self.file_system_sandbox_policy is None:
            file_system_sandbox_policy = self.permission_profile.file_system_sandbox_policy()
            object.__setattr__(self, "file_system_sandbox_policy", file_system_sandbox_policy)
        elif not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy or None")
        if not isinstance(self.network_sandbox_policy, NetworkSandboxPolicy):
            object.__setattr__(
                self,
                "network_sandbox_policy",
                NetworkSandboxPolicy.parse(str(self.network_sandbox_policy)),
            )
        if self.arg0 is not None and not isinstance(self.arg0, str):
            raise TypeError("arg0 must be a string or None")


def new_exec_request(
    command: tuple[str, ...] | list[str],
    cwd: Path | str,
    env: Mapping[str, str],
    network: Any,
    expiration: ExecExpiration,
    capture_policy: ExecCapturePolicy,
    sandbox: SandboxType | str,
    windows_sandbox_level: WindowsSandboxLevel | str,
    windows_sandbox_private_desktop: bool,
    permission_profile: PermissionProfile,
    arg0: str | None,
) -> ExecRequest:
    """Mirror ``ExecRequest::new`` from Rust ``core::sandboxing``."""

    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    file_system_sandbox_policy, network_sandbox_policy = permission_profile.to_runtime_permissions()
    return ExecRequest(
        command=tuple(command),
        cwd=Path(cwd),
        env=dict(env),
        network=network,
        expiration=expiration,
        capture_policy=capture_policy,
        sandbox=sandbox,
        windows_sandbox_policy_cwd=Path(cwd),
        windows_sandbox_level=windows_sandbox_level,
        windows_sandbox_private_desktop=windows_sandbox_private_desktop,
        permission_profile=permission_profile,
        file_system_sandbox_policy=file_system_sandbox_policy,
        network_sandbox_policy=network_sandbox_policy,
        windows_sandbox_filesystem_overrides=None,
        arg0=arg0,
        exec_server_env_config=None,
    )


def compatibility_sandbox_policy(exec_request: ExecRequest) -> SandboxPolicy:
    """Return the legacy sandbox policy used for compatibility callers."""

    if not isinstance(exec_request, ExecRequest):
        raise TypeError("exec_request must be an ExecRequest")
    permission_profile = exec_request.permission_profile
    if not isinstance(permission_profile, PermissionProfile):
        permission_profile = PermissionProfile.from_runtime_permissions(
            exec_request.file_system_sandbox_policy or FileSystemSandboxPolicy.default(),
            exec_request.network_sandbox_policy,
        )
    return compatibility_sandbox_policy_for_permission_profile(
        permission_profile,
        exec_request.file_system_sandbox_policy or permission_profile.file_system_sandbox_policy(),
        exec_request.network_sandbox_policy,
        exec_request.windows_sandbox_policy_cwd,
    )


def compatibility_sandbox_policy_for_permission_profile(
    permissions: PermissionProfile,
    file_system_policy: FileSystemSandboxPolicy,
    network_policy: NetworkSandboxPolicy,
    cwd: Path | str,
) -> SandboxPolicy:
    """Python counterpart to ``codex-sandboxing`` compatibility conversion."""

    if not isinstance(permissions, PermissionProfile):
        raise TypeError("permissions must be a PermissionProfile")
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be a FileSystemSandboxPolicy")
    if not isinstance(network_policy, NetworkSandboxPolicy):
        network_policy = NetworkSandboxPolicy.parse(str(network_policy))
    try:
        return permissions.to_legacy_sandbox_policy(cwd)
    except ValueError:
        return _compatibility_workspace_write_policy(file_system_policy, network_policy, cwd)


def from_sandbox_exec_request(
    request: SandboxExecRequest,
    options: ExecOptions,
    windows_sandbox_policy_cwd: Path | str,
) -> ExecRequest:
    """Mirror Rust ``ExecRequest::from_sandbox_exec_request``."""

    if not isinstance(request, SandboxExecRequest):
        raise TypeError("request must be a SandboxExecRequest")
    if not isinstance(options, ExecOptions):
        raise TypeError("options must be ExecOptions")
    env = dict(request.env)
    if not request.network_sandbox_policy.is_enabled():
        env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "1"
    if sys.platform == "darwin" and request.sandbox is SandboxType.MACOS_SEATBELT:
        env[CODEX_SANDBOX_ENV_VAR] = "seatbelt"

    return ExecRequest(
        command=request.command,
        cwd=request.cwd,
        env=env,
        network=request.network,
        expiration=options.expiration,
        capture_policy=options.capture_policy,
        sandbox=request.sandbox,
        windows_sandbox_policy_cwd=Path(windows_sandbox_policy_cwd),
        windows_sandbox_level=request.windows_sandbox_level,
        windows_sandbox_private_desktop=request.windows_sandbox_private_desktop,
        permission_profile=request.permission_profile,
        file_system_sandbox_policy=request.file_system_sandbox_policy,
        network_sandbox_policy=request.network_sandbox_policy,
        windows_sandbox_filesystem_overrides=None,
        arg0=request.arg0,
        exec_server_env_config=None,
    )


def _transform_to_sandbox_exec_request(
    *,
    params: ExecParams,
    permission_profile: PermissionProfile,
    sandbox_type: SandboxType | str,
    env: Mapping[str, str],
    enforce_managed_network: bool,
    sandbox_cwd: Path,
    codex_linux_sandbox_exe: Path | str | None,
    use_legacy_landlock: bool,
    sandbox_manager: Any = None,
) -> SandboxExecRequest:
    """Return the sandbox-transformed request for ``ExecParams``.

    Rust source: ``codex-rs/core/src/exec.rs::build_exec_request`` delegates
    command rewriting to ``SandboxManager::transform`` before projecting the
    resulting ``SandboxExecRequest`` through ``sandboxing::ExecRequest``.
    Python keeps that seam: when a sandbox manager is supplied, this helper
    calls its ``transform`` method; otherwise it constructs the selected
    sandbox request directly from the already resolved policies.
    """

    windows_sandbox_level = params.windows_sandbox_level or WindowsSandboxLevel.DISABLED
    windows_private_desktop = bool(params.windows_sandbox_private_desktop)
    if sandbox_manager is not None:
        transform = getattr(sandbox_manager, "transform", None)
        if not callable(transform):
            raise TypeError("sandbox_manager must expose a callable transform")
        command = {
            "program": params.command[0],
            "args": tuple(params.command[1:]),
            "cwd": sandbox_cwd,
            "env": dict(env),
            "additional_permissions": None,
        }
        transformed = transform(
            {
                "command": command,
                "permissions": permission_profile.to_runtime_permissions(),
                "sandbox": sandbox_type,
                "enforce_managed_network": enforce_managed_network,
                "network": params.network,
                "sandbox_policy_cwd": sandbox_cwd,
                "codex_linux_sandbox_exe": codex_linux_sandbox_exe,
                "use_legacy_landlock": use_legacy_landlock,
                "windows_sandbox_level": windows_sandbox_level,
                "windows_sandbox_private_desktop": windows_private_desktop,
                "permission_profile": permission_profile,
            }
        )
        if isinstance(transformed, SandboxExecRequest):
            return transformed
        if isinstance(transformed, Mapping):
            return SandboxExecRequest(
                command=tuple(str(part) for part in transformed["command"]),
                cwd=Path(transformed.get("cwd", sandbox_cwd)),
                env=dict(transformed.get("env", env)),
                network=transformed.get("network", params.network),
                sandbox=transformed.get("sandbox", sandbox_type),
                windows_sandbox_level=transformed.get("windows_sandbox_level", windows_sandbox_level),
                windows_sandbox_private_desktop=transformed.get(
                    "windows_sandbox_private_desktop",
                    windows_private_desktop,
                ),
                permission_profile=transformed.get("permission_profile", permission_profile),
                file_system_sandbox_policy=transformed.get(
                    "file_system_sandbox_policy",
                    permission_profile.file_system_policy,
                ),
                network_sandbox_policy=transformed.get(
                    "network_sandbox_policy",
                    permission_profile.network_policy,
                ),
                arg0=transformed.get("arg0"),
            )
        raise TypeError("sandbox_manager.transform must return SandboxExecRequest or mapping")

    return SandboxExecRequest(
        command=params.command,
        cwd=sandbox_cwd,
        env=dict(env),
        network=params.network,
        sandbox=sandbox_type,
        windows_sandbox_level=windows_sandbox_level,
        windows_sandbox_private_desktop=windows_private_desktop,
        permission_profile=permission_profile,
        file_system_sandbox_policy=permission_profile.file_system_policy,
        network_sandbox_policy=permission_profile.network_policy,
        arg0=None,
    )


def build_exec_request(
    params: ExecParams,
    permission_profile: PermissionProfile,
    sandbox_cwd: Path | str,
    codex_linux_sandbox_exe: Path | str | None = None,
    use_legacy_landlock: bool = False,
    *,
    sandbox_manager: Any = None,
) -> ExecRequest:
    """Build an ``ExecRequest`` from exec-tool params.

    Rust source: ``codex-rs/core/src/exec.rs::build_exec_request``. This
    bridges exec-tool params, permission profiles, sandbox selection, sandbox
    transformation, and the portable ``sandboxing::ExecRequest``.
    """

    if not isinstance(params, ExecParams):
        raise TypeError("params must be an ExecParams")
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    if not params.command:
        raise ValueError("command args are empty")

    sandbox_cwd_path = Path(sandbox_cwd)
    file_system_policy = permission_profile.file_system_policy
    network_policy = permission_profile.network_policy
    enforce_managed_network = params.network is not None
    env = apply_network_to_env(params.env, params.network) if enforce_managed_network else dict(params.env)
    windows_sandbox_level = params.windows_sandbox_level or WindowsSandboxLevel.DISABLED
    sandbox_type = select_process_exec_tool_sandbox_type(
        file_system_policy,
        network_policy,
        windows_sandbox_level,
        enforce_managed_network,
    )
    sandbox_request = _transform_to_sandbox_exec_request(
        params=params,
        permission_profile=permission_profile,
        sandbox_type=sandbox_type,
        env=env,
        enforce_managed_network=enforce_managed_network,
        sandbox_cwd=sandbox_cwd_path,
        codex_linux_sandbox_exe=codex_linux_sandbox_exe,
        use_legacy_landlock=use_legacy_landlock,
        sandbox_manager=sandbox_manager,
    )
    exec_request = from_sandbox_exec_request(
        sandbox_request,
        ExecOptions(params.expiration, params.capture_policy),
        sandbox_cwd_path,
    )

    sandbox_policy = compatibility_sandbox_policy(exec_request)
    use_windows_elevated_backend = windows_sandbox_uses_elevated_backend(
        exec_request.windows_sandbox_level,
        sandbox_policy.proxy_networking,
    )
    if use_windows_elevated_backend:
        overrides = resolve_windows_elevated_filesystem_overrides(
            exec_request.sandbox,
            sandbox_policy,
            exec_request.file_system_sandbox_policy,
            exec_request.network_sandbox_policy,
            sandbox_cwd_path,
            use_windows_elevated_backend,
        )
    else:
        overrides = resolve_windows_restricted_token_filesystem_overrides(
            exec_request.sandbox,
            sandbox_policy,
            exec_request.file_system_sandbox_policy,
            exec_request.network_sandbox_policy,
            sandbox_cwd_path,
            exec_request.windows_sandbox_level,
        )
    return replace(exec_request, windows_sandbox_filesystem_overrides=overrides)


async def process_exec_tool_call(
    params: ExecParams,
    permission_profile: PermissionProfile,
    sandbox_cwd: Path | str,
    codex_linux_sandbox_exe: Path | str | None = None,
    use_legacy_landlock: bool = False,
    stdout_stream: Any = None,
    *,
    sandbox_manager: Any = None,
) -> Any:
    """Process an exec-tool call through the sandboxing bridge.

    Rust source: ``codex-rs/core/src/exec.rs::process_exec_tool_call``.
    """

    exec_request = build_exec_request(
        params,
        permission_profile,
        sandbox_cwd,
        codex_linux_sandbox_exe,
        use_legacy_landlock,
        sandbox_manager=sandbox_manager,
    )
    return await execute_env(exec_request, stdout_stream)


async def execute_env(
    exec_request: ExecRequest,
    stdout_stream: Any = None,
) -> Any:
    return await execute_exec_request_with_after_spawn(exec_request, stdout_stream, None)


async def execute_exec_request_with_after_spawn(
    exec_request: ExecRequest,
    stdout_stream: Any = None,
    after_spawn: Callable[[], None] | None = None,
) -> Any:
    """Execute the non-sandbox Python subprocess path for an ``ExecRequest``."""

    if stdout_stream is not None and not callable(stdout_stream):
        raise TypeError("stdout_stream must be callable or None")
    started = time.monotonic()
    params = exec_params_from_request(exec_request)
    raw_output = await run_raw_exec_subprocess(
        params,
        exec_request.network_sandbox_policy,
        after_spawn=after_spawn,
        stdout_stream=stdout_stream,
    )
    return finalize_exec_result(
        raw_output,
        exec_request.sandbox.value,
        duration=_duration_since(started),
    )


def _compatibility_workspace_write_policy(
    file_system_policy: FileSystemSandboxPolicy,
    network_policy: NetworkSandboxPolicy,
    cwd: Path | str,
) -> SandboxPolicy:
    cwd_path = Path(cwd)
    writable_roots = tuple(
        root.root
        for root in file_system_policy.get_writable_roots_with_cwd(cwd_path)
        if root.root != cwd_path
    )
    tmpdir_writable = _path_is_writable_by_policy(file_system_policy, Path("/tmp"), cwd_path)
    slash_tmp_writable = Path("/tmp").is_absolute() and Path("/tmp").is_dir() and tmpdir_writable
    return SandboxPolicy.workspace_write(
        writable_roots,
        network_access=network_policy.is_enabled(),
        exclude_tmpdir_env_var=not tmpdir_writable,
        exclude_slash_tmp=not slash_tmp_writable,
    )


def _path_is_writable_by_policy(
    file_system_policy: FileSystemSandboxPolicy,
    path: Path,
    cwd: Path,
) -> bool:
    can_write = getattr(file_system_policy, "can_write_path_with_cwd", None)
    return bool(callable(can_write) and can_write(path, cwd))


def _duration_since(started: float) -> Any:
    from datetime import timedelta

    return timedelta(seconds=time.monotonic() - started)


__all__ = [
    "build_exec_request",
    "ExecOptions",
    "ExecParams",
    "ExecRequest",
    "ExecServerEnvConfig",
    "process_exec_tool_call",
    "SandboxExecRequest",
    "SandboxPermissions",
    "SandboxType",
    "WindowsSandboxFilesystemOverrides",
    "compatibility_sandbox_policy",
    "compatibility_sandbox_policy_for_permission_profile",
    "execute_env",
    "execute_exec_request_with_after_spawn",
    "from_sandbox_exec_request",
    "new_exec_request",
]
