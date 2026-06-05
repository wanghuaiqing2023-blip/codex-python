# 2026-06-02 local HTTP CLI retry smoke

## Scope

Added CLI-level protection for the core sampling retry path:

`exec -> prepared model request -> retryable Responses stream error -> retry decision -> retry request -> final assistant answer`.

This is a mainline runtime slice. It does not implement websocket fallback, remote compaction, or peripheral transport behavior.

## Upstream anchors

- `codex/codex-rs/core/src/responses_retry.rs`
- `codex/codex-rs/core/src/session/turn.rs`

Rust retries retryable stream errors on sampling requests, optionally reporting reconnect state and sleeping according to the error-provided delay or exponential backoff.

## Python changes

- Added `TopLevelCliParserTests.test_main_exec_local_http_retryable_stream_error_retries_and_succeeds`.
- Added that test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex exec` through the local HTTP CLI path. The fake provider first returns a Responses payload error with `code: rate_limit_exceeded`, which Python maps to a retryable `CodexErr.stream`, then returns a normal assistant message on the retry. Sleep is patched to a no-op and the provider retry cap is fixed to one retry.

## Validation

- `python -m py_compile tests\test_cli_parser.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_retryable_stream_error_retries_and_succeeds`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 27 tests; the combined local HTTP core smoke suite now covers 41 tests.
