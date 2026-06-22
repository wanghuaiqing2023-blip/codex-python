# `codex-state/src/log_db.rs` Python alignment

Status: `complete`

Rust owner:

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/log_db.rs`

Python owner:

- Module: `pycodex/state/log_db.py`
- Package export: `pycodex.state`

## Behavior contract

This pass mirrors the module-scoped log sink behavior that can be represented
without Rust's `tracing_subscriber` and Tokio runtime:

- Queue defaults and normalization:
  - `LOG_QUEUE_CAPACITY = 512`
  - `LOG_BATCH_SIZE = 128`
  - zero flush interval normalizes back to the default two-second interval
  - queue capacity and batch size are clamped to at least one
- A process-stable log UUID using Rust's `pid:{pid}:{uuid}` shape.
- `MessageVisitor` and `SpanFieldVisitor` first-match extraction for
  `message` and `thread_id`.
- `SpanLogContext`, span-root ordering, and event formatting for
  feedback-log body construction.
- `log_entry_from_event` construction of the ported `LogEntry` model,
  including seconds/nanoseconds timestamps, metadata fields, message,
  feedback-log body, span-derived thread id fallback, and process UUID.
- `LogDbLayer` start/start-with-config, bounded drop-new-entry queueing, event
  emission, and explicit flush through a sink's `insert_logs` method.

## Intentional Python adaptation

Rust implements this module as a `tracing_subscriber::Layer` that sends commands
to a Tokio background inserter with timer-driven flushes. Python does not have
that tracing runtime in this package. The Python module therefore preserves the
data-shaping and explicit flush contract with a dependency-light standard
library queue facade. Timer-driven background flushing is left to the future
runtime log-store integration module.

## Validation

Formal parity validation passed on 2026-06-17:

```text
python -m pytest tests\test_state_log_db_rs.py -q
7 passed

python -m py_compile pycodex\state\log_db.py pycodex\state\__init__.py tests\test_state_log_db_rs.py
```

The pytest suite covers queue defaults/normalization, process UUID stability,
message/thread visitor first-match behavior, span-root feedback body
formatting, event-to-`LogEntry` conversion, bounded queue drop-new-entry
behavior, explicit async flush, and validation errors for invalid config and
fields.
