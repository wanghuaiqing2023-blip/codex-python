# `codex-state/src/telemetry.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/telemetry.rs`
- Public anchors:
  - `DbTelemetry`
  - `DbTelemetryHandle`
  - `install_process_db_telemetry`
  - `record_backfill_gate`
  - `record_fallback`
- Important internal anchors:
  - `DbKind`
  - `DbOutcomeTags`
  - `record_init_result`
  - `classify_sqlite_code`

This module owns best-effort SQLite startup/fallback telemetry and error
classification. Database opening, migrations, and runtime store behavior remain
separate module contracts.

## Python mapping

- Module: `pycodex/state/telemetry.py`
- Re-exported through `pycodex/state/__init__.py`.

The Python port mirrors install-once process telemetry behavior, override sink
resolution, counter/duration recording, backfill gate/fallback tags, DB kind
labels, success/failure outcome tags, and SQLite primary/extended result-code
classification. Python exception classification maps native JSON, OS, and
SQLite-like exception attributes into the same low-cardinality tag set where
possible.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_telemetry_rs.py -q
# 9 passed

python -m py_compile pycodex\state\telemetry.py pycodex\state\__init__.py tests\test_state_telemetry_rs.py
```

Coverage includes Rust's extended SQLite code classification test,
primary/unknown SQLite code mapping, install-once process telemetry, explicit
override resolution, init/backfill/fallback tags, outcome/error
classification, no-op behavior without a sink, and Python sink/duration input
validation.

## Remaining crate work

Other `codex-state` modules remain open for focused formal validation before
the crate can be promoted from `implemented_candidate` to strict `complete`.
