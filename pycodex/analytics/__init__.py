"""Source-verified public interface slice for ``codex-analytics``.

Rust source:
- ``codex/codex-rs/analytics/src/lib.rs``
- ``codex/codex-rs/analytics/src/accepted_lines.rs``
- ``codex/codex-rs/analytics/src/facts.rs``
- ``codex/codex-rs/analytics/src/events.rs``
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def now_unix_seconds() -> int:
    return int(time.time())


def now_unix_millis() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class AcceptedLineFingerprint:
    path_hash: str
    line_hash: str


@dataclass(frozen=True)
class AcceptedLineFingerprintSummary:
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]


@dataclass(frozen=True)
class AcceptedLineFingerprintEventInput:
    event_type: str
    turn_id: str
    thread_id: str
    product_surface: str | None
    model_slug: str | None
    completed_at: int
    repo_hash: str | None
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]


def fingerprint_hash(domain: str, value: str) -> str:
    hasher = hashlib.sha1()
    hasher.update(b"file-line-v1\0")
    hasher.update(domain.encode())
    hasher.update(b"\0")
    hasher.update(value.encode())
    return hasher.hexdigest()


def accepted_line_fingerprints_from_unified_diff(unified_diff: str) -> AcceptedLineFingerprintSummary:
    current_path: str | None = None
    in_hunk = False
    accepted_added_lines = 0
    accepted_deleted_lines = 0
    fingerprints: list[AcceptedLineFingerprint] = []
    for line in unified_diff.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk and line.startswith("+++ "):
            current_path = _normalize_diff_path(line[4:])
            continue
        if not in_hunk and line.startswith("--- "):
            continue
        if line.startswith("+"):
            accepted_added_lines += 1
            if current_path is not None:
                normalized = _normalize_effective_line(line[1:])
                if normalized is not None:
                    fingerprints.append(AcceptedLineFingerprint(fingerprint_hash("path", current_path), fingerprint_hash("line", normalized)))
            continue
        if line.startswith("-"):
            accepted_deleted_lines += 1
    return AcceptedLineFingerprintSummary(accepted_added_lines, accepted_deleted_lines, fingerprints)


def accepted_line_fingerprint_event_requests(
    input: AcceptedLineFingerprintEventInput,
) -> list[dict[str, Any]]:
    return [
        {
            "event_type": "codex_accepted_line_fingerprints",
            "event_params": {
                "event_type": input.event_type,
                "turn_id": input.turn_id,
                "thread_id": input.thread_id,
                "product_surface": input.product_surface,
                "model_slug": input.model_slug,
                "completed_at": input.completed_at,
                "repo_hash": input.repo_hash,
                "accepted_added_lines": input.accepted_added_lines,
                "accepted_deleted_lines": input.accepted_deleted_lines,
                "line_fingerprints": [],
            },
        }
    ]


def _normalize_diff_path(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path


def _normalize_effective_line(line: str) -> str | None:
    normalized = " ".join(line.split())
    if len(normalized) <= 3:
        return None
    if not any(ch.isalnum() or ch == "_" for ch in normalized):
        return None
    return normalized


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


class AppServerRpcTransport(_SnakeEnum):
    STDIO = "stdio"
    WEBSOCKET = "websocket"
    IN_PROCESS = "in_process"


class GuardianReviewDecision(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"


class GuardianReviewTerminalStatus(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"
    FAILED_CLOSED = "failed_closed"


class GuardianReviewFailureReason(_SnakeEnum):
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROMPT_BUILD_ERROR = "prompt_build_error"
    SESSION_ERROR = "session_error"
    PARSE_ERROR = "parse_error"


class GuardianReviewSessionKind(_SnakeEnum):
    TRUNK_NEW = "trunk_new"
    TRUNK_REUSED = "trunk_reused"
    EPHEMERAL_FORKED = "ephemeral_forked"


class GuardianApprovalRequestSource(_SnakeEnum):
    MAIN_TURN = "main_turn"
    DELEGATED_SUBAGENT = "delegated_subagent"


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
    PRE_SAMPLING = "pre_sampling"
    MID_TURN = "mid_turn"


class CompactionStatus(_SnakeEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CompactionStrategy(_SnakeEnum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass
class SkillInvocation:
    skill_name: str
    skill_scope: Any
    skill_path: Path
    plugin_id: str | None
    invocation_type: InvocationType


@dataclass
class AppInvocation:
    connector_id: str | None = None
    app_name: str | None = None
    invocation_type: InvocationType | None = None


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
    fields: dict[str, Any]


@dataclass
class CodexCompactionEvent:
    fields: dict[str, Any]


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
    fields: dict[str, Any]


@dataclass
class GuardianReviewTrackContext:
    fields: dict[str, Any]


@dataclass
class GuardianReviewEventParams:
    fields: dict[str, Any]


class GuardianReviewAnalyticsResult(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    FAILED = "failed"


class AnalyticsEventsClient:
    async def record_events(self, *_args: Any, **_kwargs: Any) -> None:
        return None


InputError = TurnSteerRejectionReason
TurnSteerRequestError = TurnSteerRejectionReason
AnalyticsJsonRpcError = TurnSteerRejectionReason
GuardianReviewedAction = dict[str, Any]


__all__ = [name for name in globals() if not name.startswith("_")]
