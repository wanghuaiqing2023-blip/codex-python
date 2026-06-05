# CLI provider retry, connection, and timeout smokes

## Upstream slice

- Continued on the graph-selected core path: `exec -> model request -> provider/transport error -> turn runtime terminal error -> exec human/json output`.
- Public JSONL behavior follows `codex/codex-rs/exec/src/exec_events.rs`: terminal stream errors surface as `ThreadErrorEvent { message }`.

## Python slice

- Added real local HTTP CLI smokes for common provider failures:
  - HTTP 429 rate-limit as a JSON error event.
  - `URLError` connection failure as a human `ERROR:` event.
  - `TimeoutError` as a JSON error event.
- The CLI smokes patch stream retry limits to zero so they verify final user-facing output without waiting for the retry/backoff path. Retry behavior remains covered by lower-level transport/runtime tests.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_rate_limit_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_connection_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_timeout_prints_json_error_event tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_429_to_retry_limit tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_url_error_to_connection_failed tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_timeouts_to_request_timeout`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_http_error_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_rate_limit_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_connection_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_timeout_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_json_error_event`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Continue with usage-limit-specific CLI coverage and interrupted-turn behavior before widening beyond core local HTTP exec.
