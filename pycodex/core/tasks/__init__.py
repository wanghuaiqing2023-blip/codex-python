"""Task helper modules aligned with ``codex-core::tasks``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.context import TurnAborted
from pycodex.features import Feature
from pycodex.protocol import ContentItem, ResponseItem

from .compact import CompactTask, CompactTaskPlan
from .lifecycle import (
    emit_turn_abort_lifecycle,
    emit_turn_error_lifecycle,
    emit_turn_start_lifecycle,
    emit_turn_stop_lifecycle,
)
from .regular import RegularTask, SessionStartupPrewarmResolution
from .review import (
    REVIEW_INTERRUPTED_ASSISTANT_MESSAGE,
    REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID,
    REVIEW_ROLLOUT_USER_MESSAGE_ID,
    ReviewExitMessages,
    ReviewTask,
    collect_review_user_input,
    normalize_review_template_line_endings,
    parse_review_output_event,
    render_review_exit_interrupted,
    render_review_exit_success,
    review_exit_messages,
)

GRACEFULL_INTERRUPTION_TIMEOUT_MS = 100
TASK_COMPACT_METRIC = "codex.task.compact"
TURN_MEMORY_METRIC = "codex.turn.memory"
TURN_NETWORK_PROXY_METRIC = "codex.turn.network_proxy"


class InterruptedTurnHistoryMarker(str, Enum):
    DISABLED = "disabled"
    CONTEXTUAL_USER = "contextual_user"
    DEVELOPER = "developer"

    @classmethod
    def from_config(cls, config: Any) -> "InterruptedTurnHistoryMarker":
        if not bool(getattr(config, "agent_interrupt_message_enabled", False)):
            return cls.DISABLED
        features = getattr(config, "features", None)
        enabled = getattr(features, "enabled", None)
        if callable(enabled) and enabled(Feature.MULTI_AGENT_V2):
            return cls.DEVELOPER
        return cls.CONTEXTUAL_USER


def interrupted_turn_history_marker(marker: InterruptedTurnHistoryMarker | str) -> ResponseItem | None:
    marker = InterruptedTurnHistoryMarker(marker)
    if marker is InterruptedTurnHistoryMarker.DISABLED:
        return None
    if marker is InterruptedTurnHistoryMarker.CONTEXTUAL_USER:
        return TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE).into_response_item()
    return ResponseItem.message(
        "developer",
        (ContentItem.input_text(TurnAborted.new(TurnAborted.INTERRUPTED_DEVELOPER_GUIDANCE).render()),),
    )


def bool_tag(value: bool) -> str:
    return "true" if value else "false"


def emit_turn_network_proxy_metric(
    session_telemetry: Any,
    network_proxy_active: bool,
    tmp_mem: tuple[str, str],
) -> None:
    session_telemetry.counter(
        TURN_NETWORK_PROXY_METRIC,
        1,
        [("active", bool_tag(network_proxy_active)), tmp_mem],
    )


def emit_turn_memory_metric(
    session_telemetry: Any,
    feature_enabled: bool,
    config_enabled: bool,
    has_citations: bool,
) -> None:
    read_allowed = feature_enabled and config_enabled
    session_telemetry.counter(
        TURN_MEMORY_METRIC,
        1,
        [
            ("read_allowed", bool_tag(read_allowed)),
            ("feature_enabled", bool_tag(feature_enabled)),
            ("config_use_memories", bool_tag(config_enabled)),
            ("has_citations", bool_tag(has_citations)),
        ],
    )


def emit_compact_metric(session_telemetry: Any, compact_type: str, manual: bool) -> None:
    session_telemetry.counter(
        TASK_COMPACT_METRIC,
        1,
        [("type", compact_type), ("manual", bool_tag(manual))],
    )


@dataclass(frozen=True)
class SessionTaskContext:
    session: Any
    turn_extension_data_value: Any

    @classmethod
    def new(cls, session: Any, turn_extension_data: Any) -> "SessionTaskContext":
        return cls(session, turn_extension_data)

    def clone_session(self) -> Any:
        return self.session

    def turn_extension_data(self) -> Any:
        return self.turn_extension_data_value

    def auth_manager(self) -> Any:
        return self.session.services.auth_manager

    def models_manager(self) -> Any:
        return self.session.services.models_manager


__all__ = [
    "CompactTask",
    "CompactTaskPlan",
    "GRACEFULL_INTERRUPTION_TIMEOUT_MS",
    "InterruptedTurnHistoryMarker",
    "RegularTask",
    "REVIEW_INTERRUPTED_ASSISTANT_MESSAGE",
    "REVIEW_ROLLOUT_ASSISTANT_MESSAGE_ID",
    "REVIEW_ROLLOUT_USER_MESSAGE_ID",
    "ReviewExitMessages",
    "ReviewTask",
    "SessionStartupPrewarmResolution",
    "SessionTaskContext",
    "TASK_COMPACT_METRIC",
    "TURN_MEMORY_METRIC",
    "TURN_NETWORK_PROXY_METRIC",
    "bool_tag",
    "collect_review_user_input",
    "emit_compact_metric",
    "emit_turn_abort_lifecycle",
    "emit_turn_error_lifecycle",
    "emit_turn_memory_metric",
    "emit_turn_network_proxy_metric",
    "emit_turn_start_lifecycle",
    "emit_turn_stop_lifecycle",
    "interrupted_turn_history_marker",
    "normalize_review_template_line_endings",
    "parse_review_output_event",
    "render_review_exit_interrupted",
    "render_review_exit_success",
    "review_exit_messages",
]
