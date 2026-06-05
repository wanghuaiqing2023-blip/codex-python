# SessionConfigured granular approval policy

## Upstream slice

- Followed the upstream graph around `SessionConfiguredEvent` and `AskForApproval::Granular`.
- Confirmed behavior in:
  - `codex-rs/protocol/src/protocol.rs#AskForApproval`
  - `codex-rs/protocol/src/protocol.rs#SessionConfiguredEvent`
  - `codex-rs/core/src/session/session.rs` where `SessionConfiguredEvent` is emitted with `session_configuration.approval_policy.value()`

## Rust behavior matched

- `SessionConfiguredEvent.approval_policy` uses the same `AskForApproval` enum as turn context.
- The granular approval variant serializes as a structured value rather than a plain string.
- Thread start/resume responses that carry granular approval should construct a usable `SessionConfiguredEvent`.

## Python changes

- `SessionConfiguredEvent` now accepts `AskForApproval | GranularApprovalConfig`.
- Session configured JSON now uses the shared approval-policy parser/serializer, preserving existing string policies and adding `{"granular": {...}}`.
- Remote exec thread start/resume response parsing now accepts granular approval policy objects.
- Added protocol and exec-session focused coverage for granular session configured round-trips.

## Validation

- `python -m unittest tests.test_protocol_protocol.ProtocolProtocolTests.test_session_configured_event_round_trips_granular_approval_policy tests.test_exec_session.ExecSessionRequestBuilderTests.test_session_configured_from_thread_start_response_accepts_granular_approval_policy`
- `python -m unittest tests.test_protocol_protocol tests.test_exec_session tests.test_exec_event_processor`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
- `python -m py_compile pycodex\protocol\protocol.py pycodex\exec\session.py tests\test_protocol_protocol.py tests\test_exec_session.py`

## Known gaps

- Some display helpers still render structured granular approval with generic JSON/dict formatting. That is acceptable for this contract slice but can be polished later if it becomes user-facing in normal CLI output.
- Other protocol structs with `approval_policy` fields may still need granular support if they become active on the common core runtime path.
