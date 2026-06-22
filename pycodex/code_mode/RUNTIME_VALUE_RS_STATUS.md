# codex-code-mode src/runtime/value.rs status

Rust coordinate: `codex/codex-rs/code-mode/src/runtime/value.rs`

Python coordinate: `pycodex.core.tools.code_mode`

Status: `complete` for dependency-light output text/image value helpers.

## Behavior Contract

- `serialize_output_text` projects null, booleans, numbers, strings, and JSON
  objects into Rust-compatible code-mode output text.
- `normalize_output_image` accepts non-empty `http://`, `https://`, and
  `data:` URLs.
- Non-MCP image objects accept `image_url` plus optional string `detail`.
- MCP image blocks accept `type: "image"`, base64 `data`, `mimeType` or
  `mime_type`, existing `data:` URLs, and `_meta["codex/imageDetail"]`.
- Image detail values match Rust: `auto`, `low`, `high`, and `original` are
  accepted; invalid values raise the Rust-style error text.
- Invalid shapes preserve Rust source error strings for unsupported URL
  schemes, non-string detail, non-image MCP blocks, and missing MCP image data.
- `value_to_error_text` prefers object `stack` text and otherwise uses
  serialized output text.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/value.rs`
- Rust usage/tests:
  - `src/service.rs` tests for output helpers and image helper acceptance /
    rejection cases.
  - `normalize_output_image` source contract for detail handling and MCP image
    block parsing.
- Python tests: `tests/test_core_code_mode.py`

## Validation

- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed on 2026-06-21 with `49 passed`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed on 2026-06-21.

## Non-blocking runtime notes

This status covers the dependency-light value conversion/output helper
contract. It does not claim concrete V8 value serialization, V8 exception
objects, isolate execution, timers, module loading, or Tokio session control;
those remain optional operational/runtime checks.
