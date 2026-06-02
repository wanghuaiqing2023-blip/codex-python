"""Shared tool-handler helpers ported from Codex core.

This module mirrors the pure helper layer in
``core/src/tools/handlers/mod.rs``: JSON argument parsing, hook input
rewriting, workdir/environment selection, and the feature/policy checks around
inline additional permissions.
"""

from __future__ import annotations

import fnmatch
import inspect
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar

from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxPolicy,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    GranularApprovalConfig,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    SandboxPermissions,
)

JsonValue = Any
_T = TypeVar("_T")


def parse_arguments(arguments: str, parser: Callable[[JsonValue], _T] | None = None) -> JsonValue | _T:
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError as err:
        raise FunctionCallError.respond_to_model(f"failed to parse function arguments: {err}") from err
    return parser(value) if parser is not None else value


def updated_hook_command(updated_input: JsonValue) -> str:
    if not isinstance(updated_input, dict):
        raise FunctionCallError.respond_to_model("hook returned updatedInput without string field `command`")
    command = updated_input.get("command")
    if not isinstance(command, str):
        raise FunctionCallError.respond_to_model("hook returned updatedInput without string field `command`")
    return command


def rewrite_function_arguments(
    arguments: str,
    tool_name: str,
    rewrite: Callable[[dict[str, JsonValue]], None],
) -> str:
    value = parse_arguments(arguments)
    if not isinstance(value, dict):
        raise FunctionCallError.respond_to_model(f"{tool_name} arguments must be an object")
    rewrite(value)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as err:
        raise FunctionCallError.respond_to_model(f"failed to serialize rewritten {tool_name} arguments: {err}") from err


def rewrite_function_string_argument(
    arguments: str,
    tool_name: str,
    field_name: str,
    value: str,
) -> str:
    def rewrite(data: dict[str, JsonValue]) -> None:
        data[field_name] = value

    return rewrite_function_arguments(arguments, tool_name, rewrite)


def parse_arguments_with_base_path(
    arguments: str,
    _base_path: Path | str,
    parser: Callable[[JsonValue], _T] | None = None,
) -> JsonValue | _T:
    return parse_arguments(arguments, parser)


def resolve_workdir_base_path(arguments: str, default_cwd: Path | str) -> Path:
    value = parse_arguments(arguments)
    default = Path(default_cwd)
    if not isinstance(value, dict):
        return default
    workdir = value.get("workdir")
    if not isinstance(workdir, str) or workdir == "":
        return default
    return default / workdir


def resolve_tool_environment(turn: Any, environment_id: str | None) -> Any | None:
    environments = getattr(turn, "environments", None)
    if environment_id is None:
        primary = getattr(environments, "primary", None)
        if callable(primary):
            return primary()
        if primary is not None:
            return primary
        if isinstance(environments, (tuple, list)):
            return environments[0] if environments else None
        candidates = getattr(environments, "turn_environments", None)
        if candidates is not None:
            return candidates[0] if candidates else None
        candidates = getattr(environments, "environments", None)
        if candidates is not None:
            return candidates[0] if candidates else None
        return None

    candidates = getattr(environments, "turn_environments", None)
    if candidates is None:
        candidates = getattr(environments, "environments", ())
    if candidates == () and isinstance(environments, (tuple, list)):
        candidates = environments
    for environment in candidates or ():
        if getattr(environment, "environment_id", None) == environment_id:
            return environment
    raise FunctionCallError.respond_to_model(f"unknown turn environment id `{environment_id}`")


def normalize_additional_permissions(profile: AdditionalPermissionProfile) -> AdditionalPermissionProfile:
    if not isinstance(profile, AdditionalPermissionProfile):
        raise TypeError("profile must be AdditionalPermissionProfile")
    network = profile.network
    if network is not None and network.is_empty():
        network = None
    file_system = profile.file_system
    if file_system is not None and file_system.is_empty():
        file_system = None
    return AdditionalPermissionProfile(network=network, file_system=file_system)


def normalize_and_validate_additional_permissions(
    additional_permissions_allowed: bool,
    approval_policy: AskForApproval | GranularApprovalConfig | str,
    sandbox_permissions: SandboxPermissions,
    additional_permissions: AdditionalPermissionProfile | None,
    permissions_preapproved: bool,
    _cwd: Path | str,
) -> AdditionalPermissionProfile | None:
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    uses_additional_permissions = sandbox_permissions is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS

    if (
        not permissions_preapproved
        and not additional_permissions_allowed
        and (uses_additional_permissions or additional_permissions is not None)
    ):
        raise ValueError(
            "additional permissions are disabled; enable `features.exec_permission_approvals` before using `with_additional_permissions`"
        )

    if uses_additional_permissions:
        if not permissions_preapproved and not _approval_policy_is_on_request(approval_policy):
            raise ValueError(
                f"approval policy is {approval_policy!r}; reject command - you cannot request additional permissions unless the approval policy is OnRequest"
            )
        if additional_permissions is None:
            raise ValueError(
                "missing `additional_permissions`; provide at least one of `network` or `file_system` when using `with_additional_permissions`"
            )
        normalized = normalize_additional_permissions(additional_permissions)
        if normalized.is_empty():
            raise ValueError(
                "`additional_permissions` must include at least one requested permission in `network` or `file_system`"
            )
        return normalized

    if additional_permissions is not None:
        raise ValueError("`additional_permissions` requires `sandbox_permissions` set to `with_additional_permissions`")
    return None


def _approval_policy_is_on_request(policy: AskForApproval | GranularApprovalConfig | str) -> bool:
    if isinstance(policy, GranularApprovalConfig):
        return False
    if isinstance(policy, AskForApproval):
        return policy is AskForApproval.ON_REQUEST
    return AskForApproval.parse(str(policy)) is AskForApproval.ON_REQUEST


@dataclass(frozen=True)
class EffectiveAdditionalPermissions:
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None
    permissions_preapproved: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(str(self.sandbox_permissions)))
        if self.additional_permissions is not None and not isinstance(
            self.additional_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile")
        if not isinstance(self.permissions_preapproved, bool):
            raise TypeError("permissions_preapproved must be a bool")


def implicit_granted_permissions(
    sandbox_permissions: SandboxPermissions,
    additional_permissions: AdditionalPermissionProfile | None,
    effective_additional_permissions: EffectiveAdditionalPermissions,
) -> AdditionalPermissionProfile | None:
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if (
        not sandbox_permissions.uses_additional_permissions()
        and sandbox_permissions is not SandboxPermissions.REQUIRE_ESCALATED
        and additional_permissions is None
    ):
        return effective_additional_permissions.additional_permissions
    return None


async def apply_granted_turn_permissions(
    session: Any,
    cwd: Path | str,
    sandbox_permissions: SandboxPermissions,
    additional_permissions: AdditionalPermissionProfile | None,
) -> EffectiveAdditionalPermissions:
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if sandbox_permissions is SandboxPermissions.REQUIRE_ESCALATED:
        return EffectiveAdditionalPermissions(sandbox_permissions, additional_permissions, False)

    granted_session_permissions = await _maybe_await(_call_attr(session, "granted_session_permissions"))
    granted_turn_permissions = await _maybe_await(_call_attr(session, "granted_turn_permissions"))
    granted_permissions = merge_permission_profiles(granted_session_permissions, granted_turn_permissions)
    effective_permissions = (
        normalize_additional_permissions(additional_permissions)
        if additional_permissions is not None
        else granted_permissions
    )
    permissions_preapproved = (
        permissions_are_preapproved(effective_permissions, granted_permissions, cwd)
        if effective_permissions is not None and granted_permissions is not None
        else False
    )

    if effective_permissions is not None and not sandbox_permissions.uses_additional_permissions():
        sandbox_permissions = SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS

    return EffectiveAdditionalPermissions(sandbox_permissions, effective_permissions, permissions_preapproved)


async def session_strict_auto_review(session: Any) -> bool:
    if session is None:
        return False
    reader = getattr(session, "strict_auto_review", None)
    if callable(reader):
        value = await _maybe_await(reader())
        if not isinstance(value, bool):
            raise TypeError("strict_auto_review() must return a bool")
        return value
    value = getattr(session, "strict_auto_review_enabled", False)
    if not isinstance(value, bool):
        raise TypeError("strict_auto_review_enabled must be a bool")
    return value


def merge_permission_profiles(
    left: AdditionalPermissionProfile | None,
    right: AdditionalPermissionProfile | None,
) -> AdditionalPermissionProfile | None:
    if left is None:
        return normalize_additional_permissions(right) if right is not None else None
    if right is None:
        return normalize_additional_permissions(left)
    left = normalize_additional_permissions(left)
    right = normalize_additional_permissions(right)
    network = _merge_network_permissions(left.network, right.network)
    file_system = _merge_file_system_permissions(left.file_system, right.file_system)
    merged = normalize_additional_permissions(AdditionalPermissionProfile(network=network, file_system=file_system))
    return None if merged.is_empty() else merged


def intersect_permission_profiles(
    requested: AdditionalPermissionProfile,
    granted: AdditionalPermissionProfile,
    cwd: Path | str,
) -> AdditionalPermissionProfile:
    if not isinstance(requested, AdditionalPermissionProfile):
        raise TypeError("requested must be AdditionalPermissionProfile")
    if not isinstance(granted, AdditionalPermissionProfile):
        raise TypeError("granted must be AdditionalPermissionProfile")
    cwd = Path(cwd)
    file_system = None
    if requested.file_system is not None:
        requested_file_system = requested.file_system
        granted_file_system = granted.file_system or FileSystemPermissions()
        requested_policy = FileSystemSandboxPolicy.restricted(requested_file_system.entries)
        accepted_entries: list[FileSystemSandboxEntry] = []
        for entry in granted_file_system.entries:
            if not _granted_file_system_entry_within_request(
                requested_file_system,
                requested_policy,
                entry,
                cwd,
            ):
                continue
            materialized = _materialize_cwd_dependent_entry(entry, cwd)
            if materialized not in accepted_entries:
                accepted_entries.append(materialized)
        entries = list(accepted_entries)
        requested_retained_deny_entries = _retain_constraining_deny_entries(
            requested_file_system.entries,
            tuple(accepted_entries),
            cwd,
            entries,
        )
        granted_retained_deny_entries = _retain_constraining_deny_entries(
            granted_file_system.entries,
            tuple(accepted_entries),
            cwd,
            entries,
        )
        candidate = FileSystemPermissions(
            entries=tuple(entries),
            glob_scan_max_depth=_merge_glob_scan_max_depth(
                tuple(requested_retained_deny_entries),
                requested_file_system.glob_scan_max_depth,
                tuple(granted_retained_deny_entries),
                granted_file_system.glob_scan_max_depth,
            ),
        )
        if not candidate.is_empty():
            file_system = candidate
    network = None
    if (
        requested.network is not None
        and requested.network.enabled is True
        and granted.network is not None
        and granted.network.enabled is True
    ):
        network = NetworkPermissions(enabled=True)
    return AdditionalPermissionProfile(network=network, file_system=file_system)


def permissions_are_preapproved(
    effective_permissions: AdditionalPermissionProfile,
    granted_permissions: AdditionalPermissionProfile,
    cwd: Path | str,
) -> bool:
    cwd = Path(cwd)
    effective = normalize_additional_permissions(effective_permissions)
    granted = normalize_additional_permissions(granted_permissions)
    materialized_effective_permissions = intersect_permission_profiles(effective, effective, cwd)
    return intersect_permission_profiles(effective, granted, cwd) == materialized_effective_permissions


def normalize_request_permissions_response(
    requested_permissions: RequestPermissionProfile,
    response: RequestPermissionsResponse,
    cwd: Path | str,
) -> RequestPermissionsResponse:
    if not isinstance(requested_permissions, RequestPermissionProfile):
        raise TypeError("requested_permissions must be RequestPermissionProfile")
    if not isinstance(response, RequestPermissionsResponse):
        raise TypeError("response must be RequestPermissionsResponse")
    if response.strict_auto_review and response.scope is PermissionGrantScope.SESSION:
        return RequestPermissionsResponse(
            RequestPermissionProfile(),
            PermissionGrantScope.TURN,
            False,
        )
    if response.permissions.is_empty():
        return response
    permissions = intersect_permission_profiles(
        requested_permissions.to_additional_permission_profile(),
        response.permissions.to_additional_permission_profile(),
        cwd,
    )
    return RequestPermissionsResponse(
        RequestPermissionProfile.from_additional_permission_profile(permissions),
        response.scope,
        response.strict_auto_review,
    )


async def record_granted_request_permissions(
    response: RequestPermissionsResponse,
    *,
    session: Any = None,
    turn_state: Any = None,
) -> bool:
    if not isinstance(response, RequestPermissionsResponse):
        raise TypeError("response must be RequestPermissionsResponse")
    if response.permissions.is_empty():
        return False
    permissions = response.permissions.to_additional_permission_profile()
    if response.scope is PermissionGrantScope.TURN:
        if turn_state is None:
            return False
        await _record_turn_permissions_on_target(turn_state, permissions)
        if response.strict_auto_review:
            await _enable_strict_auto_review_on_target(turn_state)
        return True
    if session is None:
        return False
    await _record_permissions_on_target(session, permissions)
    return True


def _merge_network_permissions(
    left: NetworkPermissions | None,
    right: NetworkPermissions | None,
) -> NetworkPermissions | None:
    if left is None:
        return right
    if right is None:
        return left
    enabled = True if left.enabled is True or right.enabled is True else left.enabled if left.enabled is not None else right.enabled
    return NetworkPermissions(enabled=enabled)


def _merge_file_system_permissions(
    left: FileSystemPermissions | None,
    right: FileSystemPermissions | None,
) -> FileSystemPermissions | None:
    if left is None:
        return right
    if right is None:
        return left
    entries = tuple(dict.fromkeys((*left.entries, *right.entries)))
    depth = _merge_glob_scan_max_depth(
        left.entries,
        left.glob_scan_max_depth,
        right.entries,
        right.glob_scan_max_depth,
    )
    return FileSystemPermissions(entries=entries, glob_scan_max_depth=depth)


def _granted_file_system_entry_within_request(
    requested: FileSystemPermissions,
    requested_policy: FileSystemSandboxPolicy,
    granted_entry: FileSystemSandboxEntry,
    cwd: Path,
) -> bool:
    if not granted_entry.access.can_read():
        return False
    path = _resolve_permission_path(granted_entry.path, cwd)
    if path is not None:
        if _requested_deny_entries_match_path(requested.entries, path, cwd):
            return False
        return _access_covers(
            requested_policy.resolve_access_with_cwd(path, cwd),
            granted_entry.access,
        )
    return any(
        _access_covers(requested_entry.access, granted_entry.access)
        and requested_entry.path == granted_entry.path
        for requested_entry in requested.entries
    )


def _retain_constraining_deny_entries(
    source_entries: tuple[FileSystemSandboxEntry, ...],
    accepted_entries: tuple[FileSystemSandboxEntry, ...],
    cwd: Path,
    output_entries: list[FileSystemSandboxEntry],
) -> tuple[FileSystemSandboxEntry, ...]:
    retained_entries: list[FileSystemSandboxEntry] = []
    for entry in source_entries:
        if entry.access is not FileSystemAccessMode.DENY:
            continue
        if not _deny_entry_constrains_accepted_grant(entry, accepted_entries, cwd):
            continue
        materialized = _materialize_cwd_dependent_entry(entry, cwd)
        if materialized not in output_entries:
            output_entries.append(materialized)
        retained_entries.append(materialized)
    return tuple(retained_entries)


def _deny_entry_constrains_accepted_grant(
    deny_entry: FileSystemSandboxEntry,
    accepted_entries: tuple[FileSystemSandboxEntry, ...],
    cwd: Path,
) -> bool:
    for entry in accepted_entries:
        if not entry.access.can_read():
            continue
        grant_path = _resolve_permission_path(entry.path, cwd)
        if grant_path is None:
            continue
        if deny_entry.path.type == "glob_pattern" and deny_entry.path.pattern is not None:
            prefix = _glob_static_prefix_path(deny_entry.path.pattern, cwd)
            if prefix is not None and _paths_overlap(prefix, grant_path):
                return True
            continue
        deny_path = _resolve_permission_path(deny_entry.path, cwd)
        if deny_path is not None and _paths_overlap(deny_path, grant_path):
            return True
    return False


def _requested_deny_entries_match_path(
    requested_entries: tuple[FileSystemSandboxEntry, ...],
    path: Path,
    cwd: Path,
) -> bool:
    for entry in requested_entries:
        if entry.access is not FileSystemAccessMode.DENY:
            continue
        if entry.path.type == "glob_pattern" and entry.path.pattern is not None:
            pattern = str(_resolve_against_base(entry.path.pattern, cwd)).replace("\\", "/")
            if _glob_pattern_matches_path(pattern, path):
                return True
            continue
        deny_path = _resolve_permission_path(entry.path, cwd)
        if deny_path is not None and _path_starts_with(path, deny_path):
            return True
    return False


def _access_covers(requested: FileSystemAccessMode, granted: FileSystemAccessMode) -> bool:
    if granted is FileSystemAccessMode.READ:
        return requested.can_read()
    if granted is FileSystemAccessMode.WRITE:
        return requested.can_write()
    return False


def _merge_glob_scan_max_depth(
    left_entries: tuple[FileSystemSandboxEntry, ...],
    left_depth: int | None,
    right_entries: tuple[FileSystemSandboxEntry, ...],
    right_depth: int | None,
) -> int | None:
    left_effective = _effective_glob_scan_depth(left_entries, left_depth)
    right_effective = _effective_glob_scan_depth(right_entries, right_depth)
    if left_effective == "unbounded" or right_effective == "unbounded":
        return None
    depths = [depth for depth in (left_effective, right_effective) if isinstance(depth, int)]
    if depths:
        return max(depths)
    return None


def _effective_glob_scan_depth(
    entries: tuple[FileSystemSandboxEntry, ...],
    depth: int | None,
) -> int | str | None:
    has_deny_glob = any(
        entry.access is FileSystemAccessMode.DENY and entry.path.type == "glob_pattern"
        for entry in entries
    )
    if not has_deny_glob:
        return None
    return depth if depth is not None else "unbounded"


def _materialize_permission_profile(profile: AdditionalPermissionProfile, cwd: Path) -> AdditionalPermissionProfile:
    file_system = profile.file_system
    if file_system is None:
        return profile
    entries = tuple(_materialize_entry(entry, cwd) for entry in file_system.entries)
    return replace(profile, file_system=replace(file_system, entries=entries))


def _materialize_cwd_dependent_entry(entry: FileSystemSandboxEntry, cwd: Path) -> FileSystemSandboxEntry:
    if (
        entry.path.type == "special"
        and entry.path.value is not None
        and entry.path.value.kind == "project_roots"
    ):
        resolved = _resolve_permission_path(entry.path, cwd)
        if resolved is not None:
            return replace(entry, path=FileSystemPath.explicit_path(resolved))
    if entry.path.type == "glob_pattern" and entry.path.pattern is not None:
        return replace(
            entry,
            path=FileSystemPath.glob_pattern(str(_resolve_against_base(entry.path.pattern, cwd))),
        )
    return entry


def _materialize_entry(entry: FileSystemSandboxEntry, cwd: Path) -> FileSystemSandboxEntry:
    path = entry.path
    if path.type == "path" and path.path is not None and not path.path.is_absolute():
        return replace(entry, path=replace(path, path=cwd / path.path))
    if (
        path.type == "special"
        and path.value is not None
        and isinstance(path.value, FileSystemSpecialPath)
        and path.value.kind == "project_roots"
    ):
        subpath = path.value.subpath or Path()
        return replace(entry, path=replace(path, type="path", path=cwd / subpath, value=None))
    return entry


def _resolve_permission_path(path: FileSystemPath, cwd: Path) -> Path | None:
    if path.type == "path":
        return path.path
    if path.type == "glob_pattern":
        return None
    if path.type == "special" and path.value is not None:
        value = path.value
        if value.kind == "root":
            return _absolute_root_path_for_cwd(cwd)
        if value.kind == "project_roots":
            return _resolve_against_base(value.subpath or Path("."), cwd)
        if value.kind == "tmpdir":
            raw_tmpdir = os.environ.get("TMPDIR")
            if not raw_tmpdir:
                return None
            tmpdir = Path(raw_tmpdir)
            return tmpdir if tmpdir.is_absolute() else None
        if value.kind == "slash_tmp":
            slash_tmp = Path("/tmp")
            return slash_tmp if slash_tmp.is_dir() else None
    return None


def _resolve_against_base(path: Path | str, base: Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return _resolve_base_cwd(base) / path


def _resolve_base_cwd(cwd: Path) -> Path:
    return cwd if cwd.is_absolute() else Path.cwd() / cwd


def _absolute_root_path_for_cwd(cwd: Path) -> Path:
    if cwd.anchor:
        return Path(cwd.anchor)
    return Path("/")


def _path_starts_with(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
    except ValueError:
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_starts_with(left, right) or _path_starts_with(right, left)


def _glob_static_prefix_path(pattern: str, cwd: Path) -> Path | None:
    resolved_pattern = str(_resolve_against_base(pattern, cwd))
    wildcard_indexes = [index for token in ("*", "?", "[", "]") if (index := resolved_pattern.find(token)) != -1]
    if not wildcard_indexes:
        return Path(resolved_pattern)
    index = min(wildcard_indexes)
    if index == 0:
        return None
    prefix = resolved_pattern[:index]
    if prefix.endswith(("/", "\\")):
        return Path(prefix)
    parent = Path(prefix).parent
    return parent if str(parent) else None


def _glob_pattern_matches_path(pattern: str, path: Path) -> bool:
    target = str(path).replace("\\", "/")
    candidates = [pattern]
    if "**/" in pattern:
        candidates.append(pattern.replace("**/", ""))
    return any(fnmatch.fnmatch(target, candidate) for candidate in candidates)


def _call_attr(value: Any, name: str) -> Any:
    attr = getattr(value, name)
    return attr() if callable(attr) else attr


async def _record_permissions_on_target(target: Any, permissions: AdditionalPermissionProfile) -> None:
    recorder = getattr(target, "record_granted_permissions", None)
    if callable(recorder):
        await _maybe_await(recorder(permissions))
        return
    current = getattr(target, "granted_permissions", None)
    if callable(current):
        current = await _maybe_await(current())
    setattr(target, "granted_permissions", merge_permission_profiles(current, permissions))


async def _record_turn_permissions_on_target(target: Any, permissions: AdditionalPermissionProfile) -> None:
    recorder = getattr(target, "record_granted_turn_permissions", None)
    if callable(recorder):
        await _maybe_await(recorder(permissions))
        return
    await _record_permissions_on_target(target, permissions)


async def _enable_strict_auto_review_on_target(target: Any) -> None:
    enabler = getattr(target, "enable_strict_auto_review", None)
    if callable(enabler):
        await _maybe_await(enabler())
        return
    setattr(target, "strict_auto_review_enabled", True)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "EffectiveAdditionalPermissions",
    "apply_granted_turn_permissions",
    "implicit_granted_permissions",
    "intersect_permission_profiles",
    "merge_permission_profiles",
    "normalize_additional_permissions",
    "normalize_and_validate_additional_permissions",
    "normalize_request_permissions_response",
    "parse_arguments",
    "parse_arguments_with_base_path",
    "permissions_are_preapproved",
    "record_granted_request_permissions",
    "resolve_tool_environment",
    "resolve_workdir_base_path",
    "rewrite_function_arguments",
    "rewrite_function_string_argument",
    "session_strict_auto_review",
    "updated_hook_command",
]
