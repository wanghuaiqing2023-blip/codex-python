import importlib
from pathlib import Path

import pycodex.state as state


CONSTANTS = {
    "SQLITE_HOME_ENV": "CODEX_SQLITE_HOME",
    "LOGS_DB_FILENAME": "logs_2.sqlite",
    "GOALS_DB_FILENAME": "goals_1.sqlite",
    "MEMORIES_DB_FILENAME": "memories_1.sqlite",
    "STATE_DB_FILENAME": "state_5.sqlite",
    "DB_ERROR_METRIC": "codex.db.error",
    "DB_METRIC_BACKFILL": "codex.db.backfill",
    "DB_METRIC_BACKFILL_DURATION_MS": "codex.db.backfill.duration_ms",
    "DB_INIT_METRIC": "codex.sqlite.init.count",
    "DB_INIT_DURATION_METRIC": "codex.sqlite.init.duration_ms",
    "DB_FALLBACK_METRIC": "codex.sqlite.fallback.count",
}


REEXPORTS = {
    "ThreadStateAuditRow": "pycodex.state.audit",
    "read_thread_state_audit_rows": "pycodex.state.audit",
    "apply_rollout_item": "pycodex.state.extract",
    "rollout_item_affects_thread_metadata": "pycodex.state.extract",
    "LogEntry": "pycodex.state.model",
    "LogQuery": "pycodex.state.model",
    "LogRow": "pycodex.state.model",
    "Phase2JobClaimOutcome": "pycodex.state.model",
    "AgentJob": "pycodex.state.model",
    "AgentJobCreateParams": "pycodex.state.model",
    "AgentJobItem": "pycodex.state.model",
    "AgentJobItemCreateParams": "pycodex.state.model",
    "AgentJobItemStatus": "pycodex.state.model",
    "AgentJobProgress": "pycodex.state.model",
    "AgentJobStatus": "pycodex.state.model",
    "Anchor": "pycodex.state.model",
    "BackfillState": "pycodex.state.model",
    "BackfillStats": "pycodex.state.model",
    "BackfillStatus": "pycodex.state.model",
    "DirectionalThreadSpawnEdgeStatus": "pycodex.state.model",
    "ExtractionOutcome": "pycodex.state.model",
    "SortDirection": "pycodex.state.model",
    "SortKey": "pycodex.state.model",
    "Stage1JobClaim": "pycodex.state.model",
    "Stage1JobClaimOutcome": "pycodex.state.model",
    "Stage1Output": "pycodex.state.model",
    "Stage1StartupClaimParams": "pycodex.state.model",
    "ThreadGoal": "pycodex.state.model",
    "ThreadGoalStatus": "pycodex.state.model",
    "ThreadMetadata": "pycodex.state.model",
    "ThreadMetadataBuilder": "pycodex.state.model",
    "ThreadsPage": "pycodex.state.model",
    "GoalAccountingMode": "pycodex.state.runtime",
    "GoalAccountingOutcome": "pycodex.state.runtime",
    "GoalStore": "pycodex.state.runtime",
    "GoalUpdate": "pycodex.state.runtime",
    "MemoryStore": "pycodex.state.runtime",
    "RemoteControlEnrollmentRecord": "pycodex.state.runtime",
    "ThreadFilterOptions": "pycodex.state.runtime",
    "sqlite_integrity_check": "pycodex.state.state_runtime",
    "StateRuntime": "pycodex.state.state_runtime",
    "DbTelemetry": "pycodex.state.telemetry",
    "DbTelemetryHandle": "pycodex.state.telemetry",
    "install_process_db_telemetry": "pycodex.state.telemetry",
    "record_backfill_gate": "pycodex.state.telemetry",
    "record_fallback": "pycodex.state.telemetry",
}


def test_lib_rs_constants_match_rust_values() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/lib.rs DB filename/env/metric constants
    # Behavior contract: crate-root constants preserve Rust's public string values.
    for name, expected in CONSTANTS.items():
        assert getattr(state, name) == expected
        assert name in state.__all__


def test_lib_rs_runtime_db_paths_use_crate_root_filenames() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/lib.rs DB filename constants and runtime path re-exports
    # Behavior contract: crate-root path helpers use the same DB filenames exposed
    # as public constants.
    codex_home = Path("/tmp/codex-home")

    assert state.state_db_path(codex_home) == codex_home / state.STATE_DB_FILENAME
    assert state.logs_db_path(codex_home) == codex_home / state.LOGS_DB_FILENAME
    assert state.goals_db_path(codex_home) == codex_home / state.GOALS_DB_FILENAME
    assert state.memories_db_path(codex_home) == codex_home / state.MEMORIES_DB_FILENAME


def test_lib_rs_reexports_selected_rust_public_anchors() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/lib.rs public `pub use` surface
    # Behavior contract: the Python package root exposes the Rust-shaped public
    # anchors while behavior remains owned by each child module.
    for name, module_name in REEXPORTS.items():
        child_module = importlib.import_module(module_name)
        assert getattr(state, name) is getattr(child_module, name)
        assert name in state.__all__
