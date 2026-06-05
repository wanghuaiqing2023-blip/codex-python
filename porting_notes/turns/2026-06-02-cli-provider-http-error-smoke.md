# CLI provider HTTP error smoke

## Upstream slice

- Used the upstream graph to stay on the core `exec -> model client -> error event -> exec JSONL` path.
- Confirmed public exec JSONL errors from `codex/codex-rs/exec/src/exec_events.rs` expose a `ThreadErrorEvent { message }`.

## Python slice

- `pycodex/core/http_transport.py` now maps HTTP 400 invalid-request payloads to the parsed `error.message` when present, falling back to the raw body only when no message is available.
- Added real CLI local HTTP smokes that patch `pycodex.core.http_transport.urlopen` to raise an actual `HTTPError(400)` with a Responses-style JSON body.
- Human output now surfaces `ERROR: bad schema` instead of the raw JSON body.
- JSON output emits the Rust-shaped sequence `thread.started`, `turn.started`, `error`, `turn.completed` with `message: bad schema`.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_json_error_event tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_400_to_invalid_request tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_reports_http_error_body`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_json_turn_failed tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_json_error_event`
- `python -m py_compile pycodex\core\http_transport.py tests\test_cli_parser.py`

## Follow-up

- Continue with retry/rate-limit and connection-failure CLI smokes so common provider failures are visible and stable before widening into non-core extension behavior.
