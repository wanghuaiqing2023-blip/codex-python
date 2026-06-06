"""Lightweight in-memory core session runtime.

This module provides a minimal session object that implements the session-like
methods used by the core user-turn runtime. It is intentionally small and
transport-agnostic: richer persistence, rollout, UI events, and tool execution
can be layered on later without changing the request/sampling path.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field, fields, is_dataclass, replace
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
    UserInstructions,
)
from pycodex.core.context_manager.updates import (
    build_initial_realtime_item,
    build_contextual_user_message,
    build_developer_update_item,
    build_model_instructions_update_item,
    build_settings_update_items,
    personality_message_for,
)
from pycodex.features import Feature
from pycodex.core.event_mapping import parse_turn_item
from pycodex.core.context.permissions_instructions import PermissionsInstructions
from pycodex.core.tools.handlers.utils import (
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
from pycodex.core.compact_remote import normalize_history_for_prompt
from pycodex.core.context_manager.history import (
    process_history_item as _context_manager_process_history_item,
    process_history_items as _context_manager_process_history_items,
)
from pycodex.core.state.session import SessionState
from pycodex.core.state.turn import PendingRequestPermissions
from pycodex.core.session.turn.prompt import is_guardian_reviewer_source
from pycodex.core.unified_exec import UnifiedExecProcessManager
from pycodex.protocol import (
    AdditionalPermissionProfile,
    ApprovalsReviewer,
    AskForApproval,
    BaseInstructions,
    CodexErrorInfo,
    CollaborationMode,
    CompactedItem,
    FileSystemSandboxPolicy,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    GranularApprovalConfig,
    InterAgentCommunication,
    ModeKind,
    PermissionProfile,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsEvent,
    RequestPermissionsResponse,
    ResponseInputItem,
    ResponseItem,
    EventMsg,
    ItemCompletedEvent,
    ItemStartedEvent,
    ModelRerouteEvent,
    ModelRerouteReason,
    ModelVerificationEvent,
    RateLimitSnapshot,
    SandboxEnforcement,
    SandboxPolicy,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    SessionSource,
    ServiceTier,
    Settings,
    TokenCountEvent,
    TruncationPolicyConfig,
    TokenUsage,
    TokenUsageInfo,
    TurnContextItem,
    TurnContextNetworkItem,
    TurnEnvironmentSelection,
    TurnItem,
    UserInput,
    UserMessageItem,
    WarningEvent,
)

_SETTING_UNSET = SETTINGS_UNSET
CYBER_VERIFY_URL = "https://chatgpt.com/cyber"
CYBER_SAFETY_URL = "https://developers.openai.com/codex/concepts/cyber-safety"


def _default_services() -> SimpleNamespace:
    return SimpleNamespace(unified_exec_manager=UnifiedExecProcessManager())


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
    server_model_warning_emitted: bool = False
    model_verification_emitted: bool = False
    truncation_policy: TruncationPolicyConfig = field(default_factory=lambda: TruncationPolicyConfig.tokens(10_000))
    session_source: SessionSource = field(default_factory=SessionSource.default)


@dataclass
class InMemoryHistory:
    """Prompt-visible conversation history."""

    items: list[ResponseItem] = field(default_factory=list)

    def for_prompt(self, modalities: object = None) -> list[ResponseItem]:
        return list(normalize_history_for_prompt(self.items, modalities))


@dataclass
class InMemoryActiveTurnState:
    tool_calls: int = 0
    pending_request_permissions: dict[str, PendingRequestPermissions] = field(default_factory=dict)


@dataclass
class InMemoryActiveTurn:
    turn_state: InMemoryActiveTurnState = field(default_factory=InMemoryActiveTurnState)


@dataclass
class InMemoryInputQueue:
    """Turn-local pending input queue for the in-memory session runtime."""

    items: list[Any] = field(default_factory=list)
    mailbox_pending_mails: list[InterAgentCommunication] = field(default_factory=list)
    mailbox_subscribers: list[Any] = field(default_factory=list)

    async def extend_pending_input(self, items: Any) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("pending input must be a list or tuple")
        self.items.extend(items)

    async def enqueue_mailbox_communication(self, communication: InterAgentCommunication) -> None:
        if not isinstance(communication, InterAgentCommunication):
            communication = InterAgentCommunication.from_mapping(communication)
        self.mailbox_pending_mails.append(communication)
        for subscriber in tuple(self.mailbox_subscribers):
            subscriber.mark_changed()

    async def subscribe_mailbox(self) -> Any:
        subscriber = _InMemoryMailboxSubscription()
        self.mailbox_subscribers.append(subscriber)
        if self.mailbox_pending_mails:
            subscriber.mark_changed()
        return subscriber

    async def has_pending_mailbox_items(self) -> bool:
        return bool(self.mailbox_pending_mails)

    async def has_trigger_turn_mailbox_items(self) -> bool:
        return any(mail.trigger_turn for mail in self.mailbox_pending_mails)

    async def drain_mailbox_input_items(self) -> tuple[ResponseItem, ...]:
        pending = tuple(self.mailbox_pending_mails)
        self.mailbox_pending_mails.clear()
        return tuple(ResponseItem.from_response_input_item(mail.to_response_input_item()) for mail in pending)

    async def accept_mailbox_delivery_for_turn_state(self, turn_state: Any) -> None:
        accept = getattr(turn_state, "accept_mailbox_delivery_for_current_turn")
        accept()

    async def extend_pending_input_for_turn_state(self, turn_state: Any, items: Any) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("pending input must be a list or tuple")
        pending = _turn_state_pending_input_items(turn_state)
        pending.extend(items)

    async def extend_pending_input_and_accept_mailbox_delivery_for_turn_state(self, turn_state: Any, items: Any) -> None:
        await self.extend_pending_input_for_turn_state(turn_state, items)
        await self.accept_mailbox_delivery_for_turn_state(turn_state)

    async def take_pending_input_for_turn_state(self, turn_state: Any) -> tuple[Any, ...]:
        pending = _turn_state_pending_input_items(turn_state)
        items = tuple(pending)
        pending.clear()
        return items

    async def turn_state_for_sub_id(self, active_turn: Any, sub_id: str) -> Any | None:
        active = _active_turn_value(active_turn)
        if active is None:
            return None
        task = getattr(active, "task", None)
        turn_context = getattr(task, "turn_context", None)
        if getattr(turn_context, "sub_id", None) != sub_id:
            return None
        return getattr(active, "turn_state", None)

    async def clear_pending(self, active_turn: Any) -> None:
        active = _active_turn_value(active_turn)
        if active is None:
            return
        turn_state = getattr(active, "turn_state", None)
        if turn_state is None:
            return
        clear_pending_waiters = getattr(turn_state, "clear_pending_waiters", None)
        if callable(clear_pending_waiters):
            clear_pending_waiters()
        _turn_state_pending_input_items(turn_state).clear()

    async def defer_mailbox_delivery_to_next_turn(self, active_turn: Any, sub_id: str) -> None:
        turn_state = await self.turn_state_for_sub_id(active_turn, sub_id)
        if turn_state is None:
            return
        if _turn_state_pending_input_items(turn_state):
            return
        setter = getattr(turn_state, "set_mailbox_delivery_phase", None)
        if callable(setter):
            setter("next_turn")

    async def accept_mailbox_delivery_for_current_turn(self, active_turn: Any, sub_id: str) -> None:
        turn_state = await self.turn_state_for_sub_id(active_turn, sub_id)
        if turn_state is not None:
            await self.accept_mailbox_delivery_for_turn_state(turn_state)

    async def get_pending_input(self, active_turn: Any = None) -> tuple[Any, ...]:
        turn_state = _active_turn_state(active_turn)
        if turn_state is None:
            items = tuple(self.items)
            self.items.clear()
            if self.mailbox_pending_mails:
                items = items + tuple(await self.drain_mailbox_input_items())
            return items

        pending = _turn_state_pending_input_items(turn_state)
        items = tuple(pending)
        pending.clear()
        accepts_mailbox = _accepts_mailbox_delivery_for_current_turn(turn_state)
        if accepts_mailbox and self.mailbox_pending_mails:
            items = items + tuple(await self.drain_mailbox_input_items())
        return items

    async def has_pending_input(self, active_turn: Any = None) -> bool:
        turn_state = _active_turn_state(active_turn)
        if turn_state is None:
            return bool(self.items) or bool(self.mailbox_pending_mails)
        pending = _turn_state_pending_input_items(turn_state)
        if pending:
            return True
        return _accepts_mailbox_delivery_for_current_turn(turn_state) and bool(self.mailbox_pending_mails)


def _turn_state_pending_input_items(turn_state: Any) -> list[Any]:
    pending_input = getattr(turn_state, "pending_input", None)
    if pending_input is None:
        pending_input = SimpleNamespace(items=[])
        setattr(turn_state, "pending_input", pending_input)
    items = getattr(pending_input, "items", None)
    if items is None:
        items = []
        setattr(pending_input, "items", items)
    if not isinstance(items, list):
        raise TypeError("turn_state.pending_input.items must be a list")
    return items


class _InMemoryMailboxSubscription:
    def __init__(self) -> None:
        self._changed = asyncio.Event()

    def mark_changed(self) -> None:
        self._changed.set()

    async def changed(self) -> None:
        await self._changed.wait()
        self._changed.clear()

    def has_changed(self) -> bool:
        return self._changed.is_set()


def _active_turn_state(active_turn: Any) -> Any | None:
    active_turn = _active_turn_value(active_turn)
    if active_turn is None:
        return None
    if hasattr(active_turn, "turn_state"):
        return getattr(active_turn, "turn_state")
    return active_turn


def _active_turn_value(active_turn: Any) -> Any | None:
    if active_turn is None:
        return None
    value = getattr(active_turn, "value", active_turn)
    if callable(value):
        value = value()
    return value


def _accepts_mailbox_delivery_for_current_turn(turn_state: Any) -> bool:
    accepts = getattr(turn_state, "accepts_mailbox_delivery_for_current_turn", None)
    if callable(accepts):
        return bool(accepts())
    return True


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
    thread_id: str = "thread"
    turn_id: str | None = None
    model_info: Any = None
    model_provider_id: str = "openai"
    services: Any = field(default_factory=_default_services)
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
    request_permissions_event_roundtrip_enabled: bool = False
    shell: Any = None
    approval_policy: Any = AskForApproval.ON_REQUEST
    approvals_reviewer: ApprovalsReviewer = ApprovalsReviewer.USER
    sandbox_policy: SandboxPolicy = field(default_factory=SandboxPolicy.danger_full_access)
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    permission_profile: PermissionProfile = field(default_factory=PermissionProfile.disabled)
    allow_login_shell: bool = False
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
    session_source: SessionSource = field(default_factory=SessionSource.default)
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
    _next_turn_is_first: bool = True
    _pending_turn_environments: Any = None
    strict_auto_review_enabled: bool = False
    flush_rollout_count: int = 0
    compacted_items: list[CompactedItem] = field(default_factory=list)
    token_usage_info: TokenUsageInfo | None = None
    latest_rate_limits: RateLimitSnapshot | None = None
    server_reasoning_included: bool = False
    models_etag: str | None = None
    emitted_events: list[EventMsg] = field(default_factory=list)
    input_queue: InMemoryInputQueue = field(default_factory=InMemoryInputQueue)
    active_turn: InMemoryActiveTurn = field(default_factory=InMemoryActiveTurn)
    response_processed_ids: list[str] = field(default_factory=list)
    drain_in_flight_count: int = 0
    unified_diff: str | None = None
    loop_tail_calls: list[Any] = field(default_factory=list)
    turn_error_lifecycle: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cwd = Path(self.cwd)
        if not isinstance(self.thread_id, str):
            raise TypeError("thread_id must be a string")
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
        if not isinstance(self.request_permissions_event_roundtrip_enabled, bool):
            raise TypeError("request_permissions_event_roundtrip_enabled must be a bool")
        if not isinstance(self.approvals_reviewer, ApprovalsReviewer):
            raise TypeError("approvals_reviewer must be ApprovalsReviewer")
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be PermissionProfile")
        if not isinstance(self.allow_login_shell, bool):
            raise TypeError("allow_login_shell must be a bool")
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
        self.emitted_events = list(self.emitted_events)
        if not isinstance(self.input_queue, InMemoryInputQueue):
            raise TypeError("input_queue must be InMemoryInputQueue")
        if not isinstance(self.active_turn, InMemoryActiveTurn):
            raise TypeError("active_turn must be InMemoryActiveTurn")
        self.response_processed_ids = list(self.response_processed_ids)
        if not isinstance(self.drain_in_flight_count, int):
            raise TypeError("drain_in_flight_count must be an int")
        if self.unified_diff is not None and not isinstance(self.unified_diff, str):
            raise TypeError("unified_diff must be a string or None")
        self.loop_tail_calls = list(self.loop_tail_calls)
        self.turn_error_lifecycle = list(self.turn_error_lifecycle)

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
                permissions=SimpleNamespace(allow_login_shell=self.allow_login_shell),
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
            truncation_policy=_turn_truncation_policy(model_info),
            session_source=self.session_source,
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
        if (
            getattr(updates, "permission_profile", None) is not None
            or getattr(updates, "sandbox_policy", None) is not None
        ):
            self.permission_profile = snapshot.permission_profile
            self.file_system_sandbox_policy = snapshot.file_system_sandbox_policy
            sandbox_policy = snapshot.sandbox_policy()
            if sandbox_policy is None:
                sandbox_policy = getattr(updates, "sandbox_policy", None)
            if sandbox_policy is not None:
                self.sandbox_policy = sandbox_policy
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
                if getattr(updates, "permission_profile", None) is None:
                    permission_profile = _permission_profile_from_sandbox_policy(
                        sandbox_policy,
                        permission_profile,
                        cwd,
                    )
            if getattr(updates, "permission_profile", None) is not None:
                permission_profile = updates.permission_profile
            if getattr(updates, "active_permission_profile", None) is not None:
                active_permission_profile = updates.active_permission_profile
        model = _collaboration_mode_model(collaboration_mode) or _model_slug(self.model_info)
        reasoning_effort = _collaboration_mode_reasoning_effort(collaboration_mode)
        file_system_sandbox_policy = _file_system_sandbox_policy_from_permission_profile(permission_profile)
        return ThreadConfigSnapshot(
            model=model,
            model_provider_id=self.model_provider_id,
            service_tier=service_tier,
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=permission_profile,
            active_permission_profile=active_permission_profile,
            file_system_sandbox_policy=file_system_sandbox_policy,
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
        return self._session_state_snapshot().previous_turn_settings()

    async def set_previous_turn_settings(self, previous_turn_settings: Any | None) -> None:
        state = self._session_state_snapshot()
        state.set_previous_turn_settings(previous_turn_settings)
        self._previous_turn_settings = state.previous_turn_settings()

    async def set_next_turn_is_first(self, value: bool) -> None:
        state = self._session_state_snapshot()
        state.set_next_turn_is_first(value)
        self._next_turn_is_first = value

    async def take_next_turn_is_first(self) -> bool:
        state = self._session_state_snapshot()
        is_first_turn = state.take_next_turn_is_first()
        self._next_turn_is_first = False
        return is_first_turn

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

    async def inject_if_running(self, items: list[Any] | tuple[Any, ...]) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("items must be a list or tuple")
        await self.input_queue.extend_pending_input(tuple(_pending_input_item(item) for item in items))

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
        turn_context: InMemoryTurnContext,
        items: tuple[ResponseItem, ...],
    ) -> None:
        batch = tuple(items)
        self.recorded_batches.append(batch)
        self.history.extend(_process_history_items(batch, _turn_truncation_policy_from_context(turn_context)))

    async def emit_turn_item_started(self, turn_context: InMemoryTurnContext, item: TurnItem) -> None:
        if not isinstance(item, TurnItem):
            item = TurnItem.from_mapping(item)
        await self.send_event(
            turn_context,
            EventMsg.with_payload(
                "item_started",
                ItemStartedEvent(
                    self.thread_id,
                    _turn_id_for_event(turn_context),
                    item,
                    _now_unix_timestamp_ms(),
                ),
            ),
        )

    async def emit_turn_item_completed(self, turn_context: InMemoryTurnContext, item: TurnItem) -> None:
        if not isinstance(item, TurnItem):
            item = TurnItem.from_mapping(item)
        await self.send_event(
            turn_context,
            EventMsg.with_payload(
                "item_completed",
                ItemCompletedEvent(
                    self.thread_id,
                    _turn_id_for_event(turn_context),
                    item,
                    _now_unix_timestamp_ms(),
                ),
            ),
        )

    async def record_user_prompt_and_emit_turn_item(
        self,
        turn_context: InMemoryTurnContext,
        input: tuple[UserInput, ...] | list[UserInput],
    ) -> None:
        user_input = tuple(item if isinstance(item, UserInput) else UserInput.from_mapping(item) for item in input)
        response_item = ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(user_input))
        await self.record_conversation_items(turn_context, (response_item,))
        turn_item = TurnItem.user_message(UserMessageItem.new(user_input))
        await self.emit_turn_item_started(turn_context, turn_item)
        await self.emit_turn_item_completed(turn_context, turn_item)

    async def record_response_item_and_emit_turn_item(
        self,
        turn_context: InMemoryTurnContext,
        response_item: ResponseItem,
    ) -> None:
        if not isinstance(response_item, ResponseItem):
            response_item = ResponseItem.from_mapping(response_item)
        await self.record_conversation_items(turn_context, (response_item,))
        turn_item = parse_turn_item(response_item)
        if turn_item is None:
            return
        await self.emit_turn_item_started(turn_context, turn_item)
        await self.emit_turn_item_completed(turn_context, turn_item)

    def _session_state_snapshot(self) -> SessionState:
        state = SessionState.new()
        state.replace_history(tuple(self.history), self._reference_context_item)
        state.set_token_info(self.token_usage_info)
        state.latest_rate_limits = self.latest_rate_limits
        state.set_server_reasoning_included(self.server_reasoning_included)
        state.set_previous_turn_settings(self._previous_turn_settings)
        state.set_next_turn_is_first(self._next_turn_is_first)
        if self._granted_session_permissions is not None:
            state.record_granted_permissions(self._granted_session_permissions)
        return state

    async def clone_history(self) -> InMemoryHistory:
        return InMemoryHistory(list(self.history))

    async def replace_last_turn_images(self, placeholder: str) -> bool:
        if not isinstance(placeholder, str):
            raise TypeError("placeholder must be a string")
        for index in range(len(self.history) - 1, -1, -1):
            item = self.history[index]
            if item.type == "function_call_output":
                replaced = _function_output_item_with_replaced_images(item, placeholder)
                if replaced is None:
                    return False
                self.history[index] = replaced
                return True
            if _is_user_turn_boundary(item):
                return False
        return False

    async def get_base_instructions(self) -> BaseInstructions:
        return self.base_instructions

    async def send_event(self, _turn_context: InMemoryTurnContext, event: EventMsg | dict[str, Any]) -> None:
        if isinstance(event, EventMsg):
            self.emitted_events.append(event)
        else:
            self.emitted_events.append(EventMsg.from_mapping(event))
        if self.emitted_events[-1].type == "turn_diff":
            self.loop_tail_calls.append(("turn_diff", self.emitted_events[-1].payload.unified_diff))

    async def send_response_processed(self, response_id: str) -> None:
        if not isinstance(response_id, str):
            raise TypeError("response_id must be a string")
        self.response_processed_ids.append(response_id)
        self.loop_tail_calls.append(("response_processed", response_id))

    async def drain_in_flight(self) -> None:
        self.drain_in_flight_count += 1
        self.loop_tail_calls.append(("drain_in_flight",))

    async def get_unified_diff(self) -> str | None:
        return self.unified_diff

    async def emit_turn_error_lifecycle(
        self,
        turn_context: InMemoryTurnContext,
        codex_error_info: CodexErrorInfo | str | dict[str, Any],
    ) -> None:
        if not isinstance(codex_error_info, CodexErrorInfo):
            codex_error_info = CodexErrorInfo.from_mapping(codex_error_info)
        self.turn_error_lifecycle.append((turn_context, codex_error_info))

    async def send_token_count_event(self, turn_context: InMemoryTurnContext) -> None:
        self.loop_tail_calls.append(("token_count", turn_context))
        await self.send_event(
            turn_context,
            EventMsg.with_payload(
                "token_count",
                TokenCountEvent(info=self.token_usage_info, rate_limits=self.latest_rate_limits),
            ),
        )

    async def record_token_usage_info(self, turn_context: InMemoryTurnContext, token_usage: TokenUsage | None) -> None:
        model_context_window = _turn_model_context_window(turn_context)
        if token_usage is None:
            self.token_usage_info = TokenUsageInfo.new_or_append(
                self.token_usage_info,
                None,
                model_context_window,
            )
            return
        state = self._session_state_snapshot()
        state.update_token_info_from_usage(token_usage, model_context_window)
        self.token_usage_info = state.token_info()

    async def set_total_tokens_full(self, turn_context: InMemoryTurnContext) -> None:
        context_window = _turn_model_context_window(turn_context)
        if context_window is not None:
            state = self._session_state_snapshot()
            state.set_token_usage_full(context_window)
            self.token_usage_info = state.token_info()
        await self.send_token_count_event(turn_context)

    async def get_total_token_usage(self) -> int:
        return self._session_state_snapshot().get_total_token_usage(self.server_reasoning_included)

    async def get_total_token_usage_breakdown(self) -> Any:
        return self._session_state_snapshot().get_total_token_usage_breakdown()

    async def total_token_usage(self) -> TokenUsage | None:
        info = self._session_state_snapshot().token_info()
        return info.total_token_usage if info is not None else None

    async def record_rate_limits_info(self, new_rate_limits: RateLimitSnapshot) -> None:
        if not isinstance(new_rate_limits, RateLimitSnapshot):
            raise TypeError("new_rate_limits must be RateLimitSnapshot")
        state = self._session_state_snapshot()
        state.set_rate_limits(new_rate_limits)
        self.latest_rate_limits = state.latest_rate_limits

    async def update_rate_limits(
        self,
        turn_context: InMemoryTurnContext,
        new_rate_limits: RateLimitSnapshot,
    ) -> None:
        await self.record_rate_limits_info(new_rate_limits)
        await self.send_token_count_event(turn_context)

    async def maybe_warn_on_server_model_mismatch(
        self,
        turn_context: InMemoryTurnContext,
        server_model: str,
    ) -> bool:
        requested_model = _model_slug(turn_context.model_info)
        if server_model.lower() == requested_model.lower():
            return False
        message = (
            "Your account was flagged for potentially high-risk cyber activity and this request was routed to "
            f"gpt-5.2 as a fallback. To regain access to gpt-5.3-codex, apply for trusted access: "
            f"{CYBER_VERIFY_URL} or learn more: {CYBER_SAFETY_URL}"
        )
        await self.send_event(
            turn_context,
            EventMsg.with_payload(
                "model_reroute",
                ModelRerouteEvent(
                    from_model=requested_model,
                    to_model=server_model,
                    reason=ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY,
                ),
            ),
        )
        await self.send_event(turn_context, EventMsg.with_payload("warning", WarningEvent(message)))
        return True

    async def set_server_reasoning_included(self, included: bool) -> None:
        if not isinstance(included, bool):
            raise TypeError("included must be bool")
        self.server_reasoning_included = included

    async def refresh_models_etag(self, etag: str) -> None:
        if not isinstance(etag, str):
            raise TypeError("etag must be str")
        self.models_etag = etag

    async def emit_model_verification(
        self,
        turn_context: InMemoryTurnContext,
        verifications: Any,
    ) -> None:
        await self.send_event(
            turn_context,
            EventMsg.with_payload("model_verification", ModelVerificationEvent(tuple(verifications))),
        )

    async def granted_session_permissions(self) -> AdditionalPermissionProfile | None:
        return self._session_state_snapshot().granted_permissions()

    async def granted_turn_permissions(self) -> AdditionalPermissionProfile | None:
        return self._granted_turn_permissions

    async def record_granted_permissions(self, permissions: AdditionalPermissionProfile) -> None:
        if not isinstance(permissions, AdditionalPermissionProfile):
            raise TypeError("permissions must be AdditionalPermissionProfile")
        state = self._session_state_snapshot()
        state.record_granted_permissions(permissions)
        self._granted_session_permissions = state.granted_permissions()

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

    async def request_permissions(
        self,
        parent_ctx: Any,
        call_id: str,
        args: RequestPermissionsArgs,
        cancel_token: Any = None,
    ) -> RequestPermissionsResponse:
        request_cwd = getattr(parent_ctx, "cwd", None)
        return await self.request_permissions_for_cwd(
            parent_ctx,
            call_id,
            args,
            request_cwd if request_cwd is not None else self.cwd,
            cancel_token,
        )

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
        approval_policy = _approval_policy_value_from_context(parent_ctx, self.approval_policy)
        if _request_permissions_auto_denied_by_policy(approval_policy):
            return RequestPermissionsResponse(RequestPermissionProfile())
        if self.request_permissions_callback is None:
            if self.request_permissions_event_roundtrip_enabled:
                return await self._request_permissions_via_event_roundtrip(
                    parent_ctx,
                    call_id,
                    args,
                    cwd,
                    cancel_token,
                )
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

    async def notify_request_permissions_response(
        self,
        call_id: str,
        response: RequestPermissionsResponse | Mapping[str, Any],
    ) -> None:
        if not isinstance(call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(response, RequestPermissionsResponse):
            response = RequestPermissionsResponse.from_mapping(response)
        entry = self.active_turn.turn_state.pending_request_permissions.pop(call_id, None)
        if entry is None:
            return
        normalized = normalize_request_permissions_response(
            entry.requested_permissions,
            response,
            entry.cwd,
        )
        await record_granted_request_permissions(normalized, session=self, turn_state=self)
        tx_response = entry.tx_response
        if isinstance(tx_response, asyncio.Future):
            if not tx_response.done():
                tx_response.set_result(normalized)
        elif callable(tx_response):
            tx_response(normalized)
        elif isinstance(tx_response, dict):
            tx_response["value"] = normalized

    async def _request_permissions_via_event_roundtrip(
        self,
        parent_ctx: Any,
        call_id: str,
        args: RequestPermissionsArgs,
        cwd: Path | str | None,
        cancel_token: Any = None,
    ) -> RequestPermissionsResponse | None:
        effective_cwd = Path(cwd) if cwd is not None else self.cwd
        loop = asyncio.get_running_loop()
        future: asyncio.Future[RequestPermissionsResponse] = loop.create_future()
        self.active_turn.turn_state.pending_request_permissions[call_id] = PendingRequestPermissions(
            future,
            args.permissions,
            effective_cwd,
        )
        await self.send_event(
            parent_ctx,
            EventMsg.with_payload(
                "request_permissions",
                RequestPermissionsEvent(
                    call_id=call_id,
                    turn_id=getattr(parent_ctx, "turn_id", None)
                    or getattr(parent_ctx, "sub_id", "")
                    or "",
                    started_at_ms=int(datetime.now(utc_timezone.utc).timestamp() * 1000),
                    reason=args.reason,
                    permissions=args.permissions,
                    cwd=effective_cwd,
                ),
            ),
        )
        try:
            return await _await_request_permissions_response_or_cancel(
                future,
                cancel_token,
                lambda: self.active_turn.turn_state.pending_request_permissions.pop(
                    call_id,
                    None,
                ),
            )
        except asyncio.CancelledError:
            self.active_turn.turn_state.pending_request_permissions.pop(call_id, None)
            raise


__all__ = [
    "InMemoryActiveTurn",
    "InMemoryActiveTurnState",
    "InMemoryCodexSession",
    "InMemoryHistory",
    "InMemoryInputQueue",
    "InMemoryTurnContext",
]


async def _await_request_permissions_response_or_cancel(
    response_future: asyncio.Future[RequestPermissionsResponse],
    cancel_token: Any,
    on_cancel: Any,
) -> RequestPermissionsResponse | None:
    if cancel_token is None:
        return await response_future
    is_cancelled = getattr(cancel_token, "is_cancelled", None)
    if callable(is_cancelled) and is_cancelled():
        on_cancel()
        return None
    cancelled = getattr(cancel_token, "cancelled", None)
    if not callable(cancelled):
        return await response_future
    cancel_task = asyncio.create_task(cancelled())
    done, pending = await asyncio.wait(
        {response_future, cancel_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if cancel_task in done:
        on_cancel()
        if not response_future.done():
            response_future.cancel()
        return None
    cancel_task.cancel()
    await _drain_cancelled_request_permissions_task(cancel_task)
    return response_future.result()


async def _drain_cancelled_request_permissions_task(task: asyncio.Task[Any]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return


class _NoFeatures:
    def enabled(self, _feature: Any) -> bool:
        return False


class _ApprovalCell:
    def __init__(self, value: AskForApproval | GranularApprovalConfig) -> None:
        self._value = value

    def value(self) -> AskForApproval | GranularApprovalConfig:
        return self._value


def _approval_policy_cell(value: Any) -> _ApprovalCell:
    if isinstance(value, _ApprovalCell):
        return value
    return _ApprovalCell(_coerce_approval_policy_value(value))


def _approval_policy_value_from_context(parent_ctx: Any, fallback: Any) -> AskForApproval | GranularApprovalConfig:
    value = getattr(parent_ctx, "approval_policy", None)
    if value is None:
        value = fallback
    return _coerce_approval_policy_value(value)


def _coerce_approval_policy_value(value: Any) -> AskForApproval | GranularApprovalConfig:
    if isinstance(value, _ApprovalCell):
        return value.value()
    method = getattr(value, "value", None)
    if callable(method):
        value = method()
    if isinstance(value, GranularApprovalConfig):
        return value
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return value


def _request_permissions_auto_denied_by_policy(policy: AskForApproval | GranularApprovalConfig) -> bool:
    if policy is AskForApproval.NEVER:
        return True
    return isinstance(policy, GranularApprovalConfig) and not policy.allows_request_permissions()


def _session_shell(shell: Any) -> Any:
    return shell if shell is not None else SimpleNamespace(name=lambda: "")


def _is_user_turn_boundary(item: ResponseItem) -> bool:
    return item.type == "message" and item.role == "user"


def _function_output_item_with_replaced_images(item: ResponseItem, placeholder: str) -> ResponseItem | None:
    output = item.output
    try:
        payload = output if isinstance(output, FunctionCallOutputPayload) else FunctionCallOutputPayload.from_value(output)
    except (TypeError, ValueError):
        return None
    if payload.body.type != "content_items":
        return None
    content_items = []
    replaced = False
    for content_item in payload.body.content_items:
        if content_item.type == "input_image":
            content_items.append(FunctionCallOutputContentItem.input_text(placeholder))
            replaced = True
        else:
            content_items.append(content_item)
    if not replaced:
        return None
    return replace(
        item,
        output=FunctionCallOutputPayload.from_content_items(tuple(content_items), success=payload.success),
    )


def _model_slug(model_info: Any) -> str:
    slug = getattr(model_info, "slug", None)
    return str(slug) if slug is not None else ""


def _turn_id_for_event(turn_context: InMemoryTurnContext) -> str:
    return str(turn_context.turn_id or "")


def _now_unix_timestamp_ms() -> int:
    return int(datetime.now(utc_timezone.utc).timestamp() * 1000)


def _turn_truncation_policy(model_info: Any) -> TruncationPolicyConfig:
    policy = getattr(model_info, "truncation_policy", None)
    if isinstance(policy, TruncationPolicyConfig):
        return policy
    if isinstance(policy, Mapping):
        return TruncationPolicyConfig.from_mapping(policy)
    return TruncationPolicyConfig.tokens(10_000)


def _turn_truncation_policy_from_context(turn_context: Any) -> TruncationPolicyConfig:
    policy = getattr(turn_context, "truncation_policy", None)
    if isinstance(policy, TruncationPolicyConfig):
        return policy
    if isinstance(policy, Mapping):
        return TruncationPolicyConfig.from_mapping(policy)
    return _turn_truncation_policy(getattr(turn_context, "model_info", None))


def _process_history_items(items: tuple[ResponseItem, ...], policy: TruncationPolicyConfig) -> tuple[ResponseItem, ...]:
    return _context_manager_process_history_items(items, policy)


def _process_history_item(item: ResponseItem, policy: TruncationPolicyConfig) -> ResponseItem:
    return _context_manager_process_history_item(item, policy)


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


def _permission_profile_from_sandbox_policy(
    sandbox_policy: Any,
    base_profile: PermissionProfile | None,
    cwd: Path | str,
) -> PermissionProfile:
    if not isinstance(sandbox_policy, SandboxPolicy):
        if isinstance(sandbox_policy, Mapping):
            sandbox_policy = SandboxPolicy.from_mapping(sandbox_policy)
        else:
            raise TypeError("sandbox_policy must be a SandboxPolicy")
    base_file_system = FileSystemSandboxPolicy.default()
    if isinstance(base_profile, PermissionProfile):
        getter = getattr(base_profile, "file_system_sandbox_policy", None)
        if callable(getter):
            base_file_system_profile = getter()
            if isinstance(base_file_system_profile, FileSystemSandboxPolicy):
                base_file_system = base_file_system_profile
    projected_file_system = FileSystemSandboxPolicy.from_legacy_sandbox_policy_preserving_deny_entries(
        sandbox_policy,
        Path(cwd),
        base_file_system,
    )
    return PermissionProfile.from_runtime_permissions_with_enforcement(
        SandboxEnforcement.from_legacy_sandbox_policy(sandbox_policy),
        projected_file_system,
        sandbox_policy.network_sandbox_policy(),
    )


def _file_system_sandbox_policy_from_permission_profile(
    permission_profile: Any,
) -> FileSystemSandboxPolicy | None:
    getter = getattr(permission_profile, "file_system_sandbox_policy", None)
    if not callable(getter):
        return None
    value = getter()
    if not isinstance(value, FileSystemSandboxPolicy):
        return None
    return value


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


def _turn_model_context_window(turn_context: Any) -> int | None:
    model_info = getattr(turn_context, "model_info", None)
    if model_info is None:
        return None
    resolved_method = getattr(model_info, "resolved_context_window", None)
    if callable(resolved_method):
        resolved = resolved_method()
    else:
        resolved = getattr(model_info, "context_window", None)
        if resolved is None:
            resolved = getattr(model_info, "max_context_window", None)
    if isinstance(resolved, bool) or not isinstance(resolved, int) or resolved < 0:
        return None
    percent = getattr(model_info, "effective_context_window_percent", 95)
    if isinstance(percent, bool) or not isinstance(percent, int):
        percent = 95
    return max((resolved * max(percent, 0)) // 100, 0)


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
    value = _coerce_approval_policy_value(turn_context.approval_policy)
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
                _coerce_approval_policy_value(turn_context.approval_policy),
                getattr(config, "approvals_reviewer", ApprovalsReviewer.USER),
                None,
                turn_context.cwd,
                _feature_enabled(turn_context.features, Feature.EXEC_PERMISSION_APPROVALS),
                _feature_enabled(turn_context.features, Feature.REQUEST_PERMISSIONS_TOOL),
            ).render()
        )
    separate_guardian_developer_message = is_guardian_reviewer_source(turn_context.session_source)
    if turn_context.developer_instructions and not separate_guardian_developer_message:
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
    if turn_context.user_instructions:
        contextual_user_sections.append(
            UserInstructions(
                directory=str(turn_context.cwd),
                text=str(turn_context.user_instructions),
            ).render()
        )
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
    if separate_guardian_developer_message and turn_context.developer_instructions:
        developer_message = build_developer_update_item([str(turn_context.developer_instructions)])
        if developer_message is not None:
            items.append(developer_message)
    return items


def _response_item(value: ResponseItem | dict[str, Any]) -> ResponseItem:
    if isinstance(value, ResponseItem):
        return value
    if isinstance(value, dict):
        return ResponseItem.from_mapping(value)
    raise TypeError("items entries must be ResponseItem or mapping")


def _pending_input_item(value: Any) -> Any:
    if isinstance(value, (ResponseItem, UserInput)):
        return value
    if isinstance(value, Mapping):
        value_type = value.get("type")
        if value_type in {"text", "image", "local_image", "skill", "mention"}:
            return UserInput.from_mapping(value)
        return ResponseItem.from_mapping(value)
    return value


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



