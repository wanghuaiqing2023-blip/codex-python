# codex-code-mode src/runtime/mod.rs public model status

Rust coordinate: `codex/codex-rs/code-mode/src/runtime/mod.rs`

Python coordinate: `pycodex/code_mode/__init__.py` via
`pycodex.core.tools.code_mode`

Status: `complete` for the public request/response/outcome model surface.

## Behavior Contract

- `DEFAULT_EXEC_YIELD_TIME_MS`, `DEFAULT_WAIT_YIELD_TIME_MS`, and
  `DEFAULT_MAX_OUTPUT_TOKENS_PER_EXEC_CALL`.
- `ExecuteRequest`, `WaitRequest`, and `WaitToPendingRequest` public request
  shapes, including Rust field names and non-negative timing/token fields.
- `RuntimeResponse::{Yielded,Terminated,Result}` public variants, including
  Rust external tagged enum input projection and Python model-facing mapping.
- `WaitOutcome::{LiveCell,MissingCell}` provenance and
  `impl From<WaitOutcome> for RuntimeResponse`-equivalent conversion.
- `ExecuteToPendingOutcome::{Pending,Completed}` and
  `WaitToPendingOutcome::{LiveCell,MissingCell}` public lifecycle shapes.
- `CodeModeNestedToolCall` public fields and owned `input` projection.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/mod.rs`
- Rust usage/tests:
  - `runtime/mod.rs::tests::pending_mode_freezes_runtime_commands_until_resume`
  - `service.rs` tests using pending/completed/missing outcomes and runtime
    responses as the public lifecycle transport.
- Python tests: `tests/test_codex_code_mode_lib_rs.py`

## Validation

- `python -m pytest tests/test_codex_code_mode_lib_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\code_mode\__init__.py pycodex\core\tools\code_mode\__init__.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21.

## Non-blocking runtime notes

This status intentionally covers only the public model surface from
`runtime/mod.rs`. Concrete V8 isolate execution, module loading, timers,
termination, Tokio session control, turn-worker dispatch, and store/load
runtime behavior remain optional operational/runtime checks tracked at crate
level.
