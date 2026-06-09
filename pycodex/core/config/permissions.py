"""Permission profile helpers ported from ``codex-core`` config.

This module tracks the pure helper surface from
``codex/codex-rs/core/src/config/permissions.rs``.  Full TOML profile
inheritance and filesystem profile compilation remain separate config slices.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxPolicy,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    PermissionProfile,
    WindowsSandboxLevel,
    project_roots_glob_pattern,
)
from pycodex.network_proxy import (
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
)

BUILT_IN_READ_ONLY_PROFILE = BUILT_IN_PERMISSION_PROFILE_READ_ONLY
BUILT_IN_WORKSPACE_PROFILE = BUILT_IN_PERMISSION_PROFILE_WORKSPACE
BUILT_IN_DANGER_FULL_ACCESS_PROFILE = BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS

JsonValue = Any


@dataclass(frozen=True)
class ProjectTrust:
    """Tiny ProjectConfig-compatible trust snapshot used by pure helpers."""

    trusted: bool = False
    untrusted: bool = False

    def is_trusted(self) -> bool:
        return self.trusted

    def is_untrusted(self) -> bool:
        return self.untrusted


@dataclass(frozen=True)
class SandboxWorkspaceWrite:
    """Subset of Rust ``SandboxWorkspaceWrite`` used by built-in profiles."""

    writable_roots: tuple[Path, ...] = ()
    network_access: bool = False
    exclude_tmpdir_env_var: bool = False
    exclude_slash_tmp: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "writable_roots", tuple(Path(path) for path in self.writable_roots))
        if not isinstance(self.network_access, bool):
            raise TypeError("network_access must be a bool")
        if not isinstance(self.exclude_tmpdir_env_var, bool):
            raise TypeError("exclude_tmpdir_env_var must be a bool")
        if not isinstance(self.exclude_slash_tmp, bool):
            raise TypeError("exclude_slash_tmp must be a bool")


def default_builtin_permission_profile_name(
    active_project: Any,
    windows_sandbox_level: WindowsSandboxLevel | str,
) -> str:
    """Return Rust's default built-in profile id for the project/platform state."""

    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))

    is_known_project = bool(_call_or_attr(active_project, "is_trusted")) or bool(
        _call_or_attr(active_project, "is_untrusted")
    )
    windows_without_sandbox = (
        sys.platform == "win32" and windows_sandbox_level is WindowsSandboxLevel.DISABLED
    )
    if is_known_project and not windows_without_sandbox:
        return BUILT_IN_WORKSPACE_PROFILE
    return BUILT_IN_READ_ONLY_PROFILE


def is_builtin_permission_profile_name(profile_name: str) -> bool:
    if not isinstance(profile_name, str):
        raise TypeError("profile_name must be a string")
    return profile_name in {
        BUILT_IN_READ_ONLY_PROFILE,
        BUILT_IN_WORKSPACE_PROFILE,
        BUILT_IN_DANGER_FULL_ACCESS_PROFILE,
    }


def builtin_permission_profile(
    profile_name: str,
    workspace_write: SandboxWorkspaceWrite | JsonValue | None = None,
) -> PermissionProfile | None:
    if not isinstance(profile_name, str):
        raise TypeError("profile_name must be a string")
    if profile_name == BUILT_IN_READ_ONLY_PROFILE:
        return PermissionProfile.read_only()
    if profile_name == BUILT_IN_WORKSPACE_PROFILE:
        if workspace_write is None:
            return PermissionProfile.workspace_write()
        workspace_write = _workspace_write_from_value(workspace_write)
        network = (
            NetworkSandboxPolicy.ENABLED
            if workspace_write.network_access
            else NetworkSandboxPolicy.RESTRICTED
        )
        return PermissionProfile.workspace_write(
            (),
            network,
            workspace_write.exclude_tmpdir_env_var,
            workspace_write.exclude_slash_tmp,
        )
    if profile_name == BUILT_IN_DANGER_FULL_ACCESS_PROFILE:
        return PermissionProfile.disabled()
    return None


def reject_unknown_builtin_permission_profile(profile_name: str) -> None:
    if not isinstance(profile_name, str):
        raise TypeError("profile_name must be a string")
    if profile_name.startswith(":"):
        raise ValueError(
            f"default_permissions refers to unknown built-in profile `{profile_name}`"
        )


def validate_user_permission_profile_names(permissions: JsonValue | None) -> None:
    if permissions is None:
        return
    for profile_name in _permissions_entries(permissions):
        if profile_name.startswith(":"):
            raise ValueError(
                f"permissions profile `{profile_name}` uses a reserved built-in profile prefix"
            )


def compile_permission_profile_selection(
    permissions: JsonValue | None,
    profile_name: str,
    workspace_write: SandboxWorkspaceWrite | JsonValue | None = None,
    policy_cwd: Path | str | None = None,
    startup_warnings: list[str] | None = None,
) -> tuple[FileSystemSandboxPolicy, NetworkSandboxPolicy]:
    """Compile built-in profile selections to runtime policies.

    Custom TOML profile compilation intentionally remains deferred; this helper
    preserves the Rust built-in fast path and its error for missing `[permissions]`.
    """

    warnings = startup_warnings if startup_warnings is not None else []
    cwd = Path("." if policy_cwd is None else policy_cwd)
    builtin = builtin_permission_profile(profile_name, workspace_write)
    if builtin is not None:
        return builtin.to_runtime_permissions()
    reject_unknown_builtin_permission_profile(profile_name)
    if permissions is None:
        raise ValueError("default_permissions requires a `[permissions]` table")
    return compile_permission_profile(permissions, profile_name, cwd, warnings)


def resolve_permission_profile(permissions: JsonValue, profile_name: str) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    entries = _permissions_entries(permissions)
    return _resolve_permission_profile(entries, profile_name, ())


def compile_permission_profile(
    permissions: JsonValue,
    profile_name: str,
    policy_cwd: Path | str,
    startup_warnings: list[str] | None = None,
) -> tuple[FileSystemSandboxPolicy, NetworkSandboxPolicy]:
    warnings = startup_warnings if startup_warnings is not None else []
    profile, inherited_profile_names = resolve_permission_profile(permissions, profile_name)
    base_permissions = None
    for name in inherited_profile_names:
        if name == BUILT_IN_READ_ONLY_PROFILE:
            base_permissions = PermissionProfile.read_only().to_runtime_permissions()
            break
        if name == BUILT_IN_WORKSPACE_PROFILE:
            base_permissions = PermissionProfile.workspace_write().to_runtime_permissions()
            break
    if base_permissions is None:
        file_system_sandbox_policy = FileSystemSandboxPolicy.restricted(())
        base_network_sandbox_policy = NetworkSandboxPolicy.RESTRICTED
    else:
        file_system_sandbox_policy, base_network_sandbox_policy = base_permissions

    filesystem = profile.get("filesystem")
    if filesystem is not None:
        entries = _filesystem_entries(filesystem)
        if not entries and not file_system_sandbox_policy.entries:
            _push_missing_filesystem_entries_warning(warnings, profile_name)
        else:
            if sys.platform != "darwin":
                for pattern in unsupported_read_write_glob_paths(filesystem):
                    warnings.append(
                        f"Filesystem glob `{pattern}` uses `read` or `write` access, which is not fully supported by this platform's sandboxing. Use an exact path or trailing `/**` subtree rule instead. `deny` globs are supported."
                    )
                for pattern in unbounded_unreadable_globstar_paths(filesystem):
                    warnings.append(
                        f"Filesystem deny-read glob `{pattern}` uses `**`. Non-macOS sandboxing does not support unbounded `**` natively; set `glob_scan_max_depth` in this filesystem profile to cap Linux glob expansion and silence this warning, or enumerate explicit depths such as `*.env`, `*/*.env`, and `*/*/*.env`."
                    )
            compiled_entries = list(file_system_sandbox_policy.entries)
            for path, permission in entries.items():
                compiled_entries.extend(
                    compile_filesystem_permission(path, permission, policy_cwd, warnings)
                )
            file_system_sandbox_policy = FileSystemSandboxPolicy(
                kind=file_system_sandbox_policy.kind,
                entries=tuple(compiled_entries),
                glob_scan_max_depth=file_system_sandbox_policy.glob_scan_max_depth,
            )
    elif not file_system_sandbox_policy.entries:
        _push_missing_filesystem_entries_warning(warnings, profile_name)

    glob_scan_max_depth = validate_glob_scan_max_depth(
        _filesystem_glob_scan_max_depth(filesystem) if filesystem is not None else None
    )
    if glob_scan_max_depth is not None:
        file_system_sandbox_policy = FileSystemSandboxPolicy(
            kind=file_system_sandbox_policy.kind,
            entries=file_system_sandbox_policy.entries,
            glob_scan_max_depth=glob_scan_max_depth,
        )
    network_sandbox_policy = compile_network_sandbox_policy(
        profile.get("network"),
        base_network_sandbox_policy,
    )
    return file_system_sandbox_policy, network_sandbox_policy


def compile_network_sandbox_policy(
    network: JsonValue | None,
    base_network_sandbox_policy: NetworkSandboxPolicy,
) -> NetworkSandboxPolicy:
    if network is None:
        return base_network_sandbox_policy
    if not isinstance(network, dict):
        raise TypeError("network must be a mapping")
    enabled = network.get("enabled")
    if enabled is True:
        return NetworkSandboxPolicy.ENABLED
    if enabled is False:
        return NetworkSandboxPolicy.RESTRICTED
    return base_network_sandbox_policy


def network_proxy_config_from_profile_network(network: JsonValue | None) -> NetworkProxyConfig:
    config = NetworkProxyConfig()
    if network is not None:
        _apply_network_to_network_proxy_config(config, network)
    # Rust keeps profile network access as sandbox policy input only. Profile
    # proxy details may be carried forward, but they do not start managed proxy.
    config.network.enabled = False
    return config


def apply_network_proxy_feature_config(config: NetworkProxyConfig, feature_config: JsonValue) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    _apply_network_to_network_proxy_config(config, feature_config)


def network_proxy_config_for_profile_selection(
    permissions: JsonValue | None,
    profile_name: str,
) -> NetworkProxyConfig:
    if is_builtin_permission_profile_name(profile_name):
        return NetworkProxyConfig()
    reject_unknown_builtin_permission_profile(profile_name)
    if permissions is None:
        raise ValueError("default_permissions requires a `[permissions]` table")
    profile, _warnings = resolve_permission_profile(permissions, profile_name)
    return network_proxy_config_from_profile_network(profile.get("network"))


def compile_permission_profile_workspace_roots(
    permissions: JsonValue | None,
    profile_name: str,
    policy_cwd: Path | str,
) -> tuple[Path, ...]:
    """Return Rust-equivalent workspace roots for built-ins and missing custom tables."""

    if is_builtin_permission_profile_name(profile_name):
        return ()
    reject_unknown_builtin_permission_profile(profile_name)
    if permissions is None:
        raise ValueError("default_permissions requires a `[permissions]` table")
    profile, _ = resolve_permission_profile(permissions, profile_name)
    return compile_workspace_roots(profile.get("workspace_roots"), policy_cwd)


def compile_workspace_roots(workspace_roots: JsonValue | None, policy_cwd: Path | str) -> tuple[Path, ...]:
    if workspace_roots is None:
        return ()
    entries = _entries_mapping(workspace_roots)
    cwd = Path(policy_cwd)
    roots = []
    for path, enabled in entries.items():
        if not isinstance(enabled, bool):
            raise TypeError("workspace root enabled flags must be bools")
        if enabled:
            roots.append(_resolve_path_against_base(path, cwd))
    return tuple(roots)


def compile_filesystem_permission(
    path: str,
    permission: JsonValue,
    policy_cwd: Path | str | None = None,
    startup_warnings: list[str] | None = None,
) -> tuple[FileSystemSandboxEntry, ...]:
    del policy_cwd
    warnings = startup_warnings if startup_warnings is not None else []
    entries: list[FileSystemSandboxEntry] = []
    if _is_scoped_permission(permission):
        for subpath, access in permission.items():
            access = _access_mode(access)
            has_glob = contains_glob_chars(subpath)
            can_compile_as_pattern = _special_path_allows_glob_pattern(path)
            if has_glob and access is FileSystemAccessMode.DENY and can_compile_as_pattern:
                entries.append(
                    FileSystemSandboxEntry(
                        FileSystemPath.glob_pattern(
                            compile_scoped_filesystem_pattern(path, subpath, access)
                        ),
                        access,
                    )
                )
            else:
                subpath = compile_read_write_glob_path(subpath, access)
                entries.append(
                    FileSystemSandboxEntry(
                        compile_scoped_filesystem_path(path, subpath, warnings),
                        access,
                    )
                )
    else:
        access = _access_mode(permission)
        entries.append(
            FileSystemSandboxEntry(
                compile_filesystem_access_path(path, access, warnings),
                access,
            )
        )
    return tuple(entries)


def compile_filesystem_access_path(
    path: str,
    access: FileSystemAccessMode | str,
    startup_warnings: list[str] | None = None,
) -> FileSystemPath:
    access = _access_mode(access)
    warnings = startup_warnings if startup_warnings is not None else []
    if not contains_glob_chars(path):
        return compile_filesystem_path(path, warnings)
    if access is FileSystemAccessMode.DENY:
        return FileSystemPath.glob_pattern(str(parse_absolute_path(path)))
    path = compile_read_write_glob_path(path, access)
    return compile_filesystem_path(path, warnings)


def compile_filesystem_path(
    path: str,
    startup_warnings: list[str] | None = None,
) -> FileSystemPath:
    warnings = startup_warnings if startup_warnings is not None else []
    special = parse_special_path(path)
    if special is not None:
        maybe_push_unknown_special_path_warning(special, warnings)
        return FileSystemPath.special(special)
    return FileSystemPath.explicit_path(parse_absolute_path(path))


def compile_scoped_filesystem_path(
    path: str,
    subpath: str,
    startup_warnings: list[str] | None = None,
) -> FileSystemPath:
    warnings = startup_warnings if startup_warnings is not None else []
    if subpath == ".":
        return compile_filesystem_path(path, warnings)

    special = parse_special_path(path)
    if special is not None:
        parsed_subpath = parse_relative_subpath(subpath)
        if special.kind == "project_roots":
            return FileSystemPath.special(FileSystemSpecialPath.project_roots(parsed_subpath))
        if special.kind == "unknown":
            unknown = FileSystemSpecialPath.unknown(special.path or path, parsed_subpath)
            maybe_push_unknown_special_path_warning(unknown, warnings)
            return FileSystemPath.special(unknown)
        raise ValueError(f"filesystem path `{path}` does not support nested entries")

    parsed_subpath = parse_relative_subpath(subpath)
    base = parse_absolute_path(path)
    return FileSystemPath.explicit_path(_resolve_path_against_base(str(parsed_subpath), base))


def compile_scoped_filesystem_pattern(
    path: str,
    subpath: str,
    access: FileSystemAccessMode | str,
) -> str:
    access = _access_mode(access)
    if access is not FileSystemAccessMode.DENY:
        raise ValueError(f"filesystem glob subpath `{subpath}` only supports `deny` access")
    parsed_subpath = parse_relative_subpath(subpath)
    special = parse_special_path(path)
    if special is not None:
        if special.kind == "project_roots":
            return project_roots_glob_pattern(parsed_subpath)
        raise ValueError(f"filesystem path `{path}` does not support nested entries")
    base = parse_absolute_path(path)
    return str(base / parsed_subpath)


def validate_glob_scan_max_depth(max_depth: int | None) -> int | None:
    if max_depth is None:
        return None
    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise TypeError("glob_scan_max_depth must be an integer or None")
    if max_depth == 0:
        raise ValueError("glob_scan_max_depth must be at least 1")
    if max_depth < 0:
        raise ValueError("glob_scan_max_depth must be non-negative")
    return max_depth


def contains_glob_chars(path: str) -> bool:
    return contains_glob_chars_for_platform(path, sys.platform == "win32")


def contains_glob_chars_for_platform(path: str, is_windows: bool) -> bool:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if is_windows:
        normalized = normalize_windows_device_path(path)
        if normalized is not None:
            path = normalized
    return any(char in "*?[]" for char in path)


def remove_trailing_glob_suffix(path: str) -> str:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    return path[:-3] if path.endswith("/**") else path


def compile_read_write_glob_path(path: str, access: FileSystemAccessMode | str) -> str:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    access = _access_mode(access)
    if not contains_glob_chars(path):
        return path

    path_without_trailing_glob = remove_trailing_glob_suffix(path)
    if not contains_glob_chars(path_without_trailing_glob):
        return path_without_trailing_glob

    raise ValueError(
        f"filesystem glob path `{path}` only supports `deny` access; "
        f"use an exact path or trailing `/**` for `{access.value}` subtree access"
    )


def unsupported_read_write_glob_paths(filesystem: JsonValue) -> tuple[str, ...]:
    patterns: list[str] = []
    for path, permission in _filesystem_entries(filesystem).items():
        if _is_scoped_permission(permission):
            for subpath, access in permission.items():
                access = _access_mode(access)
                if access is not FileSystemAccessMode.DENY and contains_glob_chars(
                    remove_trailing_glob_suffix(subpath)
                ):
                    patterns.append(f"{path}/{subpath}")
        else:
            access = _access_mode(permission)
            if access is not FileSystemAccessMode.DENY and contains_glob_chars(
                remove_trailing_glob_suffix(path)
            ):
                patterns.append(path)
    return tuple(patterns)


def unbounded_unreadable_globstar_paths(filesystem: JsonValue) -> tuple[str, ...]:
    if _filesystem_glob_scan_max_depth(filesystem) is not None:
        return ()
    patterns: list[str] = []
    for path, permission in _filesystem_entries(filesystem).items():
        if _is_scoped_permission(permission):
            for subpath, access in permission.items():
                if _access_mode(access) is FileSystemAccessMode.DENY and "**" in subpath:
                    patterns.append(f"{path}/{subpath}")
        elif _access_mode(permission) is FileSystemAccessMode.DENY and "**" in path:
            patterns.append(path)
    return tuple(patterns)


def normalize_absolute_path_for_platform(path: str, is_windows: bool) -> Path:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if not is_windows:
        return Path(path)
    normalized = normalize_windows_device_path(path)
    return Path(normalized if normalized is not None else path)


def parse_absolute_path(path: str) -> Path:
    return parse_absolute_path_for_platform(path, sys.platform == "win32")


def parse_absolute_path_for_platform(path: str, is_windows: bool) -> Path:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    normalized = normalize_absolute_path_for_platform(path, is_windows)
    if not _is_absolute_path_for_platform(path, normalized, is_windows) and path != "~" and not path.startswith("~/"):
        raise ValueError(f"filesystem path `{path}` must be absolute, use `~/...`, or start with `:`")
    return normalized


def normalize_windows_device_path(path: str) -> str | None:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[len("\\\\?\\UNC\\") :]
    if path.startswith("\\\\.\\UNC\\"):
        return "\\\\" + path[len("\\\\.\\UNC\\") :]
    if path.startswith("\\\\?\\"):
        suffix = path[len("\\\\?\\") :]
        if is_windows_drive_absolute_path(suffix):
            return suffix
    if path.startswith("\\\\.\\"):
        suffix = path[len("\\\\.\\") :]
        if is_windows_drive_absolute_path(suffix):
            return suffix
    return None


def is_windows_absolute_path(path: str) -> bool:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    return is_windows_drive_absolute_path(path) or path.startswith("\\\\")


def is_windows_drive_absolute_path(path: str) -> bool:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    return (
        len(path) >= 3
        and path[0].isalpha()
        and path[1] == ":"
        and path[2] in "\\/"
    )


def parse_relative_subpath(subpath: str) -> Path:
    if not isinstance(subpath, str):
        raise TypeError("subpath must be a string")
    path = Path(subpath)
    if (
        subpath
        and subpath != "."
        and not path.is_absolute()
        and path.parts
        and all(part not in {"", ".", ".."} for part in path.parts)
        and not (len(subpath) >= 2 and subpath[1] == ":")
    ):
        return path
    raise ValueError(
        f"filesystem subpath `{path}` must be a descendant path without `.` or `..` components"
    )


def parse_special_path(path: str) -> FileSystemSpecialPath | None:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if path == ":root":
        return FileSystemSpecialPath.root()
    if path == ":minimal":
        return FileSystemSpecialPath.minimal()
    if path == ":workspace_roots":
        return FileSystemSpecialPath.project_roots()
    if path == ":tmpdir":
        return FileSystemSpecialPath.tmpdir()
    if path.startswith(":"):
        return FileSystemSpecialPath.unknown(path)
    return None


def maybe_push_unknown_special_path_warning(
    special: FileSystemSpecialPath,
    startup_warnings: list[str],
) -> None:
    if special.kind != "unknown":
        return
    path = special.path or ":unknown"
    if special.subpath is not None:
        startup_warnings.append(
            f"Configured filesystem path `{path}` with nested entry `{special.subpath}` "
            "is not recognized by this version of Codex and will be ignored. "
            "Upgrade Codex if this path is required."
        )
    else:
        startup_warnings.append(
            f"Configured filesystem path `{path}` is not recognized by this version of Codex "
            "and will be ignored. Upgrade Codex if this path is required."
        )


def _push_missing_filesystem_entries_warning(startup_warnings: list[str], profile_name: str) -> None:
    startup_warnings.append(
        f"Permissions profile `{profile_name}` does not define any recognized filesystem entries for this version of Codex. Filesystem access will remain restricted. Upgrade Codex if this profile expects filesystem permissions."
    )


def get_readable_roots_required_for_codex_runtime(
    codex_home: Path | str,
    zsh_path: Path | str | None = None,
    main_execve_wrapper_exe: Path | str | None = None,
) -> tuple[Path, ...]:
    """Return helper roots that Rust always adds to restricted read policies."""

    codex_home = Path(codex_home)
    arg0_root = codex_home / "tmp" / "arg0"
    readable_roots: list[Path] = []

    if zsh_path is not None:
        readable_roots.append(Path(zsh_path))

    if main_execve_wrapper_exe is not None:
        wrapper = Path(main_execve_wrapper_exe)
        if _path_starts_with(wrapper, arg0_root):
            parent = wrapper.parent
            if parent != wrapper:
                readable_roots.append(parent)
        else:
            readable_roots.append(wrapper)

    return tuple(readable_roots)


def _workspace_write_from_value(value: SandboxWorkspaceWrite | JsonValue) -> SandboxWorkspaceWrite:
    if isinstance(value, SandboxWorkspaceWrite):
        return value
    if isinstance(value, dict):
        return SandboxWorkspaceWrite(
            writable_roots=tuple(Path(path) for path in value.get("writable_roots", ())),
            network_access=bool(value.get("network_access", False)),
            exclude_tmpdir_env_var=bool(value.get("exclude_tmpdir_env_var", False)),
            exclude_slash_tmp=bool(value.get("exclude_slash_tmp", False)),
        )
    return SandboxWorkspaceWrite(
        writable_roots=tuple(Path(path) for path in getattr(value, "writable_roots", ())),
        network_access=bool(getattr(value, "network_access", False)),
        exclude_tmpdir_env_var=bool(getattr(value, "exclude_tmpdir_env_var", False)),
        exclude_slash_tmp=bool(getattr(value, "exclude_slash_tmp", False)),
    )


def _apply_network_to_network_proxy_config(config: NetworkProxyConfig, network: JsonValue) -> None:
    network = _network_mapping(network)
    target = config.network
    if "enabled" in network and network["enabled"] is not None:
        if not isinstance(network["enabled"], bool):
            raise TypeError("network.enabled must be a bool")
        target.enabled = network["enabled"]
    if "proxy_url" in network and network["proxy_url"] is not None:
        target.proxy_url = _string_field(network["proxy_url"], "network.proxy_url")
    if "enable_socks5" in network and network["enable_socks5"] is not None:
        target.enable_socks5 = _bool_field(network["enable_socks5"], "network.enable_socks5")
    if "socks_url" in network and network["socks_url"] is not None:
        target.socks_url = _string_field(network["socks_url"], "network.socks_url")
    if "enable_socks5_udp" in network and network["enable_socks5_udp"] is not None:
        target.enable_socks5_udp = _bool_field(network["enable_socks5_udp"], "network.enable_socks5_udp")
    if "allow_upstream_proxy" in network and network["allow_upstream_proxy"] is not None:
        target.allow_upstream_proxy = _bool_field(network["allow_upstream_proxy"], "network.allow_upstream_proxy")
    if "dangerously_allow_non_loopback_proxy" in network and network["dangerously_allow_non_loopback_proxy"] is not None:
        target.dangerously_allow_non_loopback_proxy = _bool_field(
            network["dangerously_allow_non_loopback_proxy"],
            "network.dangerously_allow_non_loopback_proxy",
        )
    if "dangerously_allow_all_unix_sockets" in network and network["dangerously_allow_all_unix_sockets"] is not None:
        target.dangerously_allow_all_unix_sockets = _bool_field(
            network["dangerously_allow_all_unix_sockets"],
            "network.dangerously_allow_all_unix_sockets",
        )
    if "mode" in network and network["mode"] is not None:
        target.mode = NetworkMode(_string_field(network["mode"], "network.mode"))
    if "domains" in network and network["domains"] is not None:
        allowed, denied = _network_domain_lists(network["domains"])
        target.set_allowed_domains(allowed)
        target.set_denied_domains(denied)
    if "unix_sockets" in network and network["unix_sockets"] is not None:
        target.set_allow_unix_sockets(_network_allowed_unix_sockets(network["unix_sockets"]))
    if "allow_local_binding" in network and network["allow_local_binding"] is not None:
        target.allow_local_binding = _bool_field(network["allow_local_binding"], "network.allow_local_binding")


def _network_mapping(network: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(network, dict):
        fields = {
            name: getattr(network, name)
            for name in (
                "enabled",
                "proxy_url",
                "enable_socks5",
                "socks_url",
                "enable_socks5_udp",
                "allow_upstream_proxy",
                "dangerously_allow_non_loopback_proxy",
                "dangerously_allow_all_unix_sockets",
                "mode",
                "domains",
                "unix_sockets",
                "allow_local_binding",
            )
            if hasattr(network, name)
        }
        if fields:
            return fields
        raise TypeError("network must be a mapping")
    return dict(network)


def _network_domain_lists(domains: JsonValue) -> tuple[list[str] | None, list[str] | None]:
    entries = _entries_container(domains)
    allowed: list[str] = []
    denied: list[str] = []
    for pattern, permission in entries.items():
        if not isinstance(pattern, str):
            raise TypeError("network domain patterns must be strings")
        permission = NetworkDomainPermission(permission)
        if permission is NetworkDomainPermission.ALLOW:
            allowed.append(pattern)
        else:
            denied.append(pattern)
    return allowed or None, denied or None


def _network_allowed_unix_sockets(unix_sockets: JsonValue) -> list[str]:
    if isinstance(unix_sockets, dict):
        entries = _entries_container(unix_sockets)
        sockets = []
        for path, permission in entries.items():
            if not isinstance(path, str):
                raise TypeError("network unix socket paths must be strings")
            if str(permission) == "allow":
                sockets.append(path)
        return sockets
    if isinstance(unix_sockets, str) or not isinstance(unix_sockets, (list, tuple)):
        raise TypeError("network.unix_sockets must be a sequence or mapping")
    if not all(isinstance(path, str) for path in unix_sockets):
        raise TypeError("network.unix_sockets entries must be strings")
    return list(unix_sockets)


def _string_field(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _bool_field(value: JsonValue, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a bool")
    return value


def _workspace_roots_from_permissions(permissions: JsonValue, profile_name: str) -> JsonValue | None:
    if not isinstance(permissions, dict):
        raise TypeError("permissions must be a mapping")
    profile = permissions.get(profile_name)
    if profile is None:
        raise ValueError(f"permissions profile `{profile_name}` is not defined")
    if not isinstance(profile, dict):
        raise TypeError("permission profile must be a mapping")
    return profile.get("workspace_roots")


def _permissions_entries(permissions: JsonValue) -> dict[str, JsonValue]:
    if isinstance(permissions, dict) and "entries" in permissions:
        permissions = permissions["entries"]
    if not isinstance(permissions, dict):
        raise TypeError("permissions must be a mapping")
    if not all(isinstance(key, str) for key in permissions):
        raise TypeError("permission profile names must be strings")
    return dict(permissions)


def _resolve_permission_profile(
    entries: dict[str, JsonValue],
    profile_name: str,
    stack: tuple[str, ...],
) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    if profile_name in stack:
        cycle = " -> ".join((*stack, profile_name))
        raise ValueError(f"permissions profile inheritance cycle detected: {cycle}")

    builtin_marker = _extensible_builtin_parent_profile_marker(profile_name)
    if builtin_marker is not None:
        return builtin_marker, ()
    if profile_name.startswith(":"):
        raise ValueError(
            f"permissions profile `{stack[-1] if stack else profile_name}` cannot extend unsupported built-in profile `{profile_name}`"
        )
    if profile_name not in entries:
        if stack:
            raise ValueError(
                f"permissions profile `{stack[-1]}` extends undefined profile `{profile_name}`"
            )
        raise ValueError(f"permissions profile `{profile_name}` is not defined")

    profile = _profile_mapping(entries[profile_name])
    parent_name = profile.get("extends")
    if parent_name is None:
        return dict(profile), ()
    if not isinstance(parent_name, str):
        raise TypeError("extends must be a string")
    parent, inherited = _resolve_permission_profile(entries, parent_name, (*stack, profile_name))
    merged = _merge_profiles(parent, profile)
    return merged, (*inherited, parent_name)


def _extensible_builtin_parent_profile_marker(profile_name: str) -> dict[str, JsonValue] | None:
    if profile_name in {BUILT_IN_READ_ONLY_PROFILE, BUILT_IN_WORKSPACE_PROFILE}:
        return {}
    return None


def _profile_mapping(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError("permission profile must be a mapping")
    return dict(value)


def _merge_profiles(parent: dict[str, JsonValue], child: dict[str, JsonValue]) -> dict[str, JsonValue]:
    merged: dict[str, JsonValue] = dict(parent)
    for key, value in child.items():
        if key == "filesystem":
            merged[key] = _merge_filesystem(merged.get(key), value)
        elif key == "network":
            merged[key] = _merge_network(merged.get(key), value)
        elif key == "workspace_roots":
            merged[key] = _merge_entries_mapping(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _merge_filesystem(parent: JsonValue | None, child: JsonValue | None) -> dict[str, JsonValue] | None:
    if child is None:
        return parent if parent is None else _filesystem_container(parent)
    parent_data = {} if parent is None else _filesystem_container(parent)
    child_data = _filesystem_container(child)
    entries = dict(parent_data.get("entries", {}))
    for path, permission in child_data.get("entries", {}).items():
        if _is_scoped_permission(permission) and _is_scoped_permission(entries.get(path)):
            nested = dict(entries[path])
            nested.update(permission)
            entries[path] = nested
        else:
            entries[path] = permission
    merged: dict[str, JsonValue] = dict(parent_data)
    merged["entries"] = entries
    if "glob_scan_max_depth" in child_data:
        merged["glob_scan_max_depth"] = child_data.get("glob_scan_max_depth")
    return merged


def _merge_network(parent: JsonValue | None, child: JsonValue | None) -> dict[str, JsonValue] | None:
    if child is None:
        return parent if parent is None else dict(parent)
    if not isinstance(child, dict):
        raise TypeError("network must be a mapping")
    parent_data = {} if parent is None else dict(parent)
    merged = dict(parent_data)
    for key, value in child.items():
        if key in {"domains", "unix_sockets"}:
            merged[key] = _merge_entries_mapping(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _merge_entries_mapping(parent: JsonValue | None, child: JsonValue | None) -> JsonValue | None:
    if child is None:
        return parent
    parent_entries = {} if parent is None else _entries_container(parent)
    child_entries = _entries_container(child)
    merged = dict(parent_entries)
    merged.update(child_entries)
    return {"entries": merged} if _has_entries_wrapper(parent) or _has_entries_wrapper(child) else merged


def _filesystem_container(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError("filesystem must be a mapping")
    if "entries" in value:
        entries = value["entries"]
        if not isinstance(entries, dict):
            raise TypeError("filesystem entries must be a mapping")
        return dict(value)
    data: dict[str, JsonValue] = {
        "entries": {
            key: entry for key, entry in value.items() if key != "glob_scan_max_depth"
        }
    }
    if "glob_scan_max_depth" in value:
        data["glob_scan_max_depth"] = value["glob_scan_max_depth"]
    return data


def _entries_container(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError("entries must be a mapping")
    if "entries" in value:
        entries = value["entries"]
        if not isinstance(entries, dict):
            raise TypeError("entries must be a mapping")
        return dict(entries)
    return dict(value)


def _has_entries_wrapper(value: JsonValue) -> bool:
    return isinstance(value, dict) and "entries" in value


def _entries_mapping(value: JsonValue) -> dict[str, bool]:
    if isinstance(value, dict) and "entries" in value:
        value = value["entries"]
    if not isinstance(value, dict):
        raise TypeError("workspace_roots must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise TypeError("workspace root paths must be strings")
    return dict(value)


def _filesystem_entries(filesystem: JsonValue) -> dict[str, JsonValue]:
    if isinstance(filesystem, dict) and "entries" in filesystem:
        filesystem = filesystem["entries"]
    if not isinstance(filesystem, dict):
        raise TypeError("filesystem must be a mapping")
    entries = {
        key: value
        for key, value in filesystem.items()
        if key != "glob_scan_max_depth"
    }
    if not all(isinstance(key, str) for key in entries):
        raise TypeError("filesystem paths must be strings")
    return dict(entries)


def _filesystem_glob_scan_max_depth(filesystem: JsonValue) -> int | None:
    if isinstance(filesystem, dict):
        return validate_glob_scan_max_depth(filesystem.get("glob_scan_max_depth"))
    return None


def _is_scoped_permission(permission: JsonValue) -> bool:
    return isinstance(permission, dict)


def _access_mode(access: FileSystemAccessMode | str) -> FileSystemAccessMode:
    if isinstance(access, FileSystemAccessMode):
        return access
    if not isinstance(access, str):
        raise TypeError("access must be a FileSystemAccessMode or string")
    return FileSystemAccessMode.parse(access)


def _special_path_allows_glob_pattern(path: str) -> bool:
    special = parse_special_path(path)
    return special is None or special.kind == "project_roots"


def _is_absolute_path_for_platform(path: str, normalized_path: Path, is_windows: bool) -> bool:
    if is_windows:
        return is_windows_absolute_path(path) or is_windows_absolute_path(str(normalized_path))
    return normalized_path.is_absolute()


def _resolve_path_against_base(path: str, base: Path) -> Path:
    path_value = Path(path)
    if path_value.is_absolute():
        return path_value
    return base / path_value


def _path_starts_with(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


def _call_or_attr(target: Any, name: str) -> Any:
    value = getattr(target, name, False)
    return value() if callable(value) else value


__all__ = [
    "BUILT_IN_DANGER_FULL_ACCESS_PROFILE",
    "BUILT_IN_READ_ONLY_PROFILE",
    "BUILT_IN_WORKSPACE_PROFILE",
    "ProjectTrust",
    "SandboxWorkspaceWrite",
    "builtin_permission_profile",
    "compile_permission_profile_selection",
    "compile_permission_profile_workspace_roots",
    "compile_filesystem_access_path",
    "compile_filesystem_path",
    "compile_filesystem_permission",
    "compile_network_sandbox_policy",
    "compile_permission_profile",
    "compile_read_write_glob_path",
    "compile_scoped_filesystem_path",
    "compile_scoped_filesystem_pattern",
    "compile_workspace_roots",
    "contains_glob_chars",
    "contains_glob_chars_for_platform",
    "default_builtin_permission_profile_name",
    "get_readable_roots_required_for_codex_runtime",
    "is_builtin_permission_profile_name",
    "is_windows_absolute_path",
    "is_windows_drive_absolute_path",
    "apply_network_proxy_feature_config",
    "network_proxy_config_for_profile_selection",
    "network_proxy_config_from_profile_network",
    "normalize_absolute_path_for_platform",
    "normalize_windows_device_path",
    "maybe_push_unknown_special_path_warning",
    "parse_absolute_path",
    "parse_absolute_path_for_platform",
    "parse_relative_subpath",
    "parse_special_path",
    "reject_unknown_builtin_permission_profile",
    "remove_trailing_glob_suffix",
    "resolve_permission_profile",
    "unbounded_unreadable_globstar_paths",
    "unsupported_read_write_glob_paths",
    "validate_user_permission_profile_names",
    "validate_glob_scan_max_depth",
]
