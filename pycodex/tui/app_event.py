"""Semantic port of Rust ``codex-tui::app_event``.

Upstream source: ``codex/codex-rs/tui/src/app_event.rs``.

Rust uses a large internal ``AppEvent`` enum as the TUI app-loop message bus.
Python models the same contract with explicit enum/DTO objects plus a generic
``AppEvent(kind, payload)`` semantic variant. Framework-specific Rust payload
types are intentionally carried as opaque Python values at this module boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app_event",
    source="codex/codex-rs/tui/src/app_event.rs",
    status="complete",
)


class RealtimeAudioDeviceKind(Enum):
    """Rust ``RealtimeAudioDeviceKind`` with its UI label helpers."""

    MICROPHONE = "Microphone"
    SPEAKER = "Speaker"

    def title(self) -> str:
        return self.value

    def noun(self) -> str:
        if self is RealtimeAudioDeviceKind.MICROPHONE:
            return "microphone"
        return "speaker"


@dataclass(frozen=True)
class ThreadGoalSetMode:
    """Rust ``ThreadGoalSetMode`` semantic variant.

    ``UpdateExisting`` carries the desired goal status and optional token budget.
    The concrete ``ThreadGoalStatus`` type belongs to the protocol crate, so it is
    carried opaquely here.
    """

    kind: str
    status: Any = None
    token_budget: Optional[int] = None

    CONFIRM_IF_EXISTS: ClassVar[str] = "ConfirmIfExists"
    REPLACE_EXISTING: ClassVar[str] = "ReplaceExisting"
    UPDATE_EXISTING: ClassVar[str] = "UpdateExisting"

    @classmethod
    def confirm_if_exists(cls) -> "ThreadGoalSetMode":
        return cls(cls.CONFIRM_IF_EXISTS)

    @classmethod
    def replace_existing(cls) -> "ThreadGoalSetMode":
        return cls(cls.REPLACE_EXISTING)

    @classmethod
    def update_existing(cls, status: Any, token_budget: Optional[int] = None) -> "ThreadGoalSetMode":
        return cls(cls.UPDATE_EXISTING, status=status, token_budget=token_budget)


@dataclass(frozen=True)
class HistoryLookupResponse:
    offset: int
    log_id: int
    entry: Optional[str]


class ConsolidationScrollbackReflow(Enum):
    IF_RESIZE_REFLOW_RAN = "IfResizeReflowRan"
    REQUIRED = "Required"


class WindowsSandboxEnableMode(Enum):
    ELEVATED = "Elevated"
    LEGACY = "Legacy"


@dataclass(frozen=True)
class ConnectorsSnapshot:
    connectors: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class RateLimitRefreshOrigin:
    """Rust ``RateLimitRefreshOrigin`` semantic variant."""

    kind: str
    request_id: Optional[int] = None

    STARTUP_PREFETCH: ClassVar[str] = "StartupPrefetch"
    STATUS_COMMAND: ClassVar[str] = "StatusCommand"

    @classmethod
    def startup_prefetch(cls) -> "RateLimitRefreshOrigin":
        return cls(cls.STARTUP_PREFETCH)

    @classmethod
    def status_command(cls, request_id: int) -> "RateLimitRefreshOrigin":
        return cls(cls.STATUS_COMMAND, request_id=request_id)


@dataclass(frozen=True)
class KeymapEditIntent:
    """Rust ``KeymapEditIntent`` semantic variant."""

    kind: str
    old_key: Optional[str] = None

    REPLACE_ALL: ClassVar[str] = "ReplaceAll"
    ADD_ALTERNATE: ClassVar[str] = "AddAlternate"
    REPLACE_ONE: ClassVar[str] = "ReplaceOne"

    @classmethod
    def replace_all(cls) -> "KeymapEditIntent":
        return cls(cls.REPLACE_ALL)

    @classmethod
    def add_alternate(cls) -> "KeymapEditIntent":
        return cls(cls.ADD_ALTERNATE)

    @classmethod
    def replace_one(cls, old_key: str) -> "KeymapEditIntent":
        return cls(cls.REPLACE_ONE, old_key=old_key)


@dataclass(frozen=True)
class AppEvent:
    """Rust ``AppEvent`` semantic variant.

    The Rust enum has many variants whose payload types are owned by neighboring
    modules/crates. This class preserves the local event-bus contract: a stable
    Rust variant name and a named payload map.
    """

    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, kind: str, **payload: Any) -> "AppEvent":
        return cls(kind, dict(payload))

    @classmethod
    def open_agent_picker(cls) -> "AppEvent":
        return cls.of("OpenAgentPicker")

    @classmethod
    def select_agent_thread(cls, thread_id: Any) -> "AppEvent":
        return cls.of("SelectAgentThread", thread_id=thread_id)

    @classmethod
    def start_side(cls, parent_thread_id: Any, user_message: Any = None) -> "AppEvent":
        return cls.of("StartSide", parent_thread_id=parent_thread_id, user_message=user_message)

    @classmethod
    def submit_thread_op(cls, thread_id: Any, op: Any) -> "AppEvent":
        return cls.of("SubmitThreadOp", thread_id=thread_id, op=op)

    @classmethod
    def thread_history_entry_response(cls, thread_id: Any, event: HistoryLookupResponse) -> "AppEvent":
        return cls.of("ThreadHistoryEntryResponse", thread_id=thread_id, event=event)

    @classmethod
    def append_message_history_entry(cls, thread_id: Any, text: str) -> "AppEvent":
        return cls.of("AppendMessageHistoryEntry", thread_id=thread_id, text=text)

    @classmethod
    def sync_thread_git_branch(cls, thread_id: Any, branch: str) -> "AppEvent":
        return cls.of("SyncThreadGitBranch", thread_id=thread_id, branch=branch)

    @classmethod
    def lookup_message_history_entry(cls, thread_id: Any, offset: int, log_id: int) -> "AppEvent":
        return cls.of("LookupMessageHistoryEntry", thread_id=thread_id, offset=offset, log_id=log_id)

    @classmethod
    def new_session(cls) -> "AppEvent":
        return cls.of("NewSession")

    @classmethod
    def clear_ui(cls) -> "AppEvent":
        return cls.of("ClearUi")

    @classmethod
    def raw_output_mode_changed(cls, enabled: bool) -> "AppEvent":
        return cls.of("RawOutputModeChanged", enabled=enabled)

    @classmethod
    def clear_ui_and_submit_user_message(cls, text: str) -> "AppEvent":
        return cls.of("ClearUiAndSubmitUserMessage", text=text)

    @classmethod
    def exit(cls, mode: "ExitMode") -> "AppEvent":
        return cls.of("Exit", mode=mode)

    @classmethod
    def logout(cls) -> "AppEvent":
        return cls.of("Logout")

    @classmethod
    def fatal_exit_request(cls, message: str) -> "AppEvent":
        return cls.of("FatalExitRequest", message=message)

    @classmethod
    def codex_op(cls, op: Any) -> "AppEvent":
        return cls.of("CodexOp", op=op)

    @classmethod
    def start_file_search(cls, query: str) -> "AppEvent":
        return cls.of("StartFileSearch", query=query)

    @classmethod
    def file_search_result(cls, query: str, matches: list[Any]) -> "AppEvent":
        return cls.of("FileSearchResult", query=query, matches=matches)

    @classmethod
    def refresh_rate_limits(cls, origin: RateLimitRefreshOrigin) -> "AppEvent":
        return cls.of("RefreshRateLimits", origin=origin)

    @classmethod
    def open_thread_goal_menu(cls, thread_id: Any) -> "AppEvent":
        return cls.of("OpenThreadGoalMenu", thread_id=thread_id)

    @classmethod
    def open_thread_goal_editor(cls, thread_id: Any = None) -> "AppEvent":
        return cls.of("OpenThreadGoalEditor", thread_id=thread_id)

    @classmethod
    def set_thread_goal_objective(
        cls,
        thread_id: Any,
        objective: str,
        mode: ThreadGoalSetMode,
    ) -> "AppEvent":
        return cls.of(
            "SetThreadGoalObjective",
            thread_id=thread_id,
            objective=str(objective),
            mode=mode,
        )

    @classmethod
    def set_thread_goal_status(cls, thread_id: Any, status: Any) -> "AppEvent":
        return cls.of("SetThreadGoalStatus", thread_id=thread_id, status=status)

    @classmethod
    def clear_thread_goal(cls, thread_id: Any) -> "AppEvent":
        return cls.of("ClearThreadGoal", thread_id=thread_id)

    @classmethod
    def rate_limits_loaded(cls, origin: RateLimitRefreshOrigin, result: Any) -> "AppEvent":
        return cls.of("RateLimitsLoaded", origin=origin, result=result)

    @classmethod
    def connectors_loaded(cls, result: Any, is_final: bool) -> "AppEvent":
        return cls.of("ConnectorsLoaded", result=result, is_final=is_final)

    @classmethod
    def diff_result(cls, text: str) -> "AppEvent":
        return cls.of("DiffResult", text=text)

    @classmethod
    def open_url_in_browser(cls, url: str) -> "AppEvent":
        return cls.of("OpenUrlInBrowser", url=url)

    @classmethod
    def begin_initial_history_replay_buffer(cls) -> "AppEvent":
        return cls.of("BeginInitialHistoryReplayBuffer")

    @classmethod
    def begin_thread_switch_history_replay_buffer(cls) -> "AppEvent":
        return cls.of("BeginThreadSwitchHistoryReplayBuffer")

    @classmethod
    def insert_history_cell(cls, cell: Any) -> "AppEvent":
        return cls.of("InsertHistoryCell", cell=cell)

    @classmethod
    def end_initial_history_replay_buffer(cls) -> "AppEvent":
        return cls.of("EndInitialHistoryReplayBuffer")

    @classmethod
    def consolidate_agent_message(
        cls,
        source: str,
        cwd: Any,
        scrollback_reflow: ConsolidationScrollbackReflow,
        deferred_history_cell: Any = None,
    ) -> "AppEvent":
        return cls.of(
            "ConsolidateAgentMessage",
            source=source,
            cwd=cwd,
            scrollback_reflow=scrollback_reflow,
            deferred_history_cell=deferred_history_cell,
        )

    @classmethod
    def consolidate_proposed_plan(cls, source: str) -> "AppEvent":
        return cls.of("ConsolidateProposedPlan", source=source)

    @classmethod
    def apply_thread_rollback(cls, num_turns: int) -> "AppEvent":
        return cls.of("ApplyThreadRollback", num_turns=num_turns)

    @classmethod
    def start_commit_animation(cls) -> "AppEvent":
        return cls.of("StartCommitAnimation")

    @classmethod
    def stop_commit_animation(cls) -> "AppEvent":
        return cls.of("StopCommitAnimation")

    @classmethod
    def commit_tick(cls) -> "AppEvent":
        return cls.of("CommitTick")

    @classmethod
    def update_reasoning_effort(cls, effort: Any = None) -> "AppEvent":
        return cls.of("UpdateReasoningEffort", effort=effort)

    @classmethod
    def update_model(cls, model: str) -> "AppEvent":
        return cls.of("UpdateModel", model=model)

    @classmethod
    def persist_model_selection(cls, model: str, effort: Any = None) -> "AppEvent":
        return cls.of("PersistModelSelection", model=model, effort=effort)

    @classmethod
    def open_realtime_audio_device_selection(cls, kind: RealtimeAudioDeviceKind) -> "AppEvent":
        return cls.of("OpenRealtimeAudioDeviceSelection", kind=kind)

    @classmethod
    def persist_realtime_audio_device_selection(cls, kind: RealtimeAudioDeviceKind, name: Optional[str]) -> "AppEvent":
        return cls.of("PersistRealtimeAudioDeviceSelection", kind=kind, name=name)

    @classmethod
    def restart_realtime_audio_device(cls, kind: RealtimeAudioDeviceKind) -> "AppEvent":
        return cls.of("RestartRealtimeAudioDevice", kind=kind)

    @classmethod
    def realtime_webrtc_offer_created(cls, result: Any) -> "AppEvent":
        return cls.of("RealtimeWebrtcOfferCreated", result=result)

    @classmethod
    def realtime_webrtc_event(cls, event: Any) -> "AppEvent":
        return cls.of("RealtimeWebrtcEvent", event=event)

    @classmethod
    def realtime_webrtc_local_audio_level(cls, level: int) -> "AppEvent":
        return cls.of("RealtimeWebrtcLocalAudioLevel", level=level)

    @classmethod
    def open_full_access_confirmation(
        cls,
        preset: Any,
        return_to_permissions: bool,
        profile_selection: Optional["PermissionProfileSelection"] = None,
    ) -> "AppEvent":
        return cls.of(
            "OpenFullAccessConfirmation",
            preset=preset,
            return_to_permissions=return_to_permissions,
            profile_selection=profile_selection,
        )

    @classmethod
    def update_ask_for_approval_policy(cls, policy: Any) -> "AppEvent":
        return cls.of("UpdateAskForApprovalPolicy", policy=policy)

    @classmethod
    def select_permission_profile(cls, selection: "PermissionProfileSelection") -> "AppEvent":
        return cls.of("SelectPermissionProfile", selection=selection)

    @classmethod
    def update_approvals_reviewer(cls, reviewer: Any) -> "AppEvent":
        return cls.of("UpdateApprovalsReviewer", reviewer=reviewer)

    @classmethod
    def open_approvals_popup(cls) -> "AppEvent":
        return cls.of("OpenApprovalsPopup")

    @classmethod
    def open_permissions_popup(cls) -> "AppEvent":
        return cls.of("OpenPermissionsPopup")

    @classmethod
    def open_feedback_note(cls, category: "FeedbackCategory", include_logs: bool) -> "AppEvent":
        return cls.of("OpenFeedbackNote", category=category, include_logs=include_logs)

    @classmethod
    def open_feedback_consent(cls, category: "FeedbackCategory") -> "AppEvent":
        return cls.of("OpenFeedbackConsent", category=category)

    @classmethod
    def submit_feedback(
        cls,
        category: "FeedbackCategory",
        reason: Optional[str],
        turn_id: Optional[str],
        include_logs: bool,
    ) -> "AppEvent":
        return cls.of("SubmitFeedback", category=category, reason=reason, turn_id=turn_id, include_logs=include_logs)

    @classmethod
    def launch_external_editor(cls) -> "AppEvent":
        return cls.of("LaunchExternalEditor")

    @classmethod
    def status_line_branch_updated(cls, cwd: Any, branch: Optional[str]) -> "AppEvent":
        return cls.of("StatusLineBranchUpdated", cwd=cwd, branch=branch)

    @classmethod
    def syntax_theme_selected(cls, name: str) -> "AppEvent":
        return cls.of("SyntaxThemeSelected", name=name)

    @classmethod
    def open_keymap_capture(cls, context: str, action: str, intent: KeymapEditIntent) -> "AppEvent":
        return cls.of("OpenKeymapCapture", context=context, action=action, intent=intent)

    @classmethod
    def keymap_captured(cls, context: str, action: str, key: str, intent: KeymapEditIntent) -> "AppEvent":
        return cls.of("KeymapCaptured", context=context, action=action, key=key, intent=intent)

    def is_codex_op(self) -> bool:
        return self.kind == "CodexOp"


@dataclass(frozen=True)
class PermissionProfileSelection:
    profile_id: str
    approval_policy: Optional[Any]
    approvals_reviewer: Optional[Any]
    display_label: str


@dataclass(frozen=True)
class RealtimeWebrtcOffer:
    offer_sdp: str
    handle: Any


class ExitMode(Enum):
    SHUTDOWN_FIRST = "ShutdownFirst"
    IMMEDIATE = "Immediate"


class FeedbackCategory(Enum):
    BAD_RESULT = "BadResult"
    GOOD_RESULT = "GoodResult"
    BUG = "Bug"
    SAFETY_CHECK = "SafetyCheck"
    OTHER = "Other"


__all__ = [
    "AppEvent",
    "ConnectorsSnapshot",
    "ConsolidationScrollbackReflow",
    "ExitMode",
    "FeedbackCategory",
    "HistoryLookupResponse",
    "KeymapEditIntent",
    "PermissionProfileSelection",
    "RUST_MODULE",
    "RateLimitRefreshOrigin",
    "RealtimeAudioDeviceKind",
    "RealtimeWebrtcOffer",
    "ThreadGoalSetMode",
    "WindowsSandboxEnableMode",
]
