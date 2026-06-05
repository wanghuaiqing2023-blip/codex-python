# API bridge unknown 400 body parity

## Upstream source

- `codex/codex-rs/codex-api/src/api_bridge.rs`
- `codex/codex-rs/codex-api/src/api_bridge_tests.rs`

Rust maps HTTP 400 transport errors specially:

- `error.code == "cyber_policy"` becomes `CodexErr::CyberPolicy`, using the error message or a fixed fallback.
- Invalid image bodies become `CodexErr::InvalidImageRequest`.
- Other/unknown 400 bodies become `CodexErr::InvalidRequest(body_text)`, preserving the full response body instead of extracting `error.message`.

## Python changes

- Updated `pycodex/core/http_transport.py` so unknown HTTP 400 responses keep the full body as the invalid-request message.
- Updated `tests/test_core_http_transport.py` to lock the full-body behavior.
- Updated CLI local HTTP smoke assertions in `tests/test_cli_parser.py` so human and JSON error events reflect the preserved body.

## Validation

- `python -m py_compile pycodex\core\http_transport.py tests\test_core_http_transport.py tests\test_cli_parser.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_http_transport.py -q`
  - 51 passed, 9 subtests passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_turn_runtime.py tests\test_core_client.py -q`
  - 201 passed, 1 pre-existing warning
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_parser.py -q -k "provider_http_error_prints_human_error_event or provider_http_error_prints_json_error_event"`
  - 2 passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 744 passed, 1 skipped, 98 subtests passed

## Follow-up

Continue comparing API bridge behavior for retry-limit metadata, usage-limit presentation, and identity/auth error details only where it affects the core `exec`/HTTP runtime path.
