# CLI provider usage-limit smoke

## Upstream slice

- Continued the core `exec -> HTTP provider -> terminal sampling error -> exec human/json output` slice.
- Public exec JSONL errors remain Rust-shaped `ThreadErrorEvent { message }` from `codex/codex-rs/exec/src/exec_events.rs`.
- Rust session handling records usage-limit rate-limit state and applies goal-runtime usage-limit events on terminal errors.

## Python slice

- Added real local HTTP CLI smokes for `HTTPError(429)` with a Responses-style `usage_limit_reached` payload and Codex rate-limit headers.
- Human output verifies the specific usage-limit message is surfaced instead of a generic retry-limit message.
- JSON output verifies the event sequence `thread.started`, `turn.started`, `error`, `turn.completed` and the user-facing usage-limit message.
- Lower-level validation continues to cover `UsageLimitReachedError` parsing, rate-limit snapshot update, and goal-runtime usage-limit accounting.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_usage_limit_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_usage_limit_prints_json_error_event tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_usage_limit_error tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_usage_limit_rate_limits_on_terminal_error`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_rate_limit_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_usage_limit_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_usage_limit_prints_json_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_connection_error_prints_human_error_event tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_timeout_prints_json_error_event`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Continue with interrupted-turn output and rollout behavior, then consolidate these core CLI smokes into a maintainable regression subset.
