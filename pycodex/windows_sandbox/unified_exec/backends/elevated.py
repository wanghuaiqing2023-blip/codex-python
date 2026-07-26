"""Elevated unified-exec backend.

Rust owner: ``codex-windows-sandbox::unified_exec::backends::elevated``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from ...elevated.ipc_framed import SpawnRequest
from ...elevated.runner_client import spawn_runner_transport
from ...cap import load_or_create_cap_sids, workspace_write_cap_sid_for_root
from ...env import (
    ensure_non_interactive_pager,
    inherit_path_env,
    normalize_null_device_env,
)
from ...identity import SandboxCreds
from ...identity import select_identity, setup_mismatch_reason
from ...resolved_permissions import ResolvedWindowsSandboxPermissions
from ...sandbox_utils import inject_git_safe_directory
from ...setup import (
    SandboxNetworkIdentity,
    build_elevation_payload,
    effective_write_roots_for_permissions,
    is_elevated,
    run_setup_exe,
)
from .windows_common import RunnerBackedPopen, finish_driver_spawn


def spawn_runner_popen(
    credentials: SandboxCreds,
    command: Sequence[str],
    cwd: str | Path,
    env: Mapping[str, str],
    *,
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    cap_sids: Sequence[str],
    timeout_ms: int | None,
    stdin_open: bool,
    tty: bool,
    merge_stderr: bool = True,
    use_private_desktop: bool,
) -> RunnerBackedPopen:
    request = SpawnRequest(
        command=tuple(str(part) for part in command),
        cwd=Path(cwd),
        env={str(key): str(value) for key, value in env.items()},
        permission_profile=permission_profile,
        permission_profile_cwd=Path(permission_profile_cwd),
        codex_home=Path(codex_home) / ".sandbox",
        real_codex_home=Path(codex_home),
        cap_sids=tuple(cap_sids),
        timeout_ms=timeout_ms,
        stdin_open=stdin_open,
        tty=tty,
        use_private_desktop=use_private_desktop,
    )
    transport = spawn_runner_transport(
        codex_home,
        cwd,
        credentials,
        Path(codex_home) / ".sandbox",
        request,
    )
    return finish_driver_spawn(
        RunnerBackedPopen(
            transport,
            stdin_open=stdin_open,
            merge_stderr=merge_stderr,
            tty=tty,
        ),
        stdin_open,
    )


def spawn_windows_sandbox_session_elevated_for_permission_profile(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    timeout_ms: int | None,
    read_roots_override: Sequence[str | Path] | None,
    read_roots_include_platform_defaults: bool,
    write_roots_override: Sequence[str | Path] | None,
    deny_read_paths_override: Sequence[str | Path],
    deny_write_paths_override: Sequence[str | Path],
    tty: bool,
    stdin_open: bool,
    use_private_desktop: bool,
) -> RunnerBackedPopen:
    permissions = (
        ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
            permission_profile,
            permission_profile_cwd,
        )
    )
    environment = dict(env_map)
    normalize_null_device_env(environment)
    ensure_non_interactive_pager(environment)
    inherit_path_env(environment)
    inject_git_safe_directory(environment, cwd)
    identity_kind = SandboxNetworkIdentity.from_permissions(permissions, False)
    common = dict(
        read_roots_override=read_roots_override,
        read_roots_include_platform_defaults=(
            read_roots_include_platform_defaults
        ),
        write_roots_override=write_roots_override,
        deny_read_paths=deny_read_paths_override,
        deny_write_paths=deny_write_paths_override,
    )
    if (
        setup_mismatch_reason(codex_home, identity_kind, environment)
        is not None
    ):
        payload = build_elevation_payload(
            permissions,
            cwd,
            environment,
            codex_home,
            refresh_only=False,
            **common,
        )
        run_setup_exe(
            payload,
            needs_elevation=not is_elevated(),
            codex_home=payload.codex_home,
        )
    credentials = select_identity(identity_kind, codex_home)
    if credentials is None:
        raise RuntimeError(
            "Windows sandbox setup is missing or out of date"
        )
    refresh = build_elevation_payload(
        permissions,
        cwd,
        environment,
        codex_home,
        refresh_only=True,
        **common,
    )
    run_setup_exe(
        refresh,
        needs_elevation=False,
        codex_home=refresh.codex_home,
    )
    return spawn_runner_popen(
        credentials,
        command,
        cwd,
        environment,
        permission_profile=permission_profile,
        permission_profile_cwd=permission_profile_cwd,
        codex_home=codex_home,
        cap_sids=_capability_sid_texts(
            permissions,
            cwd,
            environment,
            codex_home,
        ),
        timeout_ms=timeout_ms,
        stdin_open=stdin_open,
        tty=tty,
        merge_stderr=True,
        use_private_desktop=use_private_desktop,
    )


def _capability_sid_texts(
    permissions: ResolvedWindowsSandboxPermissions,
    cwd: str | Path,
    env_map: Mapping[str, str],
    codex_home: str | Path,
) -> tuple[str, ...]:
    if not permissions.uses_write_capabilities_for_cwd(cwd, env_map):
        return (load_or_create_cap_sids(codex_home).readonly,)
    roots = effective_write_roots_for_permissions(
        permissions,
        cwd,
        env_map,
        codex_home,
    )
    values = tuple(
        workspace_write_cap_sid_for_root(codex_home, cwd, root)
        for root in roots
    )
    if not values:
        raise RuntimeError(
            "workspace-write sandbox has no writable root capability SIDs"
        )
    return values


__all__ = [
    "spawn_windows_sandbox_session_elevated_for_permission_profile",
]
