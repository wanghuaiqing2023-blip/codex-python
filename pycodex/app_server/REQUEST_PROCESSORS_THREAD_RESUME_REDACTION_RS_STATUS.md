# request_processors/thread_resume_redaction.rs Status

Rust module: `codex-app-server/src/request_processors/thread_resume_redaction.rs`

Python module: `pycodex/app_server/request_processors_thread_resume_redaction.py`

Status: `complete`

## Covered Contract

- Remote ChatGPT client-name matching mirrors Rust's exact Android/iOS remote
  client allowlist.
- `redact_thread_resume_payloads` preserves non-sensitive thread items,
  redacts MCP tool-call arguments to `[redacted]`, replaces successful MCP
  results with a text-only redacted result, redacts MCP error messages, and
  removes image-generation items from thread/resume responses.
- Python returns a redacted `Thread` copy because protocol `Thread`/`Turn`
  values are frozen dataclasses; this preserves Rust's response-only redaction
  contract without mutating persisted history inputs.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/thread_resume_redaction.rs`
- Rust local tests:
  - `redacts_mcp_success_result_and_removes_image_generation`
  - `redacts_mcp_error_message`
- Python parity tests in
  `tests/test_app_server_request_processors_thread_resume_redaction_rs.py`.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_resume_redaction_rs.py -q`
  -> 3 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_resume_redaction.py tests/test_app_server_request_processors_thread_resume_redaction_rs.py`.

## Known Gaps

- Integration into `thread_processor.rs` and running-thread resume lifecycle is
  owned by neighboring request-processor modules.
