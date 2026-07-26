"""Windows cfg branch for elevated permission-profile capture."""

from __future__ import annotations

import threading
from pathlib import Path

from ..cap import load_or_create_cap_sids, workspace_write_cap_sid_for_root
from ..env import (
    ensure_non_interactive_pager,
    inherit_path_env,
    normalize_null_device_env,
)
from ..identity import select_identity, setup_mismatch_reason
from ..process import ProcessCaptureResult as CaptureResult
from ..resolved_permissions import ResolvedWindowsSandboxPermissions
from ..sandbox_utils import ensure_codex_home_exists, inject_git_safe_directory
from ..setup import (
    SandboxNetworkIdentity,
    build_elevation_payload,
    effective_write_roots_for_permissions,
    is_elevated,
    run_setup_exe,
)
from ..unified_exec.backends.elevated import spawn_runner_popen
from . import ElevatedSandboxProfileCaptureRequest


def run_windows_sandbox_capture_for_permission_profile(
    request: ElevatedSandboxProfileCaptureRequest,
) -> CaptureResult:
    permissions = (
        ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
            request.permission_profile,
            request.permission_profile_cwd,
        )
    )
    environment = dict(request.env_map)
    normalize_null_device_env(environment)
    ensure_non_interactive_pager(environment)
    inherit_path_env(environment)
    inject_git_safe_directory(environment, request.cwd)
    ensure_codex_home_exists(request.codex_home / ".sandbox")

    identity_kind = SandboxNetworkIdentity.from_permissions(
        permissions,
        request.proxy_enforced,
    )
    common = dict(
        proxy_enforced=request.proxy_enforced,
        read_roots_override=request.read_roots_override,
        read_roots_include_platform_defaults=(
            request.read_roots_include_platform_defaults
        ),
        write_roots_override=request.write_roots_override,
        deny_read_paths=request.deny_read_paths_override,
        deny_write_paths=request.deny_write_paths_override,
    )
    if (
        setup_mismatch_reason(
            request.codex_home,
            identity_kind,
            environment,
        )
        is not None
    ):
        payload = build_elevation_payload(
            permissions,
            request.cwd,
            environment,
            request.codex_home,
            refresh_only=False,
            **common,
        )
        run_setup_exe(
            payload,
            needs_elevation=not is_elevated(),
            codex_home=payload.codex_home,
        )

    credentials = select_identity(identity_kind, request.codex_home)
    if credentials is None:
        raise RuntimeError(
            "Windows sandbox setup is missing or out of date; "
            "rerun the sandbox setup with elevation"
        )
    refresh = build_elevation_payload(
        permissions,
        request.cwd,
        environment,
        request.codex_home,
        refresh_only=True,
        **common,
    )
    run_setup_exe(
        refresh,
        needs_elevation=False,
        codex_home=refresh.codex_home,
    )

    process = spawn_runner_popen(
        credentials,
        request.command,
        request.cwd,
        environment,
        permission_profile=request.permission_profile,
        permission_profile_cwd=request.permission_profile_cwd,
        codex_home=request.codex_home,
        cap_sids=_capability_sid_texts(
            permissions,
            request.cwd,
            environment,
            request.codex_home,
        ),
        timeout_ms=request.timeout_ms,
        stdin_open=False,
        tty=False,
        merge_stderr=False,
        use_private_desktop=request.use_private_desktop,
    )
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_reader = threading.Thread(
        target=lambda: stdout_chunks.append(
            _read_process_stream(process, "stdout")
        ),
        daemon=True,
    )
    stderr_reader = threading.Thread(
        target=lambda: stderr_chunks.append(
            _read_process_stream(process, "stderr")
        ),
        daemon=True,
    )
    stdout_reader.start()
    stderr_reader.start()
    try:
        exit_code = process.wait()
        stdout_reader.join(5)
        stderr_reader.join(5)
        return CaptureResult(
            exit_code,
            b"".join(stdout_chunks),
            b"".join(stderr_chunks),
            process.timed_out,
            False,
        )
    finally:
        process.close()


def _read_process_stream(process: object, name: str) -> bytes:
    stream = getattr(process, name, None)
    read = getattr(stream, "read", None)
    if not callable(read):
        return b""
    value = read()
    return (
        value
        if isinstance(value, bytes)
        else str(value).encode("utf-8", errors="replace")
    )


def _capability_sid_texts(
    permissions: ResolvedWindowsSandboxPermissions,
    cwd: str | Path,
    env_map: dict[str, str],
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
    "CaptureResult",
    "run_windows_sandbox_capture_for_permission_profile",
]
