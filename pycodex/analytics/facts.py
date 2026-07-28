"""Rust-aligned ``codex-analytics::facts`` owner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class AcceptedLineFingerprint:
    path_hash: str
    line_hash: str

def build_track_events_context(model_slug: str, thread_id: str, turn_id: str) -> "TrackEventsContext":
    return TrackEventsContext(model_slug, thread_id, turn_id)

@dataclass(frozen=True)
class TrackEventsContext:
    model_slug: str
    thread_id: str
    turn_id: str

class _SnakeEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

class TurnSubmissionType(_SnakeEnum):
    DEFAULT = "default"
    QUEUED = "queued"

class ThreadInitializationMode(_SnakeEnum):
    NEW = "new"
    FORKED = "forked"
    RESUMED = "resumed"

class TurnStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class TurnSteerResult(_SnakeEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class TurnSteerRejectionReason(_SnakeEnum):
    NO_ACTIVE_TURN = "no_active_turn"
    EXPECTED_TURN_MISMATCH = "expected_turn_mismatch"
    NON_STEERABLE_REVIEW = "non_steerable_review"
    NON_STEERABLE_COMPACT = "non_steerable_compact"
    EMPTY_INPUT = "empty_input"
    INPUT_TOO_LARGE = "input_too_large"

class InvocationType(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"

class SkillScope(str, Enum):
    USER = "user"
    REPO = "repo"
    SYSTEM = "system"
    ADMIN = "admin"

class CompactionTrigger(_SnakeEnum):
    MANUAL = "manual"
    AUTO = "auto"

class CompactionReason(_SnakeEnum):
    USER_REQUESTED = "user_requested"
    CONTEXT_LIMIT = "context_limit"
    MODEL_DOWNSHIFT = "model_downshift"

class CompactionImplementation(_SnakeEnum):
    RESPONSES = "responses"
    RESPONSES_COMPACTION_V2 = "responses_compaction_v2"
    RESPONSES_COMPACT = "responses_compact"

class CompactionPhase(_SnakeEnum):
    STANDALONE_TURN = "standalone_turn"
    PRE_TURN = "pre_turn"
    MID_TURN = "mid_turn"

class CompactionStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class CompactionStrategy(_SnakeEnum):
    MEMENTO = "memento"
    PREFIX_COMPACTION = "prefix_compaction"

class TurnSteerRequestError(Enum):
    NO_ACTIVE_TURN = "no_active_turn"
    EXPECTED_TURN_MISMATCH = "expected_turn_mismatch"
    NON_STEERABLE_REVIEW = "non_steerable_review"
    NON_STEERABLE_COMPACT = "non_steerable_compact"

class InputError(Enum):
    EMPTY = "empty"
    TOO_LARGE = "too_large"

@dataclass(frozen=True)
class AnalyticsJsonRpcError:
    kind: str
    error: TurnSteerRequestError | InputError

    @classmethod
    def turn_steer(cls, error: TurnSteerRequestError) -> "AnalyticsJsonRpcError":
        return cls("TurnSteer", error)

    @classmethod
    def input(cls, error: InputError) -> "AnalyticsJsonRpcError":
        return cls("Input", error)

def turn_steer_rejection_reason_from_error(
    error: TurnSteerRequestError | InputError | AnalyticsJsonRpcError,
) -> TurnSteerRejectionReason:
    if isinstance(error, AnalyticsJsonRpcError):
        return turn_steer_rejection_reason_from_error(error.error)
    if error is TurnSteerRequestError.NO_ACTIVE_TURN:
        return TurnSteerRejectionReason.NO_ACTIVE_TURN
    if error is TurnSteerRequestError.EXPECTED_TURN_MISMATCH:
        return TurnSteerRejectionReason.EXPECTED_TURN_MISMATCH
    if error is TurnSteerRequestError.NON_STEERABLE_REVIEW:
        return TurnSteerRejectionReason.NON_STEERABLE_REVIEW
    if error is TurnSteerRequestError.NON_STEERABLE_COMPACT:
        return TurnSteerRejectionReason.NON_STEERABLE_COMPACT
    if error is InputError.EMPTY:
        return TurnSteerRejectionReason.EMPTY_INPUT
    if error is InputError.TOO_LARGE:
        return TurnSteerRejectionReason.INPUT_TOO_LARGE
    raise ValueError(f"unknown turn steer error: {error!r}")

class PluginState(_SnakeEnum):
    INSTALLED = "installed"
    UNINSTALLED = "uninstalled"
    ENABLED = "enabled"
    DISABLED = "disabled"

class HookEventName(str, Enum):
    PRE_TOOL_USE = "PreToolUse"
    PERMISSION_REQUEST = "PermissionRequest"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    STOP = "Stop"

class HookSource(_SnakeEnum):
    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    MDM = "mdm"
    SESSION_FLAGS = "session_flags"
    PLUGIN = "plugin"
    CLOUD_REQUIREMENTS = "cloud_requirements"
    LEGACY_MANAGED_CONFIG_FILE = "legacy_managed_config_file"
    LEGACY_MANAGED_CONFIG_MDM = "legacy_managed_config_mdm"
    UNKNOWN = "unknown"

class HookRunStatus(_SnakeEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    STOPPED = "stopped"

@dataclass
class SkillInvocation:
    skill_name: str
    skill_scope: Any
    skill_path: Path
    plugin_id: str | None
    invocation_type: InvocationType

@dataclass
class SkillInvokedInput:
    tracking: TrackEventsContext
    invocations: list[SkillInvocation]

@dataclass
class AppInvocation:
    connector_id: str | None = None
    app_name: str | None = None
    invocation_type: InvocationType | None = None

@dataclass
class AppMentionedInput:
    tracking: TrackEventsContext
    mentions: list[AppInvocation]

@dataclass
class AppUsedInput:
    tracking: TrackEventsContext
    app: AppInvocation

@dataclass
class PluginId:
    plugin_name: str
    marketplace_name: str

    def as_key(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"

@dataclass
class PluginCapabilitySummary:
    has_skills: bool
    mcp_server_names: tuple[str, ...] = ()
    app_connector_ids: tuple[str, ...] = ()

@dataclass
class PluginTelemetryMetadata:
    plugin_id: PluginId
    remote_plugin_id: str | None = None
    capability_summary: PluginCapabilitySummary | None = None

@dataclass
class PluginUsedInput:
    tracking: TrackEventsContext
    plugin: PluginTelemetryMetadata

@dataclass
class PluginStateChangedInput:
    plugin: PluginTelemetryMetadata
    state: PluginState

@dataclass
class SubAgentThreadStartedInput:
    session_id: str
    thread_id: str
    parent_thread_id: str | None
    product_client_id: str
    client_name: str
    client_version: str
    model: str
    ephemeral: bool
    subagent_source: Any
    created_at: int

@dataclass
class TurnTokenUsageFact:
    turn_id: str
    thread_id: str
    token_usage: Any

@dataclass
class HookRunFact:
    event_name: HookEventName | str
    hook_source: HookSource | str
    status: HookRunStatus | str

@dataclass
class HookRunInput:
    tracking: TrackEventsContext
    hook: HookRunFact

@dataclass
class CodexCompactionEvent:
    thread_id: str
    turn_id: str
    trigger: CompactionTrigger
    reason: CompactionReason
    implementation: CompactionImplementation
    phase: CompactionPhase
    strategy: CompactionStrategy
    status: CompactionStatus
    error: str | None
    active_context_tokens_before: int
    active_context_tokens_after: int
    started_at: int
    completed_at: int
    duration_ms: int | None

@dataclass
class CodexTurnSteerEvent:
    expected_turn_id: str | None
    accepted_turn_id: str | None
    num_input_images: int
    result: TurnSteerResult
    rejection_reason: TurnSteerRejectionReason | None
    created_at: int

@dataclass
class TurnResolvedConfigFact:
    turn_id: str
    thread_id: str
    num_input_images: int
    submission_type: TurnSubmissionType | None
    ephemeral: bool
    session_source: Any
    model: str
    model_provider: str
    permission_profile: Any
    permission_profile_cwd: Path
    reasoning_effort: Any | None
    reasoning_summary: Any | None
    service_tier: Any | None
    approval_policy: Any
    approvals_reviewer: Any
    sandbox_network_access: bool
    collaboration_mode: Any
    personality: Any | None
    is_first_turn: bool


__all__ = [name for name in globals() if not name.startswith("_")]
