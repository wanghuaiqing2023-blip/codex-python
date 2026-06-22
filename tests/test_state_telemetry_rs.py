from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

import pycodex.state.telemetry as telemetry_module
from pycodex.state import (
    DB_FALLBACK_METRIC,
    DB_INIT_DURATION_METRIC,
    DB_INIT_METRIC,
    DbKind,
    DbOutcomeTags,
    classify_error,
    classify_sqlite_code,
    install_process_db_telemetry,
    record_backfill_gate,
    record_fallback,
    record_init_result,
    resolve_telemetry,
)


@dataclass
class RecordingTelemetry:
    counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] = field(default_factory=list)
    durations: list[tuple[str, timedelta, tuple[tuple[str, str], ...]]] = field(default_factory=list)

    def counter(self, name: str, inc: int, tags: tuple[tuple[str, str], ...]) -> None:
        self.counters.append((name, inc, tags))

    def record_duration(self, name: str, duration: timedelta, tags: tuple[tuple[str, str], ...]) -> None:
        self.durations.append((name, duration, tags))


def _reset_process_telemetry() -> None:
    with telemetry_module._PROCESS_DB_TELEMETRY_LOCK:
        telemetry_module._PROCESS_DB_TELEMETRY = None


def test_classifies_extended_sqlite_codes() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/telemetry.rs::classifies_extended_sqlite_codes
    # Behavior contract: extended SQLite result codes preserve the primary code
    # in the low byte for low-cardinality classification.
    assert classify_sqlite_code("5") == "busy"
    assert classify_sqlite_code("6") == "locked"
    assert classify_sqlite_code("2067") == "constraint"


def test_classify_sqlite_code_primary_mapping_and_unknown_values() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/telemetry.rs::classify_sqlite_code
    # Behavior contract: known SQLite primary codes map to stable tags and
    # malformed or unrecognized codes become unknown.
    assert classify_sqlite_code("8") == "readonly"
    assert classify_sqlite_code("10") == "io"
    assert classify_sqlite_code("11") == "corrupt"
    assert classify_sqlite_code("13") == "full"
    assert classify_sqlite_code("14") == "cantopen"
    assert classify_sqlite_code("17") == "schema"
    assert classify_sqlite_code("not-a-code") == "unknown"
    assert classify_sqlite_code("999") == "unknown"


def test_install_process_db_telemetry_is_install_once_and_resolved_by_default() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/telemetry.rs::install_process_db_telemetry
    # Behavior contract: the process-wide sink installs once and duplicate
    # installs keep the first sink.
    _reset_process_telemetry()
    first = RecordingTelemetry()
    second = RecordingTelemetry()

    assert install_process_db_telemetry(first) is True
    assert install_process_db_telemetry(second) is False
    assert resolve_telemetry(None) is first
    assert resolve_telemetry(second) is second


def test_record_init_result_records_counter_and_duration_tags() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/telemetry.rs::record_init_result
    # Behavior contract: init recording emits count and duration metrics with
    # status, phase, db, and error tags.
    sink = RecordingTelemetry()

    record_init_result(sink, DbKind.LOGS, "open", 1.25, None)

    tags = (
        ("status", "success"),
        ("phase", "open"),
        ("db", "logs"),
        ("error", "none"),
    )
    assert sink.counters == [(DB_INIT_METRIC, 1, tags)]
    assert sink.durations == [(DB_INIT_DURATION_METRIC, timedelta(seconds=1.25), tags)]


def test_record_backfill_gate_classifies_failures_and_uses_state_db_phase() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/telemetry.rs::record_backfill_gate
    # Behavior contract: backfill gate delegates to init-result recording for
    # the state DB with phase backfill_gate.
    sink = RecordingTelemetry()
    err = OSError("disk")

    record_backfill_gate(sink, timedelta(milliseconds=25), err)

    tags = (
        ("status", "failed"),
        ("phase", "backfill_gate"),
        ("db", "state"),
        ("error", "io"),
    )
    assert sink.counters == [(DB_INIT_METRIC, 1, tags)]
    assert sink.durations == [(DB_INIT_DURATION_METRIC, timedelta(milliseconds=25), tags)]


def test_record_fallback_uses_override_sink_and_expected_tags() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/telemetry.rs::record_fallback
    # Behavior contract: fallback recording emits one counter with caller and
    # reason tags through the explicit override sink.
    _reset_process_telemetry()
    process_sink = RecordingTelemetry()
    override_sink = RecordingTelemetry()
    assert install_process_db_telemetry(process_sink) is True

    record_fallback("runtime", "integrity_check_failed", override_sink)

    assert process_sink.counters == []
    assert override_sink.counters == [
        (
            DB_FALLBACK_METRIC,
            1,
            (("caller", "runtime"), ("reason", "integrity_check_failed")),
        )
    ]


def test_outcome_tags_and_error_classification_match_low_cardinality_set() -> None:
    # Rust crate: codex-state
    # Rust module/items: DbOutcomeTags::from_result, classify_error
    # Behavior contract: results become success/failed tags and known exception
    # classes/codes map to Rust's low-cardinality error labels where possible.
    assert DbOutcomeTags.from_result(None) == DbOutcomeTags(status="success", error="none")
    assert DbOutcomeTags.from_result(True) == DbOutcomeTags(status="success", error="none")
    assert DbOutcomeTags.from_result(OSError("disk")) == DbOutcomeTags(status="failed", error="io")

    json_error = json.JSONDecodeError("bad", "x", 0)
    assert classify_error(json_error) == "serde"
    assert classify_error(OSError("disk")) == "io"

    class SqliteLikeError(Exception):
        sqlite_errorcode = 2067

    assert classify_error(SqliteLikeError("constraint")) == "constraint"

    class MigrateFailed(Exception):
        pass

    assert classify_error(MigrateFailed("migration failed")) == "migration"
    assert classify_error(RuntimeError("plain")) == "unknown"


def test_record_helpers_noop_without_sink() -> None:
    # Rust crate: codex-state
    # Rust module/items: record_counter, record_duration, resolve_telemetry
    # Behavior contract: telemetry export is best-effort and absent sinks are
    # no-ops.
    _reset_process_telemetry()

    record_init_result(None, DbKind.STATE, "open", 0.0, None)
    record_fallback("runtime", "no_sink", None)

    assert resolve_telemetry(None) is None


def test_invalid_process_sink_and_duration_are_rejected() -> None:
    # Rust crate: codex-state
    # Rust module/items: install_process_db_telemetry, record_duration input
    # Behavior contract: Python keeps a narrow sink/duration interface for the
    # Rust telemetry contract.
    _reset_process_telemetry()

    with pytest.raises(TypeError, match="telemetry must implement DbTelemetry"):
        install_process_db_telemetry(object())
    with pytest.raises(TypeError, match="duration must be a timedelta or seconds value"):
        record_init_result(RecordingTelemetry(), DbKind.STATE, "open", object(), None)
