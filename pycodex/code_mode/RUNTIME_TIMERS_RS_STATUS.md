# codex-code-mode runtime/timers.rs status

Rust crate: `codex-code-mode`

Rust module: `codex/codex-rs/code-mode/src/runtime/timers.rs`

Python module: `pycodex.core.tools.code_mode`

Status: `complete` for the dependency-light timer normalization contract.

## Behavior Contract

- `schedule_timeout(...)` requires a function callback before scheduling.
- Missing, `null`/`undefined`, uncoercible, non-finite, and non-positive delay
  values normalize to `0` milliseconds.
- Positive fractional delay values are truncated before scheduling.
- Oversized delay values clamp to `u64::MAX`.
- `clear_timeout(...)` treats missing, `null`/`undefined`, non-finite, and
  non-positive ids as no-ops.
- Positive clear-timeout ids are truncated and clamped to `u64::MAX`.
- Uncoercible clear-timeout ids report
  `clearTimeout expects a numeric timeout id`.

The concrete Rust behavior that stores V8 function callbacks, spawns sleeping
threads, sends `RuntimeCommand::TimeoutFired`, and invokes callbacks inside a
V8 `TryCatch` remains a non-blocking operational/runtime check.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/timers.rs`
- Rust anchors:
  - `schedule_timeout`
  - `clear_timeout`
  - `timeout_id_from_args`
  - `normalize_delay_ms`
  - `invoke_timeout_callback`
- Python implementation:
  - `normalize_timeout_delay_ms(...)`
  - `clear_timeout_id_from_value(...)`
- Python tests:
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_timeout_helpers_match_upstream_timer_normalization`

## Validation

```powershell
python -m pytest tests/test_core_code_mode.py -q --tb=short
python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short
python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py
```

Latest result on 2026-06-21:

- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed.

## Non-blocking runtime notes

None for the dependency-light timer normalization contract. Concrete V8
callback storage/invocation, sleeping-thread delivery, runtime-command
dispatch, and Tokio session orchestration remain optional operational/runtime
checks for the broader crate.
