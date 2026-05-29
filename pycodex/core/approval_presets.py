"""Built-in approval presets ported from Codex utils.

This mirrors ``codex-rs/utils/approval-presets/src/lib.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass

from pycodex.protocol import (
    BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
    ActivePermissionProfile,
    AskForApproval,
    PermissionProfile,
)


@dataclass(frozen=True)
class ApprovalPreset:
    id: str
    label: str
    description: str
    approval: AskForApproval
    active_permission_profile: ActivePermissionProfile
    permission_profile: PermissionProfile

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.label, str):
            raise TypeError("label must be a string")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if not isinstance(self.approval, AskForApproval):
            if isinstance(self.approval, str):
                object.__setattr__(self, "approval", AskForApproval(self.approval))
            else:
                raise TypeError("approval must be an AskForApproval")
        if not isinstance(self.active_permission_profile, ActivePermissionProfile):
            raise TypeError("active_permission_profile must be an ActivePermissionProfile")
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be a PermissionProfile")


def builtin_approval_presets() -> tuple[ApprovalPreset, ...]:
    return (
        ApprovalPreset(
            id="read-only",
            label="Read Only",
            description=(
                "Codex can read files in the current workspace. Approval is "
                "required to edit files or access the internet."
            ),
            approval=AskForApproval.ON_REQUEST,
            active_permission_profile=ActivePermissionProfile.new(
                BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
            ),
            permission_profile=PermissionProfile.read_only(),
        ),
        ApprovalPreset(
            id="auto",
            label="Default",
            description=(
                "Codex can read and edit files in the current workspace, and run "
                "commands. Approval is required to access the internet or edit "
                "other files. (Identical to Agent mode)"
            ),
            approval=AskForApproval.ON_REQUEST,
            active_permission_profile=ActivePermissionProfile.new(
                BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
            ),
            permission_profile=PermissionProfile.workspace_write(),
        ),
        ApprovalPreset(
            id="full-access",
            label="Full Access",
            description=(
                "Codex can edit files outside this workspace and access the "
                "internet without asking for approval. Exercise caution when using."
            ),
            approval=AskForApproval.NEVER,
            active_permission_profile=ActivePermissionProfile.new(
                BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
            ),
            permission_profile=PermissionProfile.disabled(),
        ),
    )


def builtin_permission_profile_for_active_permission_profile(
    active_permission_profile: ActivePermissionProfile,
) -> PermissionProfile | None:
    if not isinstance(active_permission_profile, ActivePermissionProfile):
        raise TypeError("active_permission_profile must be an ActivePermissionProfile")
    if active_permission_profile.extends is not None:
        return None

    if active_permission_profile.id == BUILT_IN_PERMISSION_PROFILE_READ_ONLY:
        return PermissionProfile.read_only()
    if active_permission_profile.id == BUILT_IN_PERMISSION_PROFILE_WORKSPACE:
        return PermissionProfile.workspace_write()
    if active_permission_profile.id == BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS:
        return PermissionProfile.disabled()
    return None


__all__ = [
    "ApprovalPreset",
    "builtin_approval_presets",
    "builtin_permission_profile_for_active_permission_profile",
]
