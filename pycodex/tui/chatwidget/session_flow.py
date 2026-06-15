"""Semantic Python port of Rust ``codex-tui::chatwidget::session_flow``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/session_flow.rs``.

The Rust module applies a configured thread session to ``ChatWidget`` and
coordinates header, fork, initial-message, and rename side effects.  Python
models those effects as explicit records so the session-flow contract can be
tested without the full TUI runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::session_flow",
    source="codex/codex-rs/tui/src/chatwidget/session_flow.rs",
    status="complete",
)


class SessionConfiguredDisplay(Enum):
    NORMAL = "Normal"
    QUIET = "Quiet"
    SIDE_CONVERSATION = "SideConversation"


@dataclass(frozen=True)
class MessageHistoryMetadata:
    log_id: Optional[str] = None
    entry_count: int = 0


@dataclass(frozen=True)
class PermissionProfileSnapshot:
    permission_profile: Optional[Any] = None
    active_permission_profile: Optional[Any] = None


@dataclass
class CollaborationModeState:
    model: Optional[str] = None
    reasoning_effort: Optional[Any] = None
    developer_instructions: Optional[Any] = None

    def with_updates(
        self,
        model: Optional[str],
        reasoning_effort: Optional[Any],
        developer_instructions: Optional[Any],
    ) -> "CollaborationModeState":
        return CollaborationModeState(
            model=model if model is not None else self.model,
            reasoning_effort=reasoning_effort,
            developer_instructions=developer_instructions,
        )


@dataclass
class CollaborationModeMask:
    reasoning_effort: Optional[Any] = None


@dataclass
class ThreadSessionState:
    thread_id: str
    cwd: Union[Path, str]
    model: str
    reasoning_effort: Optional[Any] = None
    message_history: Optional[MessageHistoryMetadata] = None
    network_proxy: Optional[Any] = None
    thread_name: Optional[str] = None
    forked_from_id: Optional[str] = None
    fork_parent_title: Optional[str] = None
    rollout_path: Optional[Union[Path, str]] = None
    runtime_workspace_roots: Tuple[Union[Path, str], ...] = ()
    service_tier: Optional[str] = None
    approval_policy: Optional[Any] = None
    permission_profile: Optional[Any] = None
    active_permission_profile: Optional[Any] = None
    approvals_reviewer: Optional[Any] = None
    personality: Optional[Any] = None
    collaboration_mode: Optional[str] = None
    instruction_source_paths: Tuple[Union[Path, str], ...] = ()


@dataclass
class SessionInfoCellPlan:
    model: str
    thread_id: str
    display_welcome_banner: bool
    plan_type: Optional[Any] = None
    show_fast_status: bool = False
    startup_tooltip_override: Optional[Any] = None


@dataclass
class ForkedThreadEvent:
    forked_from_id: str
    fork_parent_title: Optional[str] = None

    def line_text(self) -> str:
        title = self.fork_parent_title.strip() if self.fork_parent_title else ""
        if title:
            return f"* Thread forked from {title} ({self.forked_from_id})"
        return f"* Thread forked from {self.forked_from_id}"


@dataclass
class RenameConfirmationPlan:
    thread_id: Optional[str]
    thread_name: str


@dataclass
class SessionFlowModel:
    thread_id: Optional[str] = None
    thread_name: Optional[str] = None
    forked_from: Optional[str] = None
    current_rollout_path: Optional[Path] = None
    current_cwd: Optional[Path] = None
    config_cwd: Optional[Path] = None
    workspace_roots: List[Path] = field(default_factory=list)
    permissions_workspace_roots: List[Path] = field(default_factory=list)
    approval_policy: Optional[Any] = None
    permission_snapshot: Optional[PermissionProfileSnapshot] = None
    approvals_reviewer: Optional[Any] = None
    personality: Optional[Any] = None
    effective_service_tier: Optional[str] = None
    session_network_proxy: Optional[Any] = None
    instruction_source_paths: List[Path] = field(default_factory=list)
    current_collaboration_mode: CollaborationModeState = field(default_factory=CollaborationModeState)
    active_collaboration_mask: Optional[CollaborationModeMask] = None
    current_goal_status_indicator: Optional[Any] = None
    current_goal_status: Optional[Any] = None
    status_line_project_root_name_cache: Optional[Any] = None
    startup_tooltip_override: Optional[Any] = None
    show_welcome_banner: bool = False
    plan_type: Optional[Any] = None
    suppress_initial_user_message_submit: bool = False
    suppress_session_configured_redraw: bool = False
    initial_user_message: Optional[Any] = None
    connectors_feature_enabled: bool = False
    active_cell_is_session_header: bool = False

    bottom_history_metadata: Optional[Tuple[str, Optional[str], int]] = None
    queue_submissions: Optional[bool] = None
    skills: Optional[Any] = "unset"
    submitted_user_messages: List[Any] = field(default_factory=list)
    applied_session_info_cells: List[SessionInfoCellPlan] = field(default_factory=list)
    forked_thread_events: List[ForkedThreadEvent] = field(default_factory=list)
    rename_confirmation_cells: List[RenameConfirmationPlan] = field(default_factory=list)
    emitted_history_lines: List[str] = field(default_factory=list)
    redraw_requests: int = 0
    copy_history_resets: int = 0
    review_denial_resets: int = 0
    plan_mode_nudge_refreshes: int = 0
    turn_thread_resets: int = 0
    collaboration_indicator_updates: int = 0
    model_display_refreshes: int = 0
    status_surface_refreshes: int = 0
    service_tier_syncs: int = 0
    personality_command_syncs: int = 0
    plugins_command_syncs: int = 0
    goal_command_syncs: int = 0
    plugin_mention_refreshes: int = 0
    skills_refreshes: List[bool] = field(default_factory=list)
    connector_prefetches: int = 0
    active_cell_revision_bumps: int = 0
    saw_copy_source_this_turn: bool = True
    maybe_send_next_queued_input_calls: int = 0

    def handle_thread_session(self, session: ThreadSessionState) -> None:
        self.instruction_source_paths = [Path(path) for path in session.instruction_source_paths]
        self._on_session_configured(
            session,
            SessionConfiguredDisplay.NORMAL,
            session.fork_parent_title,
        )

    def handle_thread_session_quiet(self, session: ThreadSessionState) -> None:
        self.instruction_source_paths = [Path(path) for path in session.instruction_source_paths]
        self._on_session_configured(session, SessionConfiguredDisplay.QUIET, None)

    def handle_side_thread_session(self, session: ThreadSessionState) -> None:
        self.instruction_source_paths = [Path(path) for path in session.instruction_source_paths]
        self._on_session_configured(
            session,
            SessionConfiguredDisplay.SIDE_CONVERSATION,
            session.fork_parent_title,
        )

    def _on_session_configured(
        self,
        session: ThreadSessionState,
        display: SessionConfiguredDisplay,
        fork_parent_title: Optional[str],
    ) -> None:
        self.copy_history_resets += 1
        history = session.message_history or MessageHistoryMetadata()
        self.bottom_history_metadata = (session.thread_id, history.log_id, history.entry_count)
        self.set_skills(None)
        self.session_network_proxy = session.network_proxy

        previous_thread_id = self.thread_id
        self.thread_id = session.thread_id
        self.queue_submissions = False
        if previous_thread_id != self.thread_id:
            self.review_denial_resets += 1

        self.refresh_plan_mode_nudge()
        self.turn_thread_resets += 1
        self.thread_name = session.thread_name
        self.current_goal_status_indicator = None
        self.current_goal_status = None
        self.update_collaboration_mode_indicator()
        self.forked_from = session.forked_from_id
        self.current_rollout_path = Path(session.rollout_path) if session.rollout_path else None
        self.current_cwd = Path(session.cwd)
        self.config_cwd = Path(session.cwd)
        self.workspace_roots = [Path(root) for root in session.runtime_workspace_roots]
        self.permissions_workspace_roots = list(self.workspace_roots)
        self.effective_service_tier = session.service_tier
        self.approval_policy = session.approval_policy
        self.permission_snapshot = PermissionProfileSnapshot(
            session.permission_profile,
            session.active_permission_profile,
        )
        self.approvals_reviewer = session.approvals_reviewer
        self.personality = session.personality
        self.status_line_project_root_name_cache = None

        default_model = session.model
        self.current_collaboration_mode = self.current_collaboration_mode.with_updates(
            default_model,
            session.reasoning_effort,
            None,
        )
        if session.collaboration_mode is not None:
            self.set_effective_collaboration_mode(session.collaboration_mode)
        else:
            self.active_collaboration_mask = self.initial_collaboration_mask(
                default_model,
                session.reasoning_effort,
            )
            self.update_collaboration_mode_indicator()
            self.refresh_plan_mode_nudge()

        self.refresh_model_display()
        self.refresh_status_surfaces()
        self.sync_service_tier_commands()
        self.sync_personality_command_enabled()
        self.sync_plugins_command_enabled()
        self.sync_goal_command_enabled()
        self.refresh_plugin_mentions()

        if display is SessionConfiguredDisplay.NORMAL:
            cell = SessionInfoCellPlan(
                model=self.current_model(),
                thread_id=session.thread_id,
                display_welcome_banner=self.show_welcome_banner,
                plan_type=self.plan_type,
                show_fast_status=self.should_show_fast_status(default_model, session.service_tier),
                startup_tooltip_override=self.startup_tooltip_override,
            )
            self.startup_tooltip_override = None
            self.apply_session_info_cell(cell)
        elif self.active_cell_is_session_header:
            self.active_cell_is_session_header = False
            self.bump_active_cell_revision()

        self.saw_copy_source_this_turn = False
        self.refresh_skills_for_current_cwd(force_reload=True)
        if self.connectors_enabled():
            self.prefetch_connectors()

        if self.initial_user_message is not None:
            user_message = self.initial_user_message
            self.initial_user_message = None
            if self.suppress_initial_user_message_submit:
                self.initial_user_message = user_message
            else:
                self.submit_user_message(user_message)

        if display is SessionConfiguredDisplay.NORMAL and session.forked_from_id is not None:
            self.emit_forked_thread_event(session.forked_from_id, fork_parent_title)

        if not self.suppress_session_configured_redraw:
            self.request_redraw()

    def emit_forked_thread_event(
        self,
        forked_from_id: str,
        fork_parent_title: Optional[str],
    ) -> None:
        event = ForkedThreadEvent(str(forked_from_id), fork_parent_title)
        self.forked_thread_events.append(event)
        self.emitted_history_lines.append(event.line_text())

    def on_thread_name_updated(self, thread_id: str, thread_name: Optional[str]) -> None:
        if self.thread_id != thread_id:
            return
        if thread_name is not None:
            self.rename_confirmation_cells.append(
                RenameConfirmationPlan(self.thread_id, thread_name)
            )
        self.thread_name = thread_name
        self.refresh_status_surfaces()
        self.request_redraw()
        self.maybe_send_next_queued_input()

    def set_skills(self, skills: Optional[Any]) -> None:
        self.skills = skills

    def current_model(self) -> str:
        return self.current_collaboration_mode.model or ""

    def initial_collaboration_mask(
        self,
        model: str,
        reasoning_effort: Optional[Any],
    ) -> CollaborationModeMask:
        return CollaborationModeMask(reasoning_effort=reasoning_effort)

    def set_effective_collaboration_mode(self, collaboration_mode: str) -> None:
        self.active_collaboration_mask = CollaborationModeMask(
            reasoning_effort=self.current_collaboration_mode.reasoning_effort
        )
        self.update_collaboration_mode_indicator()
        self.refresh_plan_mode_nudge()

    def should_show_fast_status(self, model: str, service_tier: Optional[str]) -> bool:
        return service_tier == "flex"

    def apply_session_info_cell(self, cell: SessionInfoCellPlan) -> None:
        self.applied_session_info_cells.append(cell)

    def submit_user_message(self, user_message: Any) -> None:
        self.submitted_user_messages.append(user_message)

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def refresh_plan_mode_nudge(self) -> None:
        self.plan_mode_nudge_refreshes += 1

    def update_collaboration_mode_indicator(self) -> None:
        self.collaboration_indicator_updates += 1

    def refresh_model_display(self) -> None:
        self.model_display_refreshes += 1

    def refresh_status_surfaces(self) -> None:
        self.status_surface_refreshes += 1

    def sync_service_tier_commands(self) -> None:
        self.service_tier_syncs += 1

    def sync_personality_command_enabled(self) -> None:
        self.personality_command_syncs += 1

    def sync_plugins_command_enabled(self) -> None:
        self.plugins_command_syncs += 1

    def sync_goal_command_enabled(self) -> None:
        self.goal_command_syncs += 1

    def refresh_plugin_mentions(self) -> None:
        self.plugin_mention_refreshes += 1

    def refresh_skills_for_current_cwd(self, force_reload: bool) -> None:
        self.skills_refreshes.append(force_reload)

    def connectors_enabled(self) -> bool:
        return self.connectors_feature_enabled

    def prefetch_connectors(self) -> None:
        self.connector_prefetches += 1

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision_bumps += 1

    def maybe_send_next_queued_input(self) -> None:
        self.maybe_send_next_queued_input_calls += 1


__all__ = [
    "CollaborationModeMask",
    "CollaborationModeState",
    "ForkedThreadEvent",
    "MessageHistoryMetadata",
    "PermissionProfileSnapshot",
    "RUST_MODULE",
    "RenameConfirmationPlan",
    "SessionConfiguredDisplay",
    "SessionFlowModel",
    "SessionInfoCellPlan",
    "ThreadSessionState",
]
