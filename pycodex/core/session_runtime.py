"""Lightweight in-memory core session runtime.

This module provides a minimal session object that implements the session-like
methods used by the core user-turn runtime. It is intentionally small and
transport-agnostic: richer persistence, rollout, UI events, and tool execution
can be layered on later without changing the request/sampling path.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone as utc_timezone
from enum import Enum
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pycodex.core.context import (
    CollaborationModeInstructions,
    EnvironmentContext,
    EnvironmentContextEnvironment,
    NetworkContext,
    PersonalitySpecInstructions,
)
from pycodex.core.context_updates import (
    build_initial_realtime_item,
    build_contextual_user_message,
    build_developer_update_item,
    build_model_instructions_update_item,
    build_settings_update_items,
    personality_message_for,
)
from pycodex.core.features import Feature
from pycodex.core.permissions_instructions import PermissionsInstructions
from pycodex.core.handler_utils import (
    merge_permission_profiles,
    normalize_request_permissions_response,
    record_granted_request_permissions,
)
from pycodex.core.codex_thread import (
    SETTINGS_UNSET,
    CodexThreadSettingsOverrides,
    SessionSettingsUpdate,
    ThreadConfigSnapshot,
)
from pycodex.protocol import (
    AdditionalPermissionProfile,
    ApprovalsReviewer,
    AskForApproval,
    BaseInstructions,
    CollaborationMode,
    CompactedItem,
    FileSystemSandboxPolicy,
    ModeKind,
    PermissionProfile,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    ResponseItem,
    SandboxPolicy,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    ServiceTier,
    Settings,
    TurnContextItem,
    TurnContextNetworkItem,
    TurnEnvironmentSelection,
)

_SETTING_UNSET = SETTINGS_UNSET


@dataclass(frozen=True)
class InMemoryTurnContext:
    """Turn context needed by prompt assembly."""

    cwd: Path
    turn_id: str | None = None
    model_info: Any = None
    user_instructions: str | None = None
    developer_instructions: str | None = None
    config: Any = None
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.disabled)
    approval_policy: Any = AskForApproval.ON_REQUEST
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy.danger_full_access)
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    features: Any = None
    collaboration_mode: Any = None
    realtime_active: bool = False
    personality: Any = None
    reasoning_effort: Any = None
    reasoning_summary: Any = "auto"
    service_tier: Any = None
    current_date: str | None = None
    timezone: str | None = None
    network: Any = None
    environments: Any = None
    final_output_json_schema: Any = None


@dataclass
class InMemoryHistory:
    """Prompt-visible conversation history."""

    items: list[ResponseItem] = field(default_factory=list)

    def for_prompt(self, _modalities: object = None) -> list[ResponseItem]:
        return list(self.items)


@dataclass(frozen=True)
class _ModelInfoWithSlug:
    base: Any
    slug: str

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)


@dataclass
class InMemoryCodexSession:
    """Minimal session-like runtime for core user turns."""

    cwd: Path | str
    turn_id: str | None = None
    model_info: Any = None
    model_provider_id: str = "openai"
    user_instructions: str | None = None
    developer_instructions: str | None = None
    base_instructions: BaseInstructions | str = field(default_factory=BaseInstructions.default)
    workspace_roots: tuple[Path | str, ...] = ()
    profile_workspace_roots: tuple[Path | str, ...] = ()
    active_permission_profile: Any = None
    history: list[ResponseItem] = field(default_factory=list)
    context_updates_recorded: int = 0
    recorded_batches: list[tuple[ResponseItem, ...]] = field(default_factory=list)
    request_permissions_callback: Any = None
    shell: Any = None
    approval_policy: Any = AskForApproval.ON_REQUEST
    approvals_reviewer: ApprovalsReviewer = ApprovalsReviewer.USER
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy.danger_full_access)
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.disabled)
    features: Any = None
    include_environment_context: bool = True
    include_permissions_instructions: bool = True
    include_collaboration_mode_instructions: bool = True
    experimental_realtime_start_instructions: str | None = None
    current_date: str | None = None
    timezone: str | None = None
    network: Any = None
    environments: Any = None
    final_output_json_schema: Any = None
    collaboration_mode: Any = None
    realtime_active: bool = False
    personality: Any = None
    reasoning_effort: Any = None
    reasoning_summary: Any = "auto"
    service_tier: Any = None
    personality_feature_enabled: bool = True
    _granted_session_permissions: AdditionalPermissionProfile | None = None
    _granted_turn_permissions: AdditionalPermissionProfile | None = None
    _reference_context_item: TurnContextItem | None = None
    _previous_turn_settings: Any = None
    _pending_turn_environments: Any = None
    strict_auto_review_enabled: bool = False
    flush_rollout_count: int = 0
    compacted_items: list[CompactedItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cwd = Path(self.cwd)
        if not isinstance(self.base_instructions, BaseInstructions):
            self.base_instructions = BaseInstructions(str(self.base_instructions))
        if not isinstance(self.model_provider_id, str):
            raise TypeError("model_provider_id must be a string")
        self.workspace_roots = _path_tuple(self.workspace_roots)
        self.profile_workspace_roots = _path_tuple(self.profile_workspace_roots)
        self.history = list(self.history)
        if self._granted_session_permissions is not None and not isinstance(
            self._granted_session_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("_granted_session_permissions must be AdditionalPermissionProfile or None")
        if self._granted_turn_permissions is not None and not isinstance(
            self._granted_turn_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("_granted_turn_permissions must be AdditionalPermissionProfile or None")
        if not isinstance(self.strict_auto_review_enabled, bool):
            raise TypeError("strict_auto_review_enabled must be a bool")
        if self.request_permissions_callback is not None and not callable(self.request_permissions_callback):
            raise TypeError("request_permissions_callback must be callable or None")
        if not isinstance(self.approvals_reviewer, ApprovalsReviewer):
            raise TypeError("approvals_reviewer must be ApprovalsReviewer")
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be PermissionProfile")
        if not isinstance(self.sandbox_policy, SandboxPolicy):
            raise TypeError("sandbox_policy must be SandboxPolicy")
        if self.file_system_sandbox_policy is not None and not isinstance(
            self.file_system_sandbox_policy,
            FileSystemSandboxPolicy,
        ):
            raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy or None")
        if not isinstance(self.include_environment_context, bool):
            raise TypeError("include_environment_context must be a bool")
        if not isinstance(self.include_permissions_instructions, bool):
            raise TypeError("include_permissions_instructions must be a bool")
        if not isinstance(self.include_collaboration_mode_instructions, bool):
            raise TypeError("include_collaboration_mode_instructions must be a bool")
        if (
            self.experimental_realtime_start_instructions is not None
            and not isinstance(self.experimental_realtime_start_instructions, str)
        ):
            raise TypeError("experimental_realtime_start_instructions must be a string or None")
        if not isinstance(self.realtime_active, bool):
            raise TypeError("realtime_active must be a bool")
        if self.reasoning_summary is not None and not isinstance(self.reasoning_summary, (str, Enum)):
            raise TypeError("reasoning_summary must be a string, enum, or None")
        if self.service_tier is not None and not isinstance(self.service_tier, (str, Enum)):
            request_value = getattr(self.service_tier, "request_value", None)
            if not callable(request_value):
                raise TypeError("service_tier must be a string, enum, request-value object, or None")
        if not isinstance(self.personality_feature_enabled, bool):
            raise TypeError("personality_feature_enabled must be a bool")
        if not isinstance(self.flush_rollout_count, int):
            raise TypeError("flush_rollout_count must be an int")
        self.compacted_items = list(self.compacted_items)
        if any(not isinstance(item, CompactedItem) for item in self.compacted_items):
            raise TypeError("compacted_items entries must be CompactedItem")

    async def new_default_turn(self) -> InMemoryTurnContext:
        self._granted_turn_permissions = None
        self.strict_auto_review_enabled = False
        final_output_json_schema = self.final_output_json_schema
        self.final_output_json_schema = None
        environments = _default_turn_environments(self.environments, self.cwd)
        if self._pending_turn_environments is not None:
            environments = self._pending_turn_environments
            self._pending_turn_environments = None
        turn_cwd = _turn_cwd(environments, self.cwd)
        collaboration_mode = self.collaboration_mode
        if collaboration_mode is None:
            collaboration_mode = _default_collaboration_mode(self.model_info, self.reasoning_effort)
        model_info = _model_info_for_collaboration_mode(self.model_info, collaboration_mode)
        reasoning_effort = self.reasoning_effort
        if reasoning_effort is None:
            reasoning_effort = _collaboration_mode_reasoning_effort(collaboration_mode)
        current_date, timezone = _turn_local_time_context(self.current_date, self.timezone)
        return InMemoryTurnContext(
            cwd=turn_cwd,
            turn_id=self.turn_id,
            model_info=model_info,
            user_instructions=self.user_instructions,
            developer_instructions=self.developer_instructions,
            config=SimpleNamespace(
                model=_model_slug(model_info),
                include_environment_context=self.include_environment_context,
                include_permissions_instructions=self.include_permissions_instructions,
                approvals_reviewer=self.approvals_reviewer,
                include_collaboration_mode_instructions=self.include_collaboration_mode_instructions,
                experimental_realtime_start_instructions=self.experimental_realtime_start_instructions,
                cwd=turn_cwd,
                service_tier=self.service_tier,
                model_reasoning_effort=reasoning_effort,
                model_reasoning_summary=self.reasoning_summary,
            ),
            permission_profile=self.permission_profile,
            approval_policy=_approval_policy_cell(self.approval_policy),
            sandbox_policy=self.sandbox_policy,
            file_system_sandbox_policy=self.file_system_sandbox_policy,
            features=self.features if self.features is not None else _NoFeatures(),
            collaboration_mode=collaboration_mode,
            realtime_active=self.realtime_active,
            personality=self.personality,
            reasoning_effort=reasoning_effort,
            reasoning_summary=self.reasoning_summary,
            service_tier=self.service_tier,
            current_date=current_date,
            timezone=timezone,
            network=self.network,
            environments=environments,
            final_output_json_schema=final_output_json_schema,
        )

    async def preview_settings(self, updates: Any) -> ThreadConfigSnapshot:
        return self._snapshot_for_settings(updates)

    async def thread_settings_update(self, thread_settings: Any) -> SessionSettingsUpdate:
        overrides = _core_thread_settings_overrides(thread_settings)
        collaboration_mode = overrides.collaboration_mode
        if collaboration_mode is None:
            collaboration_mode = _collaboration_mode_with_settings_updates(
                self.collaboration_mode or _default_collaboration_mode(self.model_info, self.reasoning_effort),
                self.model_info,
                overrides.model,
                overrides.effort,
            )
        return SessionSettingsUpdate(
            cwd=overrides.cwd,
            workspace_roots=overrides.workspace_roots,
            profile_workspace_roots=overrides.profile_workspace_roots,
            approval_policy=overrides.approval_policy,
            approvals_reviewer=overrides.approvals_reviewer,
            sandbox_policy=overrides.sandbox_policy,
            permission_profile=overrides.permission_profile,
            active_permission_profile=overrides.active_permission_profile,
            windows_sandbox_level=overrides.windows_sandbox_level,
            collaboration_mode=collaboration_mode,
            reasoning_summary=overrides.summary,
            service_tier=overrides.service_tier,
            personality=overrides.personality,
        )

    async def preview_thread_settings_overrides(self, thread_settings: Any) -> ThreadConfigSnapshot:
        return await self.preview_settings(await self.thread_settings_update(thread_settings))

    async def apply_thread_settings_overrides(self, thread_settings: Any) -> ThreadConfigSnapshot:
        return await self.update_settings(await self.thread_settings_update(thread_settings))

    async def thread_config_snapshot(self) -> ThreadConfigSnapshot:
        return self._snapshot_for_settings()

    async def update_settings(self, updates: Any) -> ThreadConfigSnapshot:
        snapshot = self._snapshot_for_settings(updates)
        if getattr(updates, "cwd", None) is not None:
            old_cwd = self.cwd
            next_cwd = Path(updates.cwd)
            self.cwd = next_cwd
            if getattr(updates, "workspace_roots", None) is None:
                self.workspace_roots = _retarget_workspace_roots(self.workspace_roots, old_cwd, next_cwd)
        if getattr(updates, "workspace_roots", None) is not None:
            self.workspace_roots = _path_tuple(updates.workspace_roots)
        if getattr(updates, "profile_workspace_roots", None) is not None:
            self.profile_workspace_roots = _path_tuple(updates.profile_workspace_roots)
        if getattr(updates, "environments", None) is not None:
            self._pending_turn_environments = tuple(updates.environments)
        final_output_json_schema_update = _setting_value(updates, "final_output_json_schema")
        if final_output_json_schema_update is not _SETTING_UNSET:
            self.final_output_json_schema = final_output_json_schema_update
        if getattr(updates, "approval_policy", None) is not None:
            self.approval_policy = updates.approval_policy
        if getattr(updates, "approvals_reviewer", None) is not None:
            self.approvals_reviewer = updates.approvals_reviewer
        if getattr(updates, "sandbox_policy", None) is not None:
            self.sandbox_policy = updates.sandbox_policy
        if getattr(updates, "permission_profile", None) is not None:
            self.permission_profile = updates.permission_profile
        if getattr(updates, "active_permission_profile", None) is not None:
            self.active_permission_profile = updates.active_permission_profile
        if getattr(updates, "collaboration_mode", None) is not None:
            self.collaboration_mode = updates.collaboration_mode
            self.reasoning_effort = _collaboration_mode_reasoning_effort(updates.collaboration_mode)
        if getattr(updates, "reasoning_summary", None) is not None:
            self.reasoning_summary = updates.reasoning_summary
        service_tier_update = _setting_value(updates, "service_tier")
        if service_tier_update is not _SETTING_UNSET:
            self.service_tier = _service_tier_request_value(service_tier_update)
        if getattr(updates, "personality", None) is not None:
            self.personality = updates.personality
        return snapshot

    def _snapshot_for_settings(self, updates: Any | None = None) -> ThreadConfigSnapshot:
        collaboration_mode = self.collaboration_mode or _default_collaboration_mode(
            self.model_info,
            self.reasoning_effort,
        )
        reasoning_summary = self.reasoning_summary
        service_tier = self.service_tier
        personality = self.personality
        cwd = self.cwd
        workspace_roots = self.workspace_roots
        profile_workspace_roots = self.profile_workspace_roots
        active_permission_profile = self.active_permission_profile
        approval_policy = self.approval_policy
        approvals_reviewer = self.approvals_reviewer
        sandbox_policy = self.sandbox_policy
        permission_profile = self.permission_profile
        if updates is not None:
            if getattr(updates, "collaboration_mode", None) is not None:
                collaboration_mode = updates.collaboration_mode
            if getattr(updates, "reasoning_summary", None) is not None:
                reasoning_summary = updates.reasoning_summary
            service_tier_update = _setting_value(updates, "service_tier")
            if service_tier_update is not _SETTING_UNSET:
                service_tier = _service_tier_request_value(service_tier_update)
            if getattr(updates, "personality", None) is not None:
                personality = updates.personality
            if getattr(updates, "cwd", None) is not None:
                cwd = Path(updates.cwd)
                if getattr(updates, "workspace_roots", None) is None:
                    workspace_roots = _retarget_workspace_roots(workspace_roots, self.cwd, cwd)
            if getattr(updates, "workspace_roots", None) is not None:
                workspace_roots = _path_tuple(updates.workspace_roots)
            if getattr(updates, "profile_workspace_roots", None) is not None:
                profile_workspace_roots = _path_tuple(updates.profile_workspace_roots)
            if getattr(updates, "approval_policy", None) is not None:
                approval_policy = updates.approval_policy
            if getattr(updates, "approvals_reviewer", None) is not None:
                approvals_reviewer = updates.approvals_reviewer
            if getattr(updates, "sandbox_policy", None) is not None:
                sandbox_policy = updates.sandbox_policy
            if getattr(updates, "permission_profile", None) is not None:
                permission_profile = updates.permission_profile
            if getattr(updates, "active_permission_profile", None) is not None:
                active_permission_profile = updates.active_permission_profile
        model = _collaboration_mode_model(collaboration_mode) or _model_slug(self.model_info)
        reasoning_effort = _collaboration_mode_reasoning_effort(collaboration_mode)
        return ThreadConfigSnapshot(
            model=model,
            model_provider_id=self.model_provider_id,
            service_tier=service_tier,
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=permission_profile,
            active_permission_profile=active_permission_profile,
            cwd=cwd,
            workspace_roots=workspace_roots,
            profile_workspace_roots=profile_workspace_roots,
            reasoning_effort=reasoning_effort,
            reasoning_summary=reasoning_summary,
            personality=personality,
            collaboration_mode=collaboration_mode,
        )

    async def record_context_updates_and_set_reference_context_item(self, turn_context: InMemoryTurnContext) -> None:
        self.context_updates_recorded += 1
        if self._reference_context_item is None:
            items = _build_initial_context_items(
                turn_context,
                _session_shell(self.shell),
                self._previous_turn_settings,
                base_instructions=self.base_instructions,
                personality_feature_enabled=self.personality_feature_enabled,
            )
        else:
            items = build_settings_update_items(
                self._reference_context_item,
                self._previous_turn_settings,
                turn_context,
                personality_feature_enabled=self.personality_feature_enabled,
                shell=_session_shell(self.shell),
            )
        if items:
            await self.record_conversation_items(turn_context, tuple(items))
        self._reference_context_item = _turn_context_item_from_turn_context(turn_context)
        self._previous_turn_settings = SimpleNamespace(
            model=_model_slug(turn_context.model_info),
            realtime_active=turn_context.realtime_active,
        )

    async def reference_context_item(self) -> TurnContextItem | None:
        return self._reference_context_item

    async def set_reference_context_item(self, item: TurnContextItem | None) -> None:
        if item is not None and not isinstance(item, TurnContextItem):
            raise TypeError("item must be TurnContextItem or None")
        self._reference_context_item = item

    async def previous_turn_settings(self) -> Any:
        return self._previous_turn_settings

    async def set_previous_turn_settings(self, previous_turn_settings: Any | None) -> None:
        self._previous_turn_settings = previous_turn_settings

    async def inject_no_new_turn(
        self,
        items: list[ResponseItem | dict[str, Any]] | tuple[ResponseItem | dict[str, Any], ...],
        current_turn_context: InMemoryTurnContext | None,
    ) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("items must be a list or tuple of ResponseItem or mapping")
        turn_context = current_turn_context
        if turn_context is None:
            turn_context = await self.new_default_turn()
        await self.record_conversation_items(
            turn_context,
            tuple(_response_item(item) for item in items),
        )

    async def flush_rollout(self) -> None:
        self.flush_rollout_count += 1

    async def replace_history(
        self,
        items: list[ResponseItem | dict[str, Any]] | tuple[ResponseItem | dict[str, Any], ...],
        reference_context_item: TurnContextItem | None,
    ) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("items must be a list or tuple of ResponseItem or mapping")
        await self.set_reference_context_item(reference_context_item)
        self.history = [_response_item(item) for item in items]

    async def replace_compacted_history(
        self,
        items: list[ResponseItem | dict[str, Any]] | tuple[ResponseItem | dict[str, Any], ...],
        reference_context_item: TurnContextItem | None,
        compacted_item: CompactedItem | dict[str, Any],
    ) -> None:
        compacted = _compacted_item(compacted_item)
        await self.replace_history(items, reference_context_item)
        self.compacted_items.append(compacted)

    async def record_conversation_items(
        self,
        _turn_context: InMemoryTurnContext,
        items: tuple[ResponseItem, ...],
    ) -> None:
        batch = tuple(items)
        self.recorded_batches.append(batch)
        self.history.extend(batch)

    async def clone_history(self) -> InMemoryHistory:
        return InMemoryHistory(list(self.history))

    async def get_base_instructions(self) -> BaseInstructions:
        return self.base_instructions

    async def granted_session_permissions(self) -> AdditionalPermissionProfile | None:
        return self._granted_session_permissions

    async def granted_turn_permissions(self) -> AdditionalPermissionProfile | None:
        return self._granted_turn_permissions

    async def record_granted_permissions(self, permissions: AdditionalPermissionProfile) -> None:
        if not isinstance(permissions, AdditionalPermissionProfile):
            raise TypeError("permissions must be AdditionalPermissionProfile")
        self._granted_session_permissions = merge_permission_profiles(
            self._granted_session_permissions,
            permissions,
        )

    async def record_granted_turn_permissions(self, permissions: AdditionalPermissionProfile) -> None:
        if not isinstance(permissions, AdditionalPermissionProfile):
            raise TypeError("permissions must be AdditionalPermissionProfile")
        self._granted_turn_permissions = merge_permission_profiles(
            self._granted_turn_permissions,
            permissions,
        )

    async def enable_strict_auto_review(self) -> None:
        self.strict_auto_review_enabled = True

    async def strict_auto_review(self) -> bool:
        return self.strict_auto_review_enabled

    async def request_permissions_for_cwd(
        self,
        parent_ctx: Any,
        call_id: str,
        args: RequestPermissionsArgs,
        cwd: Path | str | None,
        cancel_token: Any = None,
    ) -> RequestPermissionsResponse:
        if not isinstance(args, RequestPermissionsArgs):
            raise TypeError("args must be RequestPermissionsArgs")
        if self.request_permissions_callback is None:
            return RequestPermissionsResponse(RequestPermissionProfile())
        effective_cwd = Path(cwd) if cwd is not None else self.cwd
        response = self.request_permissions_callback(parent_ctx, call_id, args, effective_cwd, cancel_token)
        if inspect.isawaitable(response):
            response = await response
        if response is None:
            return RequestPermissionsResponse(RequestPermissionProfile())
        if not isinstance(response, RequestPermissionsResponse):
            response = RequestPermissionsResponse.from_mapping(response)
        normalized = normalize_request_permissions_response(args.permissions, response, effective_cwd)
        await record_granted_request_permissions(normalized, session=self, turn_state=self)
        return normalized


__all__ = [
    "InMemoryCodexSession",
    "InMemoryHistory",
    "InMemoryTurnContext",
]


class _NoFeatures:
    def enabled(self, _feature: Any) -> bool:
        return False


class _ApprovalCell:
    def __init__(self, value: AskForApproval) -> None:
        self._value = value

    def value(self) -> AskForApproval:
        return self._value


def _approval_policy_cell(value: Any) -> _ApprovalCell:
    if isinstance(value, _ApprovalCell):
        return value
    method = getattr(value, "value", None)
    if callable(method):
        value = method()
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return _ApprovalCell(value)


def _session_shell(shell: Any) -> Any:
    return shell if shell is not None else SimpleNamespace(name=lambda: "")


def _model_slug(model_info: Any) -> str:
    slug = getattr(model_info, "slug", None)
    return str(slug) if slug is not None else ""


def _default_collaboration_mode(model_info: Any, reasoning_effort: Any = None) -> CollaborationMode:
    return CollaborationMode(
        mode=ModeKind.DEFAULT,
        settings=Settings(model=_model_slug(model_info), reasoning_effort=reasoning_effort),
    )


def _service_tier_request_value(service_tier: Any) -> Any:
    if service_tier is None:
        return SERVICE_TIER_DEFAULT_REQUEST_VALUE
    request_value = getattr(service_tier, "request_value", None)
    if callable(request_value):
        return request_value()
    if isinstance(service_tier, str):
        parsed = ServiceTier.from_request_value(service_tier)
        return parsed.request_value() if parsed is not None else service_tier
    if isinstance(service_tier, Enum):
        return service_tier.value
    return service_tier


def _core_thread_settings_overrides(value: Any) -> CodexThreadSettingsOverrides:
    if isinstance(value, CodexThreadSettingsOverrides):
        return value
    return CodexThreadSettingsOverrides.from_thread_settings_overrides(value)


def _collaboration_mode_with_settings_updates(
    collaboration_mode: Any,
    model_info: Any,
    model: str | None,
    effort: Any,
) -> Any:
    updater = getattr(collaboration_mode, "with_updates", None)
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if effort is not _SETTING_UNSET:
        kwargs["effort"] = effort
    if callable(updater):
        try:
            return updater(**kwargs)
        except TypeError:
            legacy_effort = None if effort is _SETTING_UNSET else effort
            return updater(model, legacy_effort, None)
    settings = getattr(collaboration_mode, "settings", None)
    next_model = model if model is not None else _collaboration_mode_model(collaboration_mode) or _model_slug(model_info)
    next_effort = _collaboration_mode_reasoning_effort(collaboration_mode) if effort is _SETTING_UNSET else effort
    developer_instructions = getattr(settings, "developer_instructions", None)
    return CollaborationMode(
        mode=getattr(collaboration_mode, "mode", ModeKind.DEFAULT),
        settings=Settings(
            model=next_model,
            reasoning_effort=next_effort,
            developer_instructions=developer_instructions,
        ),
    )


def _setting_value(updates: Any, name: str) -> Any:
    return getattr(updates, name, _SETTING_UNSET)


def _path_tuple(paths: Any) -> tuple[Path, ...]:
    if paths is None:
        return ()
    if isinstance(paths, (str, bytes, Path)):
        raise TypeError("paths must be an iterable of paths")
    return tuple(Path(path) for path in paths)


def _default_turn_environments(value: Any, cwd: Path | str) -> Any:
    if value is None:
        return None
    environments = tuple(value)
    if not environments:
        return environments
    primary = environments[0]
    if not isinstance(primary, TurnEnvironmentSelection):
        return environments
    cwd_path = Path(cwd)
    if primary.cwd == cwd_path:
        return environments
    return (TurnEnvironmentSelection(primary.environment_id, cwd_path), *environments[1:])


def _turn_local_time_context(
    current_date: str | None,
    timezone_name: str | None,
) -> tuple[str, str]:
    resolved_date, resolved_timezone = _local_time_context()
    return (
        current_date if current_date is not None else resolved_date,
        timezone_name if timezone_name is not None else resolved_timezone,
    )


def _local_time_context() -> tuple[str, str]:
    try:
        local_now = datetime.now().astimezone()
        tzinfo = local_now.tzinfo
        timezone_name = getattr(tzinfo, "key", None) or getattr(tzinfo, "zone", None) or local_now.tzname()
        if not timezone_name:
            raise ValueError("local timezone name is unavailable")
        return local_now.strftime("%Y-%m-%d"), str(timezone_name)
    except Exception:
        utc_now = datetime.now(utc_timezone.utc)
        return utc_now.strftime("%Y-%m-%d"), "Etc/UTC"


def _turn_cwd(environments: Any, fallback: Path | str) -> Path:
    if environments:
        primary = tuple(environments)[0]
        primary_cwd = getattr(primary, "cwd", None)
        if primary_cwd is not None:
            return Path(primary_cwd)
    return Path(fallback)


def _retarget_workspace_roots(roots: tuple[Path, ...], old_cwd: Path, new_cwd: Path) -> tuple[Path, ...]:
    if old_cwd not in roots:
        return roots
    retargeted: list[Path] = []
    for root in roots:
        next_root = new_cwd if root == old_cwd else root
        if next_root not in retargeted:
            retargeted.append(next_root)
    return tuple(retargeted)


def _model_info_for_collaboration_mode(model_info: Any, collaboration_mode: Any) -> Any:
    model = _collaboration_mode_model(collaboration_mode)
    if not model or model == _model_slug(model_info):
        return model_info
    return _ModelInfoWithSlug(base=model_info, slug=model)


def _collaboration_mode_model(collaboration_mode: Any) -> str | None:
    settings = _collaboration_mode_settings(collaboration_mode)
    if settings is None:
        return None
    if isinstance(settings, Mapping):
        model = settings.get("model")
    else:
        model = getattr(settings, "model", None)
    return str(model) if model is not None else None


def _collaboration_mode_reasoning_effort(collaboration_mode: Any) -> Any:
    settings = _collaboration_mode_settings(collaboration_mode)
    if settings is None:
        return None
    if isinstance(settings, Mapping):
        return settings.get("reasoning_effort")
    return getattr(settings, "reasoning_effort", None)


def _collaboration_mode_settings(collaboration_mode: Any) -> Any:
    if isinstance(collaboration_mode, Mapping):
        return collaboration_mode.get("settings")
    return getattr(collaboration_mode, "settings", None)


def _turn_context_item_from_turn_context(turn_context: InMemoryTurnContext) -> TurnContextItem:
    approval_policy = turn_context.approval_policy
    value = approval_policy.value() if callable(getattr(approval_policy, "value", None)) else approval_policy
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return TurnContextItem(
        turn_id=turn_context.turn_id,
        cwd=Path(turn_context.cwd),
        approval_policy=value,
        sandbox_policy=turn_context.sandbox_policy,
        model=_model_slug(turn_context.model_info),
        current_date=turn_context.current_date,
        timezone=turn_context.timezone,
        permission_profile_value=turn_context.permission_profile,
        network=_turn_context_network_item(turn_context.network),
        file_system_sandbox_policy=turn_context.file_system_sandbox_policy,
        personality=turn_context.personality,
        collaboration_mode=_turn_context_collaboration_mode(turn_context.collaboration_mode),
        realtime_active=turn_context.realtime_active,
        effort=_wire_value(turn_context.reasoning_effort),
        summary="auto",
    )


def _build_initial_context_items(
    turn_context: InMemoryTurnContext,
    shell: Any,
    previous_turn_settings: Any | None,
    *,
    base_instructions: BaseInstructions,
    personality_feature_enabled: bool,
) -> list[ResponseItem]:
    config = turn_context.config
    developer_sections: list[str] = []
    model_switch_message = build_model_instructions_update_item(previous_turn_settings, turn_context)
    if model_switch_message is not None:
        developer_sections.append(model_switch_message)
    if getattr(config, "include_permissions_instructions", False):
        developer_sections.append(
            PermissionsInstructions.from_permission_profile(
                turn_context.permission_profile,
                _approval_policy_cell(turn_context.approval_policy).value(),
                getattr(config, "approvals_reviewer", ApprovalsReviewer.USER),
                None,
                turn_context.cwd,
                _feature_enabled(turn_context.features, Feature.EXEC_PERMISSION_APPROVALS),
                _feature_enabled(turn_context.features, Feature.REQUEST_PERMISSIONS_TOOL),
            ).render()
        )
    if turn_context.developer_instructions:
        developer_sections.append(str(turn_context.developer_instructions))
    if getattr(config, "include_collaboration_mode_instructions", False):
        collaboration = CollaborationModeInstructions.from_collaboration_mode(turn_context.collaboration_mode)
        if collaboration is not None:
            developer_sections.append(collaboration.render())
    realtime_message = build_initial_realtime_item(None, previous_turn_settings, turn_context)
    if realtime_message is not None:
        developer_sections.append(realtime_message)
    if personality_feature_enabled and turn_context.personality is not None:
        model_info = turn_context.model_info
        has_baked_personality = _supports_personality(model_info) and (
            _base_instructions_text(base_instructions)
            == _model_instructions(model_info, turn_context.personality)
        )
        if not has_baked_personality:
            personality_message = personality_message_for(model_info, turn_context.personality)
            if personality_message is not None:
                developer_sections.append(PersonalitySpecInstructions.new(personality_message).render())

    contextual_user_sections: list[str] = []
    if getattr(config, "include_environment_context", False):
        contextual_user_sections.append(
            EnvironmentContext.new(
                _environment_context_environments(turn_context, _shell_name(shell)),
                current_date=turn_context.current_date,
                timezone=turn_context.timezone,
                network=_network_context(turn_context.network),
            ).render()
        )

    items: list[ResponseItem] = []
    developer_message = build_developer_update_item(developer_sections)
    if developer_message is not None:
        items.append(developer_message)
    contextual_user_message = build_contextual_user_message(contextual_user_sections)
    if contextual_user_message is not None:
        items.append(contextual_user_message)
    return items


def _response_item(value: ResponseItem | dict[str, Any]) -> ResponseItem:
    if isinstance(value, ResponseItem):
        return value
    if isinstance(value, dict):
        return ResponseItem.from_mapping(value)
    raise TypeError("items entries must be ResponseItem or mapping")


def _compacted_item(value: CompactedItem | dict[str, Any]) -> CompactedItem:
    if isinstance(value, CompactedItem):
        return value
    if isinstance(value, dict):
        return CompactedItem.from_mapping(value)
    raise TypeError("compacted_item must be CompactedItem or mapping")


def _shell_name(shell: Any) -> str:
    name = getattr(shell, "name", None)
    value = name() if callable(name) else name
    return str(value if value is not None else shell)


def _environment_context_environments(
    turn_context: InMemoryTurnContext,
    shell_name: str,
) -> tuple[EnvironmentContextEnvironment, ...]:
    environments = getattr(turn_context, "environments", None)
    if environments is None:
        return (EnvironmentContextEnvironment.legacy(turn_context.cwd, shell_name),)
    candidates = getattr(environments, "turn_environments", environments)
    if candidates is None:
        return (EnvironmentContextEnvironment.legacy(turn_context.cwd, shell_name),)
    items = tuple(candidates)
    if not items:
        return ()
    result: list[EnvironmentContextEnvironment] = []
    for item in items:
        cwd = getattr(item, "cwd", turn_context.cwd)
        item_shell = getattr(item, "shell", None) or shell_name
        environment_id = getattr(item, "environment_id", None)
        if environment_id is None:
            environment_id = getattr(item, "id", "")
        result.append(EnvironmentContextEnvironment(str(environment_id), Path(cwd), str(item_shell)))
    return tuple(result)


def _feature_enabled(features: Any, feature: Feature) -> bool:
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        result = enabled(feature)
        if not isinstance(result, bool):
            raise TypeError("features.enabled() must return a bool")
        return result
    if isinstance(features, dict):
        return bool(features.get(feature, features.get(feature.value, False)))
    return False if features is None else feature in features


def _network_context(network: Any) -> NetworkContext | None:
    if network is None:
        return None
    if isinstance(network, NetworkContext):
        return network
    return NetworkContext(
        allowed_domains=tuple(getattr(network, "allowed_domains", ())),
        denied_domains=tuple(getattr(network, "denied_domains", ())),
    )


def _turn_context_network_item(network: Any) -> TurnContextNetworkItem | None:
    if network is None:
        return None
    if isinstance(network, TurnContextNetworkItem):
        return network
    return TurnContextNetworkItem(
        allowed_domains=tuple(getattr(network, "allowed_domains", ())),
        denied_domains=tuple(getattr(network, "denied_domains", ())),
    )


def _turn_context_collaboration_mode(collaboration_mode: Any) -> Any:
    if collaboration_mode is None:
        return None
    return _jsonish(collaboration_mode)


def _wire_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _jsonish(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return _jsonish(to_mapping())
    if isinstance(value, Mapping):
        return {str(key): _jsonish(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonish(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _jsonish(getattr(value, field.name))
            for field in fields(value)
            if getattr(value, field.name) is not None
        }
    if hasattr(value, "__dict__"):
        return {
            str(key): _jsonish(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _supports_personality(model_info: Any) -> bool:
    supports = getattr(model_info, "supports_personality", None)
    if not callable(supports):
        return False
    result = supports()
    if not isinstance(result, bool):
        raise TypeError("model_info.supports_personality() must return a bool")
    return result


def _model_instructions(model_info: Any, personality: Any) -> str:
    getter = getattr(model_info, "get_model_instructions", None)
    if not callable(getter):
        return ""
    value = getter(personality)
    return value if isinstance(value, str) else str(value)


def _base_instructions_text(base_instructions: BaseInstructions) -> str:
    text = getattr(base_instructions, "text", None)
    return text if isinstance(text, str) else str(base_instructions)
