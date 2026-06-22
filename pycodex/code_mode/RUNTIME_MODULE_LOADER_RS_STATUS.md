# codex-code-mode runtime/module_loader.rs status

Rust crate: `codex-code-mode`

Rust module: `codex/codex-rs/code-mode/src/runtime/module_loader.rs`

Python module: `pycodex.core.tools.code_mode`

Status: `complete` for the dependency-light module-loader state/error
contract.

## Behavior Contract

- `evaluate_main_module(...)` uses `exec_main.mjs` as the main module script
  origin.
- Static imports are unsupported and report
  `Unsupported import in exec: {specifier}`.
- Dynamic imports are unsupported and reject with `unsupported import in exec`.
- A missing or fulfilled pending promise completes with captured stored-value
  writes and no error text.
- A pending promise remains `CompletionState::Pending`.
- Rejected promises normally complete with `value_to_error_text(...)`.
- Rejected exit sentinels complete without error text when runtime exit was
  requested.
- `value_to_error_text(...)` prefers an object `stack` string and otherwise
  serializes the rejected value through the shared output-text helper.

Concrete V8 module compilation, instantiation, evaluation, microtask
checkpointing, PromiseResolver resolution/rejection, module namespace
resolution, and callback-scope host integration remain non-blocking
operational/runtime checks.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/module_loader.rs`
- Rust anchors:
  - `evaluate_main_module`
  - `completion_state`
  - `resolve_tool_response`
  - `dynamic_import_callback`
  - `resolve_module`
  - `script_origin`
  - `is_exit_exception`
- Python implementation:
  - `EXEC_MAIN_MODULE_NAME`
  - `UNSUPPORTED_DYNAMIC_IMPORT_ERROR`
  - `unsupported_static_import_error(...)`
  - `unsupported_dynamic_import_error(...)`
  - `CompletionState`
  - `completion_state_from_rejection(...)`
  - `completion_state_from_exit(...)`
  - `is_exit_exception(...)`
  - `value_to_error_text(...)`
- Python tests:
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_module_loader_completion_helpers_match_upstream_boundaries`

## Validation

```powershell
python -m pytest tests/test_core_code_mode.py -q --tb=short
python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short
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

None for the dependency-light module-loader state/error contract. Concrete V8
module compilation/evaluation, promise state inspection, microtask
checkpointing, module namespace resolution, and live dynamic-import callback
behavior remain optional operational/runtime checks for the broader crate.
