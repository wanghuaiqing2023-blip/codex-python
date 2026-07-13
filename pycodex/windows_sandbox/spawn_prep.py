"""Legacy restricted-token spawn preparation.

Rust owner: ``codex-windows-sandbox::spawn_prep`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from pycodex.protocol import PermissionProfile

from .acl import add_allow_ace, add_deny_write_ace, allow_null_device
from .allow import AllowDenyPaths, compute_allow_paths_for_permissions
from .cap import load_or_create_cap_sids, workspace_write_cap_sid_for_root
from .env import apply_no_network_to_env, ensure_non_interactive_pager, inherit_path_env, normalize_null_device_env
from .path_normalization import canonical_path_key, canonicalize_path
from .resolved_permissions import ResolvedWindowsSandboxPermissions
from .setup import effective_write_roots_for_permissions, sandbox_dir
from .token import (
    LocalSid,
    WinHandle,
    create_readonly_token_with_caps_from,
    create_workspace_write_token_with_caps_from,
    get_current_token_for_restriction,
)


class WindowsSandboxSpawnPrepError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpawnPrepOptions:
    inherit_path: bool = False
    add_git_safe_directory: bool = False


@dataclass(frozen=True)
class SpawnContext:
    permissions: ResolvedWindowsSandboxPermissions
    current_dir: Path
    logs_base_dir: Path
    uses_write_capabilities: bool


@dataclass
class RootCapabilitySid:
    root: Path
    sid: LocalSid
    sid_str: str

    def close(self) -> None:
        self.sid.close()


@dataclass
class LegacySessionSecurity:
    token: WinHandle
    readonly_sid: LocalSid | None
    readonly_sid_str: str | None
    write_root_sids: tuple[RootCapabilitySid, ...]

    def close(self) -> None:
        self.token.close()
        if self.readonly_sid is not None:
            self.readonly_sid.close()
        for root in self.write_root_sids:
            root.close()

    def __enter__(self) -> "LegacySessionSecurity":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()


def prepare_legacy_spawn_context(
    permission_profile: PermissionProfile,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    cwd: str | Path,
    env_map: MutableMapping[str, str],
    command: Sequence[str],
    options: SpawnPrepOptions = SpawnPrepOptions(),
) -> SpawnContext:
    permissions = ResolvedWindowsSandboxPermissions.try_from_permission_profile_for_cwd(
        permission_profile,
        permission_profile_cwd,
    )
    normalize_null_device_env(env_map)
    ensure_non_interactive_pager(env_map)
    if options.inherit_path:
        inherit_path_env(env_map)
    if options.add_git_safe_directory:
        _inject_git_safe_directory(env_map, cwd)
    home = Path(codex_home)
    home.mkdir(parents=True, exist_ok=True)
    logs = sandbox_dir(home)
    logs.mkdir(parents=True, exist_ok=True)
    current_dir = Path(cwd)
    uses_write = permissions.uses_write_capabilities_for_cwd(current_dir, env_map)
    if permissions.should_apply_network_block():
        apply_no_network_to_env(env_map)
    return SpawnContext(permissions, current_dir, logs, uses_write)


def legacy_session_capability_roots(
    permissions: ResolvedWindowsSandboxPermissions,
    current_dir: str | Path,
    env_map: Mapping[str, str],
    codex_home: str | Path,
) -> tuple[Path, ...]:
    allow_paths = compute_allow_paths_for_permissions(permissions, current_dir, env_map).allow
    if not permissions.uses_write_capabilities_for_cwd(current_dir, env_map):
        return tuple(sorted(allow_paths, key=canonical_path_key))
    return effective_write_roots_for_permissions(
        permissions,
        current_dir,
        env_map,
        codex_home,
        allow_paths,
    )


def root_capability_sids(
    codex_home: str | Path,
    cwd: str | Path,
    allow_paths: Iterable[str | Path],
) -> tuple[RootCapabilitySid, ...]:
    unique: dict[str, Path] = {}
    for path in allow_paths:
        canonical = canonicalize_path(path)
        unique[canonical_path_key(canonical)] = canonical
    output: list[RootCapabilitySid] = []
    try:
        for key in sorted(unique):
            root = unique[key]
            sid_str = workspace_write_cap_sid_for_root(codex_home, cwd, root)
            output.append(RootCapabilitySid(root, LocalSid(sid_str), sid_str))
    except BaseException:
        for item in output:
            item.close()
        raise
    return tuple(output)


def prepare_legacy_session_security(
    context: SpawnContext,
    codex_home: str | Path,
    env_map: Mapping[str, str],
) -> LegacySessionSecurity:
    if context.uses_write_capabilities:
        roots = root_capability_sids(
            codex_home,
            context.current_dir,
            legacy_session_capability_roots(
                context.permissions,
                context.current_dir,
                env_map,
                codex_home,
            ),
        )
        if not roots:
            raise WindowsSandboxSpawnPrepError("workspace-write sandbox has no writable root capability SIDs")
        try:
            with get_current_token_for_restriction() as base:
                token = create_workspace_write_token_with_caps_from(base, [root.sid for root in roots])
            for root in roots:
                allow_null_device(root.sid)
        except BaseException:
            for root in roots:
                root.close()
            raise
        return LegacySessionSecurity(token, None, None, roots)

    caps = load_or_create_cap_sids(codex_home)
    readonly_sid = LocalSid(caps.readonly)
    try:
        with get_current_token_for_restriction() as base:
            token = create_readonly_token_with_caps_from(base, [readonly_sid])
        allow_null_device(readonly_sid)
    except BaseException:
        readonly_sid.close()
        raise
    return LegacySessionSecurity(token, readonly_sid, caps.readonly, ())


def apply_legacy_session_acl_rules(
    context: SpawnContext,
    codex_home: str | Path,
    env_map: Mapping[str, str],
    security: LegacySessionSecurity,
    *,
    additional_deny_write_paths: Iterable[str | Path] = (),
) -> AllowDenyPaths:
    paths = compute_allow_paths_for_permissions(context.permissions, context.current_dir, env_map)
    deny = set(paths.deny)
    for raw in additional_deny_write_paths:
        path = Path(raw)
        path.mkdir(parents=True, exist_ok=True)
        deny.add(canonicalize_path(path))

    if security.readonly_sid is not None:
        for path in paths.allow:
            add_allow_ace(path, security.readonly_sid)
    else:
        for path in paths.allow:
            root = _matching_root_capability(path, security.write_root_sids)
            if root is not None:
                add_allow_ace(path, root.sid)
    for path in deny:
        for root in _deny_root_capabilities_for_path(path, security.write_root_sids):
            add_deny_write_ace(path, root.sid)
    return AllowDenyPaths(paths.allow, frozenset(deny))


def _matching_root_capability(path: Path, roots: Sequence[RootCapabilitySid]) -> RootCapabilitySid | None:
    matches = [root for root in roots if _contains(root.root, path)]
    return max(matches, key=lambda root: len(canonicalize_path(root.root).parts), default=None)


def _deny_root_capabilities_for_path(path: Path, roots: Sequence[RootCapabilitySid]) -> tuple[RootCapabilitySid, ...]:
    matches = tuple(root for root in roots if _contains(root.root, path) or _contains(path, root.root))
    return matches or tuple(roots)


def _contains(root: str | Path, path: str | Path) -> bool:
    try:
        canonicalize_path(path).relative_to(canonicalize_path(root))
    except ValueError:
        return False
    return True


def _inject_git_safe_directory(env_map: MutableMapping[str, str], cwd: str | Path) -> None:
    env_map["GIT_CONFIG_COUNT"] = "1"
    env_map["GIT_CONFIG_KEY_0"] = "safe.directory"
    env_map["GIT_CONFIG_VALUE_0"] = str(Path(cwd))


__all__ = [
    "LegacySessionSecurity",
    "RootCapabilitySid",
    "SpawnContext",
    "SpawnPrepOptions",
    "WindowsSandboxSpawnPrepError",
    "apply_legacy_session_acl_rules",
    "legacy_session_capability_roots",
    "prepare_legacy_session_security",
    "prepare_legacy_spawn_context",
    "root_capability_sids",
]
