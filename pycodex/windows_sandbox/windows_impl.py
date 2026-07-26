"""Windows implementation selected by the crate root.

Rust owner: inline module ``codex-windows-sandbox::windows_impl``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .process import create_process_as_user_capture
from .resolved_permissions import ResolvedWindowsSandboxPermissions
from .sandbox_utils import ensure_codex_home_exists
from .setup import sandbox_dir
from .spawn_prep import (
    SpawnContext,
    WindowsSandboxSpawnPrepError,
    apply_legacy_session_acl_rules,
    prepare_legacy_session_security,
    prepare_legacy_spawn_context,
)


@dataclass(frozen=True)
class CaptureResult:
    exit_code: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    cancelled: bool = False


def run_windows_sandbox_capture(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: list[str] | tuple[str, ...],
    cwd: str | Path,
    env_map: dict[str, str],
    timeout_ms: int | None,
    use_private_desktop: bool,
    *,
    is_cancelled: Any = None,
) -> CaptureResult:
    return run_windows_sandbox_capture_with_filesystem_overrides(
        permission_profile,
        permission_profile_cwd,
        codex_home,
        command,
        cwd,
        env_map,
        timeout_ms,
        (),
        (),
        use_private_desktop,
        is_cancelled=is_cancelled,
    )


def run_windows_sandbox_capture_with_filesystem_overrides(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: list[str] | tuple[str, ...],
    cwd: str | Path,
    env_map: dict[str, str],
    timeout_ms: int | None,
    additional_deny_read_paths: list[str | Path] | tuple[str | Path, ...],
    additional_deny_write_paths: list[str | Path] | tuple[str | Path, ...],
    use_private_desktop: bool,
    *,
    is_cancelled: Any = None,
) -> CaptureResult:
    if additional_deny_read_paths:
        raise WindowsSandboxSpawnPrepError(
            "deny-read overrides require the elevated Windows sandbox backend"
        )
    prepared_env = dict(env_map)
    context = prepare_legacy_spawn_context(
        permission_profile,
        permission_profile_cwd,
        codex_home,
        cwd,
        prepared_env,
        command,
    )
    if not context.permissions.has_full_disk_read_access():
        raise WindowsSandboxSpawnPrepError(
            "Restricted read-only access requires the elevated Windows sandbox backend"
        )
    with prepare_legacy_session_security(
        context,
        codex_home,
        prepared_env,
    ) as security:
        apply_legacy_session_acl_rules(
            context,
            codex_home,
            prepared_env,
            security,
            additional_deny_write_paths=additional_deny_write_paths,
        )
        result = create_process_as_user_capture(
            security.token,
            command,
            cwd,
            prepared_env,
            timeout_ms,
            use_private_desktop=use_private_desktop,
            is_cancelled=is_cancelled,
        )
    return CaptureResult(
        result.exit_code,
        result.stdout,
        result.stderr,
        result.timed_out,
        result.cancelled,
    )


def run_windows_sandbox_legacy_preflight(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    cwd: str | Path,
    env_map: dict[str, str],
) -> None:
    try:
        permissions = (
            ResolvedWindowsSandboxPermissions
            .try_from_permission_profile_for_cwd(
                permission_profile,
                permission_profile_cwd,
            )
        )
    except (TypeError, ValueError):
        return
    if not permissions.uses_write_capabilities_for_cwd(cwd, env_map):
        return
    ensure_codex_home_exists(codex_home)
    logs = sandbox_dir(codex_home)
    logs.mkdir(parents=True, exist_ok=True)
    context = SpawnContext(permissions, Path(cwd), logs, True)
    with prepare_legacy_session_security(
        context,
        codex_home,
        env_map,
    ) as security:
        apply_legacy_session_acl_rules(
            context,
            codex_home,
            env_map,
            security,
        )


__all__ = [
    "CaptureResult",
    "run_windows_sandbox_capture",
    "run_windows_sandbox_capture_with_filesystem_overrides",
    "run_windows_sandbox_legacy_preflight",
]
