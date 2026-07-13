"""Python interface for Rust ``codex-windows-sandbox``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .acl import (
    WRITE_ALLOW_MASK,
    WindowsSandboxAclError,
    add_allow_ace,
    add_deny_read_ace,
    add_deny_write_ace,
    ensure_allow_mask_aces,
    ensure_allow_write_aces,
    path_mask_allows,
    revoke_ace,
)
from .cap import (
    CapSids,
    load_or_create_cap_sids,
    workspace_cap_sid_for_cwd,
    workspace_write_cap_sid_for_root,
    workspace_write_root_contains_path,
    workspace_write_root_overlaps_path,
    workspace_write_root_specificity,
    writable_root_cap_sid_for_path,
)
from .desktop import LaunchDesktop, WindowsSandboxDesktopError
from .path_normalization import canonicalize_path
from .process import (
    ConptyInstance,
    NativeProcessPopen,
    PipeSpawnHandles,
    ProcessCaptureResult,
    StderrMode,
    StdinMode,
    WindowsSandboxProcessError,
    create_process_as_user_capture,
    create_process_as_user_conpty_popen,
    create_process_as_user_popen,
    make_env_block,
)
from .resolved_permissions import (
    ResolvedWindowsSandboxPermissions,
    WindowsSandboxPermissionError,
    WindowsSandboxTokenMode,
    WindowsWritableRoot,
    token_mode_for_permission_profile,
)
from .setup import (
    SandboxSetupRequest,
    SETUP_VERSION,
    SetupRootOverrides,
    effective_write_roots_for_permissions,
    gather_write_roots_for_permissions,
    sandbox_bin_dir,
    sandbox_dir,
    sandbox_secrets_dir,
    sandbox_users_path,
    setup_marker_path,
)
from .setup_error import SetupErrorCode, SetupErrorReport, SetupFailure
from .elevated import ElevatedSandboxProfileCaptureRequest, run_elevated_capture
from .logging import (
    current_log_file_path,
    current_log_file_path_for_codex_home,
    log_file_path_for_utc_date,
    log_note,
    log_writer,
)
from .spawn_prep import (
    LegacySessionSecurity,
    RootCapabilitySid,
    SpawnContext,
    SpawnPrepOptions,
    WindowsSandboxSpawnPrepError,
    apply_legacy_session_acl_rules,
    legacy_session_capability_roots,
    prepare_legacy_session_security,
    prepare_legacy_spawn_context,
    root_capability_sids,
)
from .token import (
    LocalSid,
    WinHandle,
    WindowsSandboxTokenError,
    create_readonly_token_with_caps_and_user_from,
    create_readonly_token_with_caps_from,
    create_workspace_write_token_with_caps_and_user_from,
    create_workspace_write_token_with_caps_from,
    get_current_token_for_restriction,
    get_logon_sid_bytes,
    is_token_restricted,
    logon_user,
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
    with prepare_legacy_session_security(context, codex_home, prepared_env) as security:
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
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        permission_profile,
        permission_profile_cwd,
    )
    if not permissions.uses_write_capabilities_for_cwd(cwd, env_map):
        return
    logs = sandbox_dir(codex_home)
    logs.mkdir(parents=True, exist_ok=True)
    context = SpawnContext(permissions, Path(cwd), logs, True)
    with prepare_legacy_session_security(context, codex_home, env_map) as security:
        apply_legacy_session_acl_rules(context, codex_home, env_map, security)


def spawn_windows_sandbox_popen(
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    command: list[str] | tuple[str, ...],
    cwd: str | Path,
    env_map: dict[str, str],
    *,
    stdin_open: bool,
    tty: bool = False,
    merge_stderr: bool = True,
    use_private_desktop: bool,
    additional_deny_read_paths: tuple[str | Path, ...] = (),
    additional_deny_write_paths: tuple[str | Path, ...] = (),
) -> NativeProcessPopen:
    if additional_deny_read_paths:
        raise WindowsSandboxSpawnPrepError("deny-read overrides require the elevated Windows sandbox backend")
    prepared_env = dict(env_map)
    context = prepare_legacy_spawn_context(
        permission_profile, permission_profile_cwd, codex_home, cwd, prepared_env, command
    )
    if not context.permissions.has_full_disk_read_access():
        raise WindowsSandboxSpawnPrepError("Restricted read-only access requires the elevated Windows sandbox backend")
    with prepare_legacy_session_security(context, codex_home, prepared_env) as security:
        apply_legacy_session_acl_rules(
            context,
            codex_home,
            prepared_env,
            security,
            additional_deny_write_paths=additional_deny_write_paths,
        )
        return create_process_as_user_popen(
            security.token,
            command,
            cwd,
            prepared_env,
            stdin_open=stdin_open,
            tty=tty,
            merge_stderr=merge_stderr,
            use_private_desktop=use_private_desktop,
        )


def resolve_windows_deny_read_paths(file_system_sandbox_policy: Any, cwd: str | Path) -> list[Path]:
    if hasattr(file_system_sandbox_policy, "get_unreadable_roots_with_cwd"):
        return [Path(path) for path in file_system_sandbox_policy.get_unreadable_roots_with_cwd(Path(cwd))]
    return []


def quote_windows_arg(arg: str) -> str:
    if not arg or any(ch.isspace() or ch == '"' for ch in arg):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def to_wide(value: str) -> list[int]:
    return [*value.encode("utf-16-le"), 0, 0]


def sanitize_setup_metric_tag_value(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


is_command_cwd_root = lambda command_cwd, root: Path(command_cwd) == Path(root)


__all__ = [
    "CaptureResult",
    "CapSids",
    "ConptyInstance",
    "LegacySessionSecurity",
    "ElevatedSandboxProfileCaptureRequest",
    "LocalSid",
    "LaunchDesktop",
    "ProcessCaptureResult",
    "NativeProcessPopen",
    "PipeSpawnHandles",
    "RootCapabilitySid",
    "SETUP_VERSION",
    "SandboxSetupRequest",
    "SetupErrorCode",
    "SetupErrorReport",
    "SetupFailure",
    "SetupRootOverrides",
    "SpawnContext",
    "SpawnPrepOptions",
    "StderrMode",
    "StdinMode",
    "ResolvedWindowsSandboxPermissions",
    "WinHandle",
    "WindowsSandboxPermissionError",
    "WindowsSandboxDesktopError",
    "WindowsSandboxAclError",
    "WindowsSandboxProcessError",
    "WindowsSandboxSpawnPrepError",
    "WindowsSandboxTokenMode",
    "WindowsSandboxTokenError",
    "WindowsWritableRoot",
    "canonicalize_path",
    "add_allow_ace",
    "add_deny_read_ace",
    "add_deny_write_ace",
    "apply_legacy_session_acl_rules",
    "create_readonly_token_with_caps_from",
    "create_readonly_token_with_caps_and_user_from",
    "create_process_as_user_capture",
    "create_process_as_user_conpty_popen",
    "create_process_as_user_popen",
    "create_workspace_write_token_with_caps_from",
    "create_workspace_write_token_with_caps_and_user_from",
    "ensure_allow_mask_aces",
    "ensure_allow_write_aces",
    "path_mask_allows",
    "effective_write_roots_for_permissions",
    "gather_write_roots_for_permissions",
    "get_current_token_for_restriction",
    "get_logon_sid_bytes",
    "is_token_restricted",
    "load_or_create_cap_sids",
    "logon_user",
    "legacy_session_capability_roots",
    "make_env_block",
    "run_windows_sandbox_capture",
    "run_elevated_capture",
    "run_windows_sandbox_capture_with_filesystem_overrides",
    "run_windows_sandbox_legacy_preflight",
    "spawn_windows_sandbox_popen",
    "revoke_ace",
    "prepare_legacy_session_security",
    "prepare_legacy_spawn_context",
    "root_capability_sids",
    "sandbox_bin_dir",
    "sandbox_dir",
    "sandbox_secrets_dir",
    "sandbox_users_path",
    "setup_marker_path",
    "token_mode_for_permission_profile",
    "workspace_cap_sid_for_cwd",
    "workspace_write_cap_sid_for_root",
    "workspace_write_root_contains_path",
    "workspace_write_root_overlaps_path",
    "workspace_write_root_specificity",
    "writable_root_cap_sid_for_path",
    "WRITE_ALLOW_MASK",
]
