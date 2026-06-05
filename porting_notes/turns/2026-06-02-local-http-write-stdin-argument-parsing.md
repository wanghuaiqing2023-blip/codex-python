# Local HTTP write_stdin argument parsing

## Upstream reference

- `codex/codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`
- `codex/codex-rs/core/src/tools/handlers/mod.rs`

Rust handles `write_stdin` as a function tool and parses its arguments through
`parse_arguments::<WriteStdinArgs>`. `session_id` is required as an `i32`;
`chars` defaults to an empty string but must be a string when present;
`yield_time_ms` and `max_output_tokens` must parse as unsigned integer fields.
Invalid typed arguments are returned to the model as
`failed to parse function arguments: ...` instead of being executed.

## Python changes

- Added `write_stdin` typed argument validation in
  `pycodex/exec/local_runtime.py` before the local session manager is called.
- Preserved existing successful paths for valid `write_stdin` calls, unknown
  sessions, default yield time, and session polling.
- Added regression coverage for missing `session_id` and non-string `chars` so
  malformed model calls become model-visible parse errors.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_missing_session_id_returns_parse_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_rejects_non_string_chars tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_tool_call_reports_unavailable_session_runtime tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_uses_default_yield_time`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
