# codex-code-mode runtime/callbacks.rs status

Rust crate: `codex-code-mode`

Rust module: `codex/codex-rs/code-mode/src/runtime/callbacks.rs`

Python module: `pycodex.core.tools.code_mode`

Status: `complete` for the dependency-light callback event-shaping contract.

## Behavior Contract

- `tool_callback(...)` parses callback data as Rust `usize`, accepting only
  ASCII decimal digits, and rejects invalid callback data with
  `invalid tool callback data`.
- Tool callback indexes outside the enabled-tool list report
  `tool callback data is out of range`.
- Tool callback runtime ids use the Rust `tool-{next_tool_call_id}` shape and
  saturate at `u64::MAX` when advanced.
- Tool callback input is JSON-round-tripped; serialization failures report the
  JavaScript-value serialization error boundary.
- `text_callback(...)` emits `RuntimeEvent::ContentItem(InputText { ... })`
  through the shared `runtime/value.rs` text serializer.
- `image_callback(...)` emits image content items through the shared
  `runtime/value.rs` image normalization helper and preserves the optional
  detail override contract.
- `notify_callback(...)` serializes text, rejects trim-empty text with
  `notify expects non-empty text`, and emits the runtime tool-call id.
- `yield_control_callback(...)` emits `RuntimeEvent::YieldRequested`.
- `exit_callback(...)` exposes the shared exit sentinel used to distinguish
  intentional exits from runtime errors.

Concrete V8 promise resolver creation, callback registration on the global
object, pending promise resolution/rejection, V8 exception throwing, and live
event-channel delivery remain non-blocking operational/runtime checks.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/callbacks.rs`
- Rust anchors:
  - `tool_callback`
  - `text_callback`
  - `image_callback`
  - `notify_callback`
  - `yield_control_callback`
  - `exit_callback`
- Python implementation:
  - `runtime_tool_index_from_callback_data(...)`
  - `runtime_tool_call_id(...)`
  - `next_runtime_tool_call_sequence(...)`
  - `normalize_runtime_tool_input(...)`
  - `build_runtime_tool_call_event(...)`
  - `build_runtime_text_event(...)`
  - `build_runtime_image_event(...)`
  - `build_runtime_notify_event(...)`
  - `build_runtime_yield_event(...)`
  - `runtime_exit_exception(...)`
- Python tests:
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_runtime_tool_callback_helpers_build_nested_tool_events`
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_text_and_image_callback_helpers_emit_content_events`
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_notify_and_exit_helpers_match_runtime_callbacks`

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

None for the dependency-light callback event-shaping contract. Concrete V8
callback registration, promise resolver state, thrown TypeError objects,
channel delivery, and live callback invocation remain optional
operational/runtime checks for the broader crate.
