"""Python interface for Rust ``codex-windows-sandbox``."""

from __future__ import annotations

import os

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
from .deny_read_resolver import resolve_windows_deny_read_paths
from .path_normalization import canonicalize_path
from .winutil import quote_windows_arg, to_wide
from .workspace_acl import is_command_cwd_root
from .process import (
    NativeProcessPopen,
    PipeSpawnHandles,
    ProcessCaptureResult,
    StderrMode,
    StdinMode,
    WindowsSandboxProcessError,
    create_process_as_user_capture,
    create_process_as_user_popen,
    make_env_block,
)
from . import conpty, proc_thread_attr
from .conpty import ConptyInstance, spawn_conpty_process_as_user
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
from .setup_error import (
    SetupErrorCode,
    SetupErrorReport,
    SetupFailure,
    sanitize_setup_metric_tag_value,
)
from .wfp_setup import install_wfp_filters
from .elevated_impl import (
    ElevatedSandboxProfileCaptureRequest,
    run_windows_sandbox_capture_for_permission_profile as run_windows_sandbox_capture_for_permission_profile_elevated,
)
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
from .unified_exec import (
    spawn_windows_sandbox_session_elevated_for_permission_profile,
    spawn_windows_sandbox_session_legacy,
)

from . import stub, windows_impl

if os.name == "nt":
    from . import audit
    from .audit import apply_world_writable_scan_and_denies_for_permissions
    from .windows_impl import (
        CaptureResult,
        run_windows_sandbox_capture,
        run_windows_sandbox_capture_with_filesystem_overrides,
        run_windows_sandbox_legacy_preflight,
    )
else:
    from .stub import (
        CaptureResult,
        run_windows_sandbox_capture,
        run_windows_sandbox_legacy_preflight,
    )


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
    "install_wfp_filters",
    "load_or_create_cap_sids",
    "logon_user",
    "legacy_session_capability_roots",
    "make_env_block",
    "run_windows_sandbox_capture",
    "run_windows_sandbox_capture_for_permission_profile_elevated",
    "run_windows_sandbox_legacy_preflight",
    "spawn_windows_sandbox_session_elevated_for_permission_profile",
    "spawn_windows_sandbox_session_legacy",
    "spawn_conpty_process_as_user",
    "revoke_ace",
    "prepare_legacy_session_security",
    "prepare_legacy_spawn_context",
    "root_capability_sids",
    "sandbox_bin_dir",
    "sandbox_dir",
    "sandbox_secrets_dir",
    "sandbox_users_path",
    "sanitize_setup_metric_tag_value",
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

if os.name == "nt":
    __all__.extend(
        (
            "apply_world_writable_scan_and_denies_for_permissions",
            "run_windows_sandbox_capture_with_filesystem_overrides",
        )
    )
