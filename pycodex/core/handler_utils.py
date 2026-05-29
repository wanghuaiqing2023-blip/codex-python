"""Shared tool-handler helpers ported from Codex core.

This module mirrors the pure helper layer in
``core/src/tools/handlers/mod.rs``: JSON argument parsing, hook input
rewriting, workdir/environment selection, and the feature/policy checks around
inline additional permissions.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypeVar

from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    NetworkPermissions,
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
        return primary() if callable(primary) else primary

    candidates = getattr(environments, "turn_environments", None)
    if candidates is None:
        candidates = getattr(environments, "environments", ())
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
    approval_policy: AskForApproval,
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
        if not permissions_preapproved and AskForApproval(approval_policy) is not AskForApproval.ON_REQUEST:
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
    effective_permissions = merge_permission_profiles(additional_permissions, granted_permissions)
    permissions_preapproved = (
        permissions_are_preapproved(effective_permissions, granted_permissions, cwd)
        if effective_permissions is not None and granted_permissions is not None
        else False
    )

    if effective_permissions is not None and not sandbox_permissions.uses_additional_permissions():
        sandbox_permissions = SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS

    return EffectiveAdditionalPermissions(sandbox_permissions, effective_permissions, permissions_preapproved)


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


def permissions_are_preapproved(
    effective_permissions: AdditionalPermissionProfile,
    granted_permissions: AdditionalPermissionProfile,
    cwd: Path | str,
) -> bool:
    effective = _materialize_permission_profile(normalize_additional_permissions(effective_permissions), Path(cwd))
    granted = _materialize_permission_profile(normalize_additional_permissions(granted_permissions), Path(cwd))
    if effective.network is not None:
        if granted.network is None or granted.network.enabled != effective.network.enabled:
            return False
    if effective.file_system is not None:
        if granted.file_system is None:
            return False
        granted_entries = {json.dumps(entry.to_mapping(), sort_keys=True) for entry in granted.file_system.entries}
        for entry in effective.file_system.entries:
            if json.dumps(entry.to_mapping(), sort_keys=True) not in granted_entries:
                return False
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
    depth = left.glob_scan_max_depth if left.glob_scan_max_depth is not None else right.glob_scan_max_depth
    if left.glob_scan_max_depth is not None and right.glob_scan_max_depth is not None:
        depth = max(left.glob_scan_max_depth, right.glob_scan_max_depth)
    return FileSystemPermissions(entries=entries, glob_scan_max_depth=depth)


def _materialize_permission_profile(profile: AdditionalPermissionProfile, cwd: Path) -> AdditionalPermissionProfile:
    file_system = profile.file_system
    if file_system is None:
        return profile
    entries = tuple(_materialize_entry(entry, cwd) for entry in file_system.entries)
    return replace(profile, file_system=replace(file_system, entries=entries))


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


def _call_attr(value: Any, name: str) -> Any:
    attr = getattr(value, name)
    return attr() if callable(attr) else attr


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "EffectiveAdditionalPermissions",
    "apply_granted_turn_permissions",
    "implicit_granted_permissions",
    "merge_permission_profiles",
    "normalize_additional_permissions",
    "normalize_and_validate_additional_permissions",
    "parse_arguments",
    "parse_arguments_with_base_path",
    "permissions_are_preapproved",
    "resolve_tool_environment",
    "resolve_workdir_base_path",
    "rewrite_function_arguments",
    "rewrite_function_string_argument",
    "updated_hook_command",
]
