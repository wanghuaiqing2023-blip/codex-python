# codex-response-debug-context src/lib.rs status

Rust coordinate: `codex/codex-rs/response-debug-context/src/lib.rs`

Python coordinate: `pycodex/response_debug_context/__init__.py`

Status: `complete`

Behavior contract:

- expose `ResponseDebugContext`.
- extract response debug headers only from HTTP transport errors.
- decode `x-error-json` as base64 JSON and read `error.code` when present.
- project `ApiError::Transport` through transport extraction.
- return stable telemetry strings that omit HTTP/API response bodies.

Evidence:

- `tests/test_response_debug_context_lib_rs.py` ports the Rust tests and adds source-contract coverage for precedence, invalid auth error JSON, and fixed telemetry variants.
