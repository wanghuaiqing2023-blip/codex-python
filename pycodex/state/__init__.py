"""State runtime path helpers.

Ported from the runtime path pieces of:

- ``codex/codex-rs/state/src/lib.rs``
- ``codex/codex-rs/state/src/runtime.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import ThreadStateAuditRow, read_thread_state_audit_rows
from .migrations import (
    GOALS_MIGRATOR,
    LOGS_MIGRATOR,
    MEMORIES_MIGRATOR,
    STATE_MIGRATOR,
    Migrator,
    runtime_goals_migrator,
    runtime_logs_migrator,
    runtime_memories_migrator,
    runtime_migrator,
    runtime_state_migrator,
)
from .model import (
    AgentJob,
    AgentJobCreateParams,
    AgentJobItem,
    AgentJobItemCreateParams,
    AgentJobItemRow,
    AgentJobItemStatus,
    AgentJobProgress,
    AgentJobRow,
    AgentJobStatus,
    Anchor,
    BackfillState,
    BackfillStats,
    BackfillStatus,
    DirectionalThreadSpawnEdgeStatus,
    ExtractionOutcome,
    LogEntry,
    LogQuery,
    LogRow,
    Phase2JobClaimOutcome,
    Phase2JobClaimed,
    SortDirection,
    SortKey,
    Stage1JobClaim,
    Stage1JobClaimOutcome,
    Stage1JobClaimed,
    Stage1Output,
    Stage1StartupClaimParams,
    ThreadGoal,
    ThreadGoalRow,
    ThreadGoalStatus,
    ThreadMetadata,
    ThreadMetadataBuilder,
    ThreadRow,
    ThreadsPage,
    anchor_from_item,
    claimed_phase2,
    claimed_stage1,
    datetime_to_epoch_millis,
    datetime_to_epoch_seconds,
    epoch_millis_to_datetime,
    epoch_seconds_to_datetime,
)
from .extract import (
    IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER,
    apply_rollout_item,
    enum_to_string,
    rollout_item_affects_thread_metadata,
    strip_user_message_prefix,
    user_message_preview,
)
from .log_db import (
    LOG_BATCH_SIZE,
    LOG_FLUSH_INTERVAL_SECONDS,
    LOG_QUEUE_CAPACITY,
    LogDbLayer,
    LogInsertSink,
    LogSinkQueueConfig,
    MessageVisitor,
    SpanFieldVisitor,
    SpanLogContext,
    append_fields,
    current_process_log_uuid,
    event_thread_id,
    format_feedback_log_body,
    format_fields,
    log_entry_from_event,
    start,
)
from .paths import file_modified_time_utc
from .runtime import (
    AgentJobStore,
    LOG_PARTITION_ROW_LIMIT,
    LOG_PARTITION_SIZE_LIMIT_BYTES,
    LOG_RETENTION_DAYS,
    DEFAULT_RETRY_REMAINING,
    JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL,
    JOB_KIND_MEMORY_STAGE1,
    MEMORY_CONSOLIDATION_JOB_KEY,
    MemoryStore,
    PHASE2_INPUT_SELECTION_PAGE_SIZE,
    PHASE2_SUCCESS_COOLDOWN_SECONDS,
    REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE,
    RemoteControlEnrollmentRecord,
    RuntimeLogStore,
    RuntimeThreadStore,
    TOKEN_BUDGET_UNCHANGED,
    TEST_THREAD_METADATA_TIMESTAMP,
    ThreadFilterOptions,
    UNSET_GIT_FIELD,
    app_server_client_name_from_key,
    checkpoint_backfill,
    delete_remote_control_enrollment,
    ensure_backfill_state_row,
    get_backfill_state,
    get_remote_control_enrollment,
    GoalAccountingMode,
    GoalAccountingOutcome,
    GoalStore,
    GoalUpdate,
    format_feedback_log_line,
    insert_log,
    mark_backfill_complete,
    mark_backfill_running,
    remote_control_app_server_client_name_key,
    test_thread_metadata,
    try_claim_backfill,
    unique_temp_dir,
    upsert_remote_control_enrollment,
)

STATE_DB_FILENAME = "state_5.sqlite"
LOGS_DB_FILENAME = "logs_2.sqlite"
GOALS_DB_FILENAME = "goals_1.sqlite"
MEMORIES_DB_FILENAME = "memories_1.sqlite"
SQLITE_HOME_ENV = "CODEX_SQLITE_HOME"

DB_ERROR_METRIC = "codex.db.error"
DB_METRIC_BACKFILL = "codex.db.backfill"
DB_METRIC_BACKFILL_DURATION_MS = "codex.db.backfill.duration_ms"
DB_INIT_METRIC = "codex.sqlite.init.count"
DB_INIT_DURATION_METRIC = "codex.sqlite.init.duration_ms"
DB_FALLBACK_METRIC = "codex.sqlite.fallback.count"

from .telemetry import (  # noqa: E402
    DbKind,
    DbOutcomeTags,
    DbTelemetry,
    DbTelemetryHandle,
    classify_error,
    classify_sqlite_code,
    install_process_db_telemetry,
    record_backfill_gate,
    record_counter,
    record_duration,
    record_fallback,
    record_init_result,
    resolve_telemetry,
)
from .state_runtime import (  # noqa: E402
    GOALS_DB,
    LOGS_DB,
    MEMORIES_DB,
    RUNTIME_DBS,
    STATE_DB,
    RuntimeDbSpec,
    StateRuntime,
    open_goals_sqlite,
    open_logs_sqlite,
    open_memories_sqlite,
    open_sqlite,
    open_state_sqlite,
    sqlite_integrity_check,
)


@dataclass(frozen=True)
class RuntimeDbPath:
    label: str
    path: Path


def state_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / STATE_DB_FILENAME


def logs_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / LOGS_DB_FILENAME


def goals_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / GOALS_DB_FILENAME


def memories_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / MEMORIES_DB_FILENAME


def runtime_db_paths(codex_home: Path | str) -> list[RuntimeDbPath]:
    root = _path(codex_home, "codex_home")
    return [
        RuntimeDbPath("state DB", root / STATE_DB_FILENAME),
        RuntimeDbPath("log DB", root / LOGS_DB_FILENAME),
        RuntimeDbPath("goals DB", root / GOALS_DB_FILENAME),
        RuntimeDbPath("memories DB", root / MEMORIES_DB_FILENAME),
    ]


def _path(value: Path | str, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{label} must be a string or Path")
    return Path(value)


__all__ = [
    "AgentJob",
    "AgentJobCreateParams",
    "AgentJobItem",
    "AgentJobItemCreateParams",
    "AgentJobItemRow",
    "AgentJobItemStatus",
    "AgentJobProgress",
    "AgentJobRow",
    "AgentJobStatus",
    "AgentJobStore",
    "Anchor",
    "BackfillState",
    "BackfillStats",
    "BackfillStatus",
    "DB_ERROR_METRIC",
    "DB_FALLBACK_METRIC",
    "DB_INIT_DURATION_METRIC",
    "DB_INIT_METRIC",
    "DB_METRIC_BACKFILL",
    "DB_METRIC_BACKFILL_DURATION_MS",
    "DbKind",
    "DbOutcomeTags",
    "DbTelemetry",
    "DbTelemetryHandle",
    "DEFAULT_RETRY_REMAINING",
    "DirectionalThreadSpawnEdgeStatus",
    "ExtractionOutcome",
    "GOALS_DB_FILENAME",
    "GOALS_DB",
    "GOALS_MIGRATOR",
    "IMAGE_ONLY_USER_MESSAGE_PLACEHOLDER",
    "JOB_KIND_MEMORY_CONSOLIDATE_GLOBAL",
    "JOB_KIND_MEMORY_STAGE1",
    "LOGS_DB_FILENAME",
    "LOGS_DB",
    "LOGS_MIGRATOR",
    "LOG_BATCH_SIZE",
    "LOG_FLUSH_INTERVAL_SECONDS",
    "LOG_PARTITION_ROW_LIMIT",
    "LOG_PARTITION_SIZE_LIMIT_BYTES",
    "LOG_QUEUE_CAPACITY",
    "LOG_RETENTION_DAYS",
    "LogDbLayer",
    "LogEntry",
    "LogInsertSink",
    "LogQuery",
    "LogRow",
    "LogSinkQueueConfig",
    "MEMORIES_DB_FILENAME",
    "MEMORIES_DB",
    "MEMORIES_MIGRATOR",
    "MEMORY_CONSOLIDATION_JOB_KEY",
    "MemoryStore",
    "MessageVisitor",
    "Migrator",
    "Phase2JobClaimOutcome",
    "Phase2JobClaimed",
    "PHASE2_INPUT_SELECTION_PAGE_SIZE",
    "PHASE2_SUCCESS_COOLDOWN_SECONDS",
    "REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE",
    "RemoteControlEnrollmentRecord",
    "RuntimeLogStore",
    "RuntimeThreadStore",
    "RuntimeDbPath",
    "RuntimeDbSpec",
    "RUNTIME_DBS",
    "SQLITE_HOME_ENV",
    "SortDirection",
    "SortKey",
    "SpanFieldVisitor",
    "SpanLogContext",
    "STATE_MIGRATOR",
    "STATE_DB",
    "STATE_DB_FILENAME",
    "StateRuntime",
    "Stage1JobClaim",
    "Stage1JobClaimOutcome",
    "Stage1JobClaimed",
    "Stage1Output",
    "Stage1StartupClaimParams",
    "ThreadGoal",
    "ThreadGoalRow",
    "ThreadGoalStatus",
    "ThreadMetadata",
    "ThreadMetadataBuilder",
    "ThreadRow",
    "ThreadsPage",
    "ThreadStateAuditRow",
    "TOKEN_BUDGET_UNCHANGED",
    "TEST_THREAD_METADATA_TIMESTAMP",
    "ThreadFilterOptions",
    "anchor_from_item",
    "app_server_client_name_from_key",
    "apply_rollout_item",
    "append_fields",
    "checkpoint_backfill",
    "claimed_phase2",
    "claimed_stage1",
    "classify_error",
    "classify_sqlite_code",
    "current_process_log_uuid",
    "enum_to_string",
    "epoch_millis_to_datetime",
    "epoch_seconds_to_datetime",
    "event_thread_id",
    "datetime_to_epoch_millis",
    "datetime_to_epoch_seconds",
    "delete_remote_control_enrollment",
    "ensure_backfill_state_row",
    "file_modified_time_utc",
    "format_feedback_log_body",
    "format_feedback_log_line",
    "format_fields",
    "goals_db_path",
    "get_backfill_state",
    "get_remote_control_enrollment",
    "GoalAccountingMode",
    "GoalAccountingOutcome",
    "GoalStore",
    "GoalUpdate",
    "install_process_db_telemetry",
    "insert_log",
    "log_entry_from_event",
    "logs_db_path",
    "mark_backfill_complete",
    "mark_backfill_running",
    "memories_db_path",
    "open_goals_sqlite",
    "open_logs_sqlite",
    "open_memories_sqlite",
    "open_sqlite",
    "open_state_sqlite",
    "record_backfill_gate",
    "record_counter",
    "record_duration",
    "record_fallback",
    "record_init_result",
    "read_thread_state_audit_rows",
    "remote_control_app_server_client_name_key",
    "resolve_telemetry",
    "runtime_goals_migrator",
    "runtime_logs_migrator",
    "runtime_memories_migrator",
    "runtime_migrator",
    "runtime_db_paths",
    "runtime_state_migrator",
    "rollout_item_affects_thread_metadata",
    "sqlite_integrity_check",
    "state_db_path",
    "start",
    "strip_user_message_prefix",
    "test_thread_metadata",
    "try_claim_backfill",
    "UNSET_GIT_FIELD",
    "unique_temp_dir",
    "upsert_remote_control_enrollment",
    "user_message_preview",
]
