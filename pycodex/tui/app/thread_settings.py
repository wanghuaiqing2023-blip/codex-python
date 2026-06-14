"""Thread settings sync helpers for Rust ``codex-tui::app::thread_settings``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_settings.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_settings",
    source="codex/codex-rs/tui/src/app/thread_settings.rs",
)


class ModeKind(str, Enum):
    Default = "default"
    Other = "other"


@dataclass(eq=True)
class CollaborationSettings:
    model: str | None = None
    reasoning_effort: Any | None = None


@dataclass(eq=True)
class CollaborationMode:
    mode: ModeKind | str = ModeKind.Default
    settings: CollaborationSettings = field(default_factory=CollaborationSettings)

    def clone_with_thread_settings(self, model: str, effort: Any | None) -> "CollaborationMode":
        return CollaborationMode(
            mode=self.mode,
            settings=CollaborationSettings(model=model, reasoning_effort=effort),
        )


@dataclass(eq=True)
class ThreadSettingsUpdateParams:
    thread_id: str
    cwd: str | None = None
    approval_policy: Any | None = None
    approvals_reviewer: Any | None = None
    sandbox_policy: Any | None = None
    permissions: Any | None = None
    model: str | None = None
    service_tier: str | None = None
    effort: Any | None = None
    summary: Any | None = None
    collaboration_mode: CollaborationMode | None = None
    personality: Any | None = None


@dataclass(eq=True)
class ThreadSessionState:
    model: str
    reasoning_effort: Any | None = None
    model_provider_id: str = ""
    service_tier: str | None = None
    approval_policy: Any | None = None
    approvals_reviewer: Any | None = None
    permission_profile: Any | None = None
    active_permission_profile: Any | None = None
    cwd: str = ""
    runtime_workspace_roots: list[str] = field(default_factory=list)
    personality: Any | None = None
    collaboration_mode: CollaborationMode | None = None


@dataclass(eq=True)
class ThreadSettings:
    model: str
    model_provider: str
    service_tier: str | None
    effort: Any | None
    approval_policy: Any
    approvals_reviewer: Any
    sandbox_policy: Any
    cwd: str
    collaboration_mode: CollaborationMode
    active_permission_profile: Any | None = None
    personality: Any | None = None


def _mode_kind(value: Any) -> str:
    if isinstance(value, ModeKind):
        return value.value
    name = getattr(value, "name", None)
    if name == "Default":
        return ModeKind.Default.value
    return str(value)


def _approval_reviewer_to_core(value: Any) -> Any:
    return value.to_core() if callable(getattr(value, "to_core", None)) else value


def _permission_profile_from_legacy_sandbox_policy_for_cwd(sandbox_policy: Any, cwd: str) -> dict[str, Any]:
    return {"sandbox_policy": sandbox_policy, "cwd": str(cwd)}


def apply_thread_settings_to_session(session: ThreadSessionState, settings: ThreadSettings) -> ThreadSessionState:
    """Mutate and return ``session`` using Rust's settings application rules."""

    if _mode_kind(settings.collaboration_mode.mode) == ModeKind.Default.value:
        session.model = settings.model
        session.reasoning_effort = settings.effort
    session.model_provider_id = settings.model_provider
    session.service_tier = settings.service_tier
    session.approval_policy = settings.approval_policy
    session.approvals_reviewer = _approval_reviewer_to_core(settings.approvals_reviewer)
    session.permission_profile = _permission_profile_from_legacy_sandbox_policy_for_cwd(settings.sandbox_policy, settings.cwd)
    session.active_permission_profile = settings.active_permission_profile
    session.cwd = str(settings.cwd)
    session.runtime_workspace_roots = [str(Path(settings.cwd))]
    session.personality = settings.personality
    session.collaboration_mode = settings.collaboration_mode.clone_with_thread_settings(settings.model, settings.effort)
    return session


def thread_settings_update_has_changes(params: ThreadSettingsUpdateParams) -> bool:
    return any(
        getattr(params, field_name) is not None
        for field_name in (
            "cwd",
            "approval_policy",
            "approvals_reviewer",
            "sandbox_policy",
            "permissions",
            "model",
            "service_tier",
            "effort",
            "summary",
            "collaboration_mode",
            "personality",
        )
    )


async def sync_active_thread_model_setting(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_settings.sync_active_thread_model_setting app-server path is not ported")


async def sync_active_thread_reasoning_setting(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_settings.sync_active_thread_reasoning_setting app-server path is not ported")


async def send_thread_settings_update(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_settings.send_thread_settings_update app-server path is not ported")


__all__ = [
    "CollaborationMode",
    "CollaborationSettings",
    "ModeKind",
    "RUST_MODULE",
    "ThreadSessionState",
    "ThreadSettings",
    "ThreadSettingsUpdateParams",
    "apply_thread_settings_to_session",
    "send_thread_settings_update",
    "sync_active_thread_model_setting",
    "sync_active_thread_reasoning_setting",
    "thread_settings_update_has_changes",
]
