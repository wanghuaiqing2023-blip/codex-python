"""Apply-patch safety checks ported from ``core/src/safety.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pycodex.protocol import (
    AskForApproval,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    WindowsSandboxLevel,
)

from .apply_patch import ApplyPatchAction
from .sandbox_tags import SandboxType, get_platform_sandbox
from .util import resolve_path

PATCH_REJECTED_OUTSIDE_PROJECT_REASON = "writing outside of the project; rejected by user approval settings"
PATCH_REJECTED_READ_ONLY_REASON = "writing is blocked by read-only sandbox; rejected by user approval settings"


def _ensure_pathlike(value: object, field: str) -> str | Path:
    if isinstance(value, (str, Path)):
        return value
    raise TypeError(f"{field} must be path-like")


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool")
    return value


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_policy(value: object) -> ApprovalPolicy:
    if isinstance(value, (AskForApproval, GranularApprovalConfig)):
        return value
    raise TypeError("policy must be AskForApproval or GranularApprovalConfig")


@dataclass(frozen=True)
class SafetyCheck:
    type: str
    sandbox_type: SandboxType | None = None
    user_explicitly_approved: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        check_type = _ensure_str(self.type, "type")
        if check_type == "auto_approve":
            if not isinstance(self.sandbox_type, SandboxType):
                raise TypeError("sandbox_type must be a SandboxType")
            object.__setattr__(self, "user_explicitly_approved", _ensure_bool(self.user_explicitly_approved, "user_explicitly_approved"))
            object.__setattr__(self, "reason", None)
        elif check_type == "ask_user":
            object.__setattr__(self, "sandbox_type", None)
            object.__setattr__(self, "user_explicitly_approved", False)
            object.__setattr__(self, "reason", None)
        elif check_type == "reject":
            object.__setattr__(self, "sandbox_type", None)
            object.__setattr__(self, "user_explicitly_approved", False)
            object.__setattr__(self, "reason", _ensure_str(self.reason, "reason"))
        else:
            raise ValueError(f"unsupported safety check type: {check_type}")

    @classmethod
    def auto_approve(
        cls,
        sandbox_type: SandboxType,
        *,
        user_explicitly_approved: bool = False,
    ) -> "SafetyCheck":
        return cls(
            type="auto_approve",
            sandbox_type=sandbox_type,
            user_explicitly_approved=_ensure_bool(user_explicitly_approved, "user_explicitly_approved"),
        )

    @classmethod
    def ask_user(cls) -> "SafetyCheck":
        return cls(type="ask_user")

    @classmethod
    def reject(cls, reason: str) -> "SafetyCheck":
        return cls(type="reject", reason=_ensure_str(reason, "reason"))


ApprovalPolicy = AskForApproval | GranularApprovalConfig


def assess_patch_safety(
    action: ApplyPatchAction | Mapping[str, object],
    policy: ApprovalPolicy,
    permission_profile: PermissionProfile,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str,
    windows_sandbox_level: WindowsSandboxLevel,
) -> SafetyCheck:
    policy = _ensure_policy(policy)
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        raise TypeError("windows_sandbox_level must be a WindowsSandboxLevel")
    action = action if isinstance(action, ApplyPatchAction) else ApplyPatchAction.from_mapping(action)
    cwd = Path(_ensure_pathlike(cwd, "cwd"))

    if not action.changes:
        return SafetyCheck.reject("empty patch")

    if policy is AskForApproval.UNLESS_TRUSTED:
        return SafetyCheck.ask_user()

    rejects_sandbox_approval = policy is AskForApproval.NEVER or (
        isinstance(policy, GranularApprovalConfig) and not policy.allows_sandbox_approval()
    )

    if is_write_patch_constrained_to_writable_paths(action, file_system_sandbox_policy, cwd) or policy is AskForApproval.ON_FAILURE:
        if permission_profile.type in {"disabled", "external"}:
            return SafetyCheck.auto_approve(
                SandboxType.NONE,
                user_explicitly_approved=False,
            )

        sandbox_type = get_platform_sandbox(windows_sandbox_level is not WindowsSandboxLevel.DISABLED)
        if sandbox_type is not None:
            return SafetyCheck.auto_approve(
                sandbox_type,
                user_explicitly_approved=False,
            )
        if rejects_sandbox_approval:
            return SafetyCheck.reject(
                patch_rejection_reason(
                    permission_profile,
                    file_system_sandbox_policy,
                    cwd,
                )
            )
        return SafetyCheck.ask_user()

    if rejects_sandbox_approval:
        return SafetyCheck.reject(
            patch_rejection_reason(
                permission_profile,
                file_system_sandbox_policy,
                cwd,
            )
        )

    return SafetyCheck.ask_user()


def patch_rejection_reason(
    permission_profile: PermissionProfile,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str,
) -> str:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    cwd = Path(_ensure_pathlike(cwd, "cwd"))

    if (
        permission_profile.type == "managed"
        and not file_system_sandbox_policy.has_full_disk_write_access()
        and not file_system_sandbox_policy.get_writable_roots_with_cwd(cwd)
    ):
        return PATCH_REJECTED_READ_ONLY_REASON
    return PATCH_REJECTED_OUTSIDE_PROJECT_REASON


def is_write_patch_constrained_to_writable_paths(
    action: ApplyPatchAction,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str,
) -> bool:
    if not isinstance(action, ApplyPatchAction):
        raise TypeError("action must be an ApplyPatchAction")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    cwd = Path(_ensure_pathlike(cwd, "cwd"))

    def is_path_writable(path: Path) -> bool:
        absolute_path = _normalize_path(resolve_path(cwd, path))
        return file_system_sandbox_policy.can_write_path_with_cwd(absolute_path, cwd)

    for path, change in action.changes.items():
        if change.type in {"add", "delete"}:
            if not is_path_writable(path):
                return False
        elif change.type == "update":
            if not is_path_writable(path):
                return False
            if change.move_path is not None and not is_path_writable(change.move_path):
                return False
    return True


def _normalize_path(path: Path) -> Path:
    anchor = path.anchor
    parts: list[str] = []
    for part in path.parts:
        if part in {"", anchor, "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)

    if anchor:
        result = Path(anchor)
    else:
        result = Path()
    for part in parts:
        result /= part
    return result


__all__ = [
    "PATCH_REJECTED_OUTSIDE_PROJECT_REASON",
    "PATCH_REJECTED_READ_ONLY_REASON",
    "ApprovalPolicy",
    "SafetyCheck",
    "assess_patch_safety",
    "is_write_patch_constrained_to_writable_paths",
    "patch_rejection_reason",
]
