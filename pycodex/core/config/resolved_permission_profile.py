"""Resolved permission profile state ported from Codex core config."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pycodex.protocol import (
    ActivePermissionProfile,
    BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
    PermissionProfile,
)

PermissionProfilePredicate = Callable[[PermissionProfile], bool]


class BuiltInPermissionProfileId(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE = "workspace"
    DANGER_FULL_ACCESS = "danger_full_access"

    @classmethod
    def from_str(cls, profile_id: str) -> "BuiltInPermissionProfileId | None":
        if profile_id == BUILT_IN_PERMISSION_PROFILE_READ_ONLY:
            return cls.READ_ONLY
        if profile_id == BUILT_IN_PERMISSION_PROFILE_WORKSPACE:
            return cls.WORKSPACE
        if profile_id == BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS:
            return cls.DANGER_FULL_ACCESS
        return None

    def as_str(self) -> str:
        if self is BuiltInPermissionProfileId.READ_ONLY:
            return BUILT_IN_PERMISSION_PROFILE_READ_ONLY
        if self is BuiltInPermissionProfileId.WORKSPACE:
            return BUILT_IN_PERMISSION_PROFILE_WORKSPACE
        return BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS


@dataclass(frozen=True)
class ResolvedPermissionProfile:
    kind: str
    permission_profile: PermissionProfile
    active_id: str | None = None
    extends: str | None = None
    profile_workspace_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"legacy", "built_in", "named"}:
            raise ValueError(f"unknown resolved permission profile kind: {self.kind}")
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be a PermissionProfile")
        if self.active_id is not None and not isinstance(self.active_id, str):
            raise TypeError("active_id must be a string")
        if self.extends is not None and not isinstance(self.extends, str):
            raise TypeError("extends must be a string")
        object.__setattr__(
            self,
            "profile_workspace_roots",
            tuple(Path(path) for path in self.profile_workspace_roots),
        )
        if self.kind == "legacy" and self.active_id is not None:
            raise ValueError("legacy resolved permission profile cannot include active_id")
        if self.kind in {"built_in", "named"} and self.active_id is None:
            raise TypeError(f"{self.kind} resolved permission profile requires active_id")

    @classmethod
    def from_active_profile(
        cls,
        permission_profile: PermissionProfile,
        active_permission_profile: ActivePermissionProfile | None,
        profile_workspace_roots: tuple[Path | str, ...] | list[Path | str] = (),
    ) -> "ResolvedPermissionProfile":
        if active_permission_profile is None:
            return cls.legacy(permission_profile)
        if not isinstance(active_permission_profile, ActivePermissionProfile):
            raise TypeError("active_permission_profile must be ActivePermissionProfile or None")
        built_in_id = BuiltInPermissionProfileId.from_str(active_permission_profile.id)
        if built_in_id is not None:
            return cls(
                "built_in",
                permission_profile,
                active_id=built_in_id.as_str(),
                extends=active_permission_profile.extends,
                profile_workspace_roots=tuple(Path(path) for path in profile_workspace_roots),
            )
        return cls(
            "named",
            permission_profile,
            active_id=active_permission_profile.id,
            extends=active_permission_profile.extends,
            profile_workspace_roots=tuple(Path(path) for path in profile_workspace_roots),
        )

    @classmethod
    def legacy(cls, permission_profile: PermissionProfile) -> "ResolvedPermissionProfile":
        return cls("legacy", permission_profile)

    def active_permission_profile(self) -> ActivePermissionProfile | None:
        if self.kind == "legacy":
            return None
        assert self.active_id is not None
        return ActivePermissionProfile(self.active_id, self.extends)


@dataclass(frozen=True)
class PermissionProfileSnapshot:
    resolved_permission_profile: ResolvedPermissionProfile

    @classmethod
    def legacy(cls, permission_profile: PermissionProfile) -> "PermissionProfileSnapshot":
        return cls(ResolvedPermissionProfile.legacy(permission_profile))

    @classmethod
    def active(
        cls,
        permission_profile: PermissionProfile,
        active_permission_profile: ActivePermissionProfile,
    ) -> "PermissionProfileSnapshot":
        return cls.active_with_profile_workspace_roots(
            permission_profile,
            active_permission_profile,
            (),
        )

    @classmethod
    def active_with_profile_workspace_roots(
        cls,
        permission_profile: PermissionProfile,
        active_permission_profile: ActivePermissionProfile,
        profile_workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "PermissionProfileSnapshot":
        return cls(
            ResolvedPermissionProfile.from_active_profile(
                permission_profile,
                active_permission_profile,
                profile_workspace_roots,
            )
        )

    @classmethod
    def from_session_snapshot(
        cls,
        permission_profile: PermissionProfile,
        active_permission_profile: ActivePermissionProfile | None,
    ) -> "PermissionProfileSnapshot":
        if active_permission_profile is None:
            return cls.legacy(permission_profile)
        return cls.active(permission_profile, active_permission_profile)

    def permission_profile(self) -> PermissionProfile:
        return self.resolved_permission_profile.permission_profile

    def active_permission_profile(self) -> ActivePermissionProfile | None:
        return self.resolved_permission_profile.active_permission_profile()

    def profile_workspace_roots(self) -> tuple[Path, ...]:
        return self.resolved_permission_profile.profile_workspace_roots

    def into_resolved_permission_profile(self) -> ResolvedPermissionProfile:
        return self.resolved_permission_profile


@dataclass(frozen=True)
class ConstrainedPermissionProfile:
    value: PermissionProfile
    predicate: PermissionProfilePredicate = lambda _profile: True

    def __post_init__(self) -> None:
        if not isinstance(self.value, PermissionProfile):
            raise TypeError("value must be a PermissionProfile")
        if not callable(self.predicate):
            raise TypeError("predicate must be callable")
        self.can_set(self.value)

    def get(self) -> PermissionProfile:
        return self.value

    def can_set(self, candidate: PermissionProfile) -> None:
        if not isinstance(candidate, PermissionProfile):
            raise TypeError("candidate must be a PermissionProfile")
        if not self.predicate(candidate):
            raise ValueError("permission profile candidate violates constraints")


@dataclass
class PermissionProfileState:
    resolved_permission_profile: ResolvedPermissionProfile
    _predicate: PermissionProfilePredicate

    @classmethod
    def from_constrained_legacy(
        cls,
        constrained_permission_profile: ConstrainedPermissionProfile,
    ) -> "PermissionProfileState":
        resolved = ResolvedPermissionProfile.legacy(constrained_permission_profile.get())
        return cls.from_constrained_resolved(constrained_permission_profile, resolved)

    @classmethod
    def from_constrained_active_profile(
        cls,
        constrained_permission_profile: ConstrainedPermissionProfile,
        active_permission_profile: ActivePermissionProfile | None,
        profile_workspace_roots: tuple[Path | str, ...] | list[Path | str] = (),
    ) -> "PermissionProfileState":
        resolved = ResolvedPermissionProfile.from_active_profile(
            constrained_permission_profile.get(),
            active_permission_profile,
            profile_workspace_roots,
        )
        return cls.from_constrained_resolved(constrained_permission_profile, resolved)

    @classmethod
    def from_constrained_resolved(
        cls,
        constrained_permission_profile: ConstrainedPermissionProfile,
        resolved_permission_profile: ResolvedPermissionProfile,
    ) -> "PermissionProfileState":
        constrained_permission_profile.can_set(resolved_permission_profile.permission_profile)
        return cls(resolved_permission_profile, constrained_permission_profile.predicate)

    def permission_profile(self) -> PermissionProfile:
        return self.resolved_permission_profile.permission_profile

    def active_permission_profile(self) -> ActivePermissionProfile | None:
        return self.resolved_permission_profile.active_permission_profile()

    def profile_workspace_roots(self) -> tuple[Path, ...]:
        return self.resolved_permission_profile.profile_workspace_roots

    def can_set_legacy_permission_profile(self, permission_profile: PermissionProfile) -> None:
        self._can_set_resolved(ResolvedPermissionProfile.legacy(permission_profile))

    def set_legacy_permission_profile(self, permission_profile: PermissionProfile) -> None:
        resolved = ResolvedPermissionProfile.legacy(permission_profile)
        self._can_set_resolved(resolved)
        self.resolved_permission_profile = resolved

    def set_permission_profile_snapshot(self, snapshot: PermissionProfileSnapshot) -> None:
        if not isinstance(snapshot, PermissionProfileSnapshot):
            raise TypeError("snapshot must be a PermissionProfileSnapshot")
        resolved = snapshot.into_resolved_permission_profile()
        self._can_set_resolved(resolved)
        self.resolved_permission_profile = resolved

    def _can_set_resolved(self, resolved: ResolvedPermissionProfile) -> None:
        if not isinstance(resolved, ResolvedPermissionProfile):
            raise TypeError("resolved must be a ResolvedPermissionProfile")
        if not self._predicate(resolved.permission_profile):
            raise ValueError("permission profile candidate violates constraints")


__all__ = [
    "BuiltInPermissionProfileId",
    "ConstrainedPermissionProfile",
    "PermissionProfileSnapshot",
    "PermissionProfileState",
    "ResolvedPermissionProfile",
]
