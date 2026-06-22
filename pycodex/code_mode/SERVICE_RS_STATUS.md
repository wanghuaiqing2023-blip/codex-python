# codex-code-mode src/service.rs dependency-light facade status

Rust coordinate: `codex/codex-rs/code-mode/src/service.rs`

Python coordinate: `pycodex/code_mode/__init__.py` via
`pycodex.core.tools.code_mode.CodeModeService`

Status: `complete` for the dependency-light public service facade.

## Behavior Contract

- `CodeModeService::new` initializes an empty service with cell id allocation
  starting at `1`.
- `allocate_cell_id` returns monotonically increasing string ids.
- `wait` and `wait_to_pending` preserve Rust missing-cell provenance by
  returning missing-cell outcomes that wrap a `RuntimeResponse::Result` with
  `exec cell {cell_id} not found`.
- `execute`, `execute_to_pending`, `wait`, and `wait_to_pending` accept the
  public request model shapes and adapt callback return values into the Rust
  public outcome variants.
- `execute_to_pending` without a dedicated pending callback uses the terminal
  execute response as a completed pending outcome, matching the Rust
  terminal-response branch for `SessionResponseSender::ExecuteToPending`.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/service.rs`
- Rust tests/contracts:
  - `wait_reports_missing_cell_separately_from_runtime_results`
  - service tests that exercise synchronous completed results,
    execute-to-pending pending/completed boundaries, wait missing-cell
    provenance, and terminal response forwarding.
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

This status covers the dependency-light public service facade only. Concrete
Tokio session control, V8 isolate lifecycle, module loading, timers,
termination, turn-worker dispatch, and isolate-backed store/load behavior
remain optional operational/runtime checks tracked at crate level.
