# codex-code-mode src/lib.rs status

Rust coordinate: `codex/codex-rs/code-mode/src/lib.rs`

Python coordinate: `pycodex/code_mode/__init__.py`

Status: `complete` for the crate-root facade, pure
`description.rs`/`response.rs` exports, `runtime/mod.rs` public model surface,
dependency-light `service.rs` public service facade, and dependency-light
`runtime/value.rs` output helper slice, and dependency-light `runtime/timers.rs`
timer normalization slice, and dependency-light `runtime/callbacks.rs` callback
event-shaping slice, and dependency-light `runtime/globals.rs` global
registration projection slice, and dependency-light `runtime/module_loader.rs`
state/error slice.

Implemented Rust-derived behavior:

- `PUBLIC_TOOL_NAME` and `WAIT_TOOL_NAME` constants.
- Crate-root re-exports for description helpers and structs:
  `CODE_MODE_PRAGMA_PREFIX`, `CodeModeToolKind`, `ToolDefinition`,
  `ToolNamespaceDescription`, `augment_tool_definition`,
  `build_exec_tool_description`, `build_wait_tool_description`,
  `is_code_mode_nested_tool`, `normalize_code_mode_identifier`,
  `parse_exec_source`, `render_code_mode_sample`, and
  `render_json_schema_to_typescript`.
- Response exports: `DEFAULT_IMAGE_DETAIL`, `FunctionCallOutputContentItem`,
  and `ImageDetail`.
- Runtime request/response shape exports used by Python core:
  `CodeModeNestedToolCall`, default yield/token constants, `ExecuteRequest`,
  `ExecuteToPendingOutcome`, `RuntimeResponse`, `WaitOutcome`, `WaitRequest`,
  `WaitToPendingOutcome`, `WaitToPendingRequest`, and `CodeModeService`.
- `src/runtime/mod.rs` public model behavior for request coercion, Rust
  external tagged `RuntimeResponse` variants, wait live/missing provenance,
  execute-to-pending pending/completed outcomes, wait-to-pending
  live/missing outcomes, `WaitOutcome` to `RuntimeResponse` conversion, and
  nested tool-call field ownership.
- Dependency-light `src/service.rs` public facade behavior for service
  construction, monotonic cell id allocation, missing-cell wait provenance,
  callback result coercion, and terminal execute response forwarding to
  completed execute-to-pending outcomes.
- Dependency-light `src/runtime/value.rs` output helper behavior for text
  serialization, image URL/object/MCP block parsing, `mimeType`/`mime_type`
  fallback, accepted `auto`/`low`/`high`/`original` details, invalid detail
  fallback for MCP metadata, Rust-style invalid-shape errors, and
  stack-preferring error text.
- Dependency-light `src/runtime/timers.rs` timer helper behavior for
  set-timeout delay normalization, clear-timeout id no-op/error boundaries,
  fractional truncation, and `u64::MAX` clamping.
- Dependency-light `src/runtime/callbacks.rs` callback helper behavior for
  ASCII Rust `usize` tool callback data parsing, out-of-range errors, `tool-*`
  runtime id generation/saturation, JSON input normalization, content and
  notify/yield event shaping, and exit sentinel handling.
- Dependency-light `src/runtime/globals.rs` global registration behavior for
  removed host globals, fixed helper names, `tools` callback-data indexes, and
  ordered `ALL_TOOLS` metadata shape.
- Dependency-light `src/runtime/module_loader.rs` state/error behavior for
  main module origin, unsupported import errors, completion-state projection,
  exit-sentinel rejection handling, and stack-preferring error text.
- Marker classes for `CodeModeTurnHost` and `CodeModeTurnWorker` while the
  concrete V8 worker remains deferred.

Validation:

- `python -m pytest tests/test_codex_code_mode_lib_rs.py -q --tb=short`
  (`6 passed`)
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  (`49 passed`)
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  (`43 passed`)
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  (passed)
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  (`1 passed, 17 deselected`)
- `python -m py_compile pycodex\code_mode\__init__.py tests\test_codex_code_mode_lib_rs.py`
  (passed)
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  (`43 passed`) after adding the dependency-light `src/runtime/timers.rs`
  contract.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  (`49 passed`) after adding the dependency-light `src/runtime/timers.rs`
  contract.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  (`1 passed, 17 deselected`) after adding the dependency-light
  `src/runtime/timers.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  (`43 passed`) after adding the dependency-light `src/runtime/callbacks.rs`
  contract.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  (`49 passed`) after adding the dependency-light `src/runtime/callbacks.rs`
  contract.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  (`1 passed, 17 deselected`) after adding the dependency-light
  `src/runtime/callbacks.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  (`43 passed`) after adding the dependency-light `src/runtime/globals.rs`
  contract.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  (`49 passed`) after adding the dependency-light `src/runtime/globals.rs`
  contract.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  (`1 passed, 17 deselected`) after adding the dependency-light
  `src/runtime/globals.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  (`43 passed`) after adding the dependency-light
  `src/runtime/module_loader.rs` contract.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  (`49 passed`) after adding the dependency-light
  `src/runtime/module_loader.rs` contract.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  (`1 passed, 17 deselected`) after adding the dependency-light
  `src/runtime/module_loader.rs` contract.

Non-blocking runtime notes:

- `src/service.rs` and `src/runtime/*` concrete V8/Tokio runtime behavior
  remains an optional operational/runtime check for the dependency-light Python
  port.
