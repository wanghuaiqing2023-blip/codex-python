# codex-response-debug-context test alignment

Rust crate: `codex-response-debug-context`

Python package: `pycodex/response_debug_context`

Status: `complete`

Certified modules:

- `codex/codex-rs/response-debug-context/src/lib.rs` -> `pycodex/response_debug_context/__init__.py`

Rust-test/source-contract coverage:

- `extract_response_debug_context_decodes_identity_headers`.
- `telemetry_error_messages_omit_http_bodies`.
- `telemetry_error_messages_preserve_non_http_details`.
- `x-request-id` takes precedence over `x-oai-request-id`.
- non-HTTP transport errors and non-transport API errors return an empty debug context.
- fixed API/transport error variants map to stable body-free telemetry strings.

Validation:

- `python -m pytest tests/test_response_debug_context_lib_rs.py -q`
- `python -m py_compile pycodex/response_debug_context/__init__.py tests/test_response_debug_context_lib_rs.py`
