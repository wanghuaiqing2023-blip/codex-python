# codex-code-mode test alignment

Rust crate: `codex-code-mode`

Rust path: `codex/codex-rs/code-mode`

Python package: `pycodex/code_mode`

Status: `complete` for the dependency-light Python port.

## Module Mapping

- `src/lib.rs` -> `pycodex/code_mode/__init__.py`
- `src/description.rs` -> `pycodex/code_mode/__init__.py` via the canonical
  pure implementation in `pycodex.core.tools.code_mode`
- `src/response.rs` -> `pycodex/code_mode/__init__.py` via
  `pycodex.protocol` content item/image-detail models
- `src/runtime/mod.rs` public request/response/outcome model surface ->
  `pycodex/code_mode/__init__.py` via the dependency-light implementation in
  `pycodex.core.tools.code_mode`
- `src/service.rs` dependency-light public service facade ->
  `pycodex/code_mode/__init__.py` via `pycodex.core.tools.code_mode`
- `src/runtime/value.rs` dependency-light output text/image helper slice ->
  `pycodex.core.tools.code_mode`
- `src/runtime/timers.rs` dependency-light timer normalization slice ->
  `pycodex.core.tools.code_mode`
- `src/runtime/callbacks.rs` dependency-light callback event-shaping slice ->
  `pycodex.core.tools.code_mode`
- `src/runtime/globals.rs` dependency-light global registration projection
  slice -> `pycodex.core.tools.code_mode`
- `src/runtime/module_loader.rs` dependency-light module-loader state/error
  slice -> `pycodex.core.tools.code_mode`
- Non-model `src/runtime/*` execution internals ->
  non-blocking V8/Tokio runtime boundary with dependency-light
  callback/service shims in `pycodex.core.tools.code_mode`

## Rust Behavior Covered

`tests/test_codex_code_mode_lib_rs.py` covers:

- Rust crate-root public `pub use` facade and `PUBLIC_TOOL_NAME` /
  `WAIT_TOOL_NAME` constants from `src/lib.rs`.
- `parse_exec_source` success and error contracts from `src/description.rs`,
  including pragma field parsing, supported-key validation, missing-source
  errors, blank-source errors, and JavaScript safe-integer bounds.
- `build_exec_tool_description` namespace grouping and shared MCP type
  rendering from the Rust `description.rs` tests.
- `ImageDetail`, `DEFAULT_IMAGE_DETAIL`, and
  `FunctionCallOutputContentItem` response shapes from `src/response.rs`.
- Runtime public model contracts from `src/runtime/mod.rs`: `ExecuteRequest`,
  `WaitRequest`, `WaitToPendingRequest`, `RuntimeResponse`,
  `WaitOutcome`, `ExecuteToPendingOutcome`, `WaitToPendingOutcome`,
  `CodeModeNestedToolCall`, Rust external tagged enum input projection, and
  `impl From<WaitOutcome> for RuntimeResponse`-equivalent conversion.
- Dependency-light public service contracts from `src/service.rs`:
  `CodeModeService::new`, monotonic string `allocate_cell_id`,
  missing-cell `wait`/`wait_to_pending` provenance, callback result coercion
  for execute/wait/pending paths, and terminal execute response forwarding to
  completed execute-to-pending outcomes.
- Dependency-light value helper contracts from `src/runtime/value.rs`:
  output text serialization, image URL validation, non-MCP image object
  parsing, MCP image block parsing, `mimeType`/`mime_type` fallback, accepted
  `auto`/`low`/`high`/`original` image details, invalid MCP detail fallback,
  Rust-style invalid-shape error text, and stack-preferring error text.
- Dependency-light timer helper contracts from `src/runtime/timers.rs`:
  delay normalization for `schedule_timeout`, `clearTimeout` id no-op/error
  boundaries, fractional truncation, and `u64::MAX` clamping.
- Dependency-light callback helper contracts from `src/runtime/callbacks.rs`:
  ASCII `usize` tool callback data parsing, out-of-range tool callback errors,
  `tool-*` runtime id generation/saturation, JSON input normalization,
  text/image content event shaping, notify trim-empty rejection, yield event
  shaping, and the exit sentinel.
- Dependency-light global registration projection from `src/runtime/globals.rs`:
  removed host globals, fixed helper names, `tools` object callback-data
  indexes, and ordered `ALL_TOOLS` metadata shape.
- Dependency-light module-loader state/error contract from
  `src/runtime/module_loader.rs`: main module origin, unsupported static and
  dynamic import error text, completion-state projection, exit-sentinel
  rejection handling, and stack-preferring error text.

Related Rust-derived validation already exists in `tests/test_core_code_mode.py`
for the same pure helpers plus the dependency-light core service/runtime shim.

## Validation

- `python -m pytest tests/test_codex_code_mode_lib_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 with `49 passed`.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 with `43 passed`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\code_mode\__init__.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/timers.rs` contract
  with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/timers.rs` contract
  with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/timers.rs` contract
  with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21 after adding the `src/runtime/timers.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/callbacks.rs` contract
  with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/callbacks.rs` contract
  with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/callbacks.rs` contract
  with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21 after adding the `src/runtime/callbacks.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/globals.rs` contract
  with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/globals.rs` contract
  with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/globals.rs` contract
  with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21 after adding the `src/runtime/globals.rs` contract.
- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/module_loader.rs`
  contract with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/module_loader.rs`
  contract with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed on 2026-06-21 after adding the `src/runtime/module_loader.rs`
  contract with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21 after adding the `src/runtime/module_loader.rs`
  contract.

## Non-blocking runtime notes

- Concrete V8 isolate execution, module loader, timer callback scheduling,
  live runtime termination, Tokio session control, turn-worker host dispatch,
  and isolate-backed store/load semantics remain optional operational/runtime
  checks. They do not block crate completion because the dependency-light public
  facade, request/response/outcome models, and helper contracts have
  Rust-derived coverage and focused validation passes.
