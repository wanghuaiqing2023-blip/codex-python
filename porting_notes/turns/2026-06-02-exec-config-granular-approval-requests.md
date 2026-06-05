# Exec Config Granular Approval Requests

## Scope

Extended granular approval policy support from protocol/session parsing into
the `codex exec` request-construction path.

## Upstream references

- Graph nodes:
  - `codex-rs/exec/src/cli.rs`
  - `codex-rs/protocol/src/protocol.rs#AskForApproval`
  - `codex-rs/protocol/src/protocol.rs#GranularApprovalConfig`
  - `codex-rs/protocol/src/protocol.rs#ThreadSettingsAppliedEvent`
  - `codex-rs/protocol/src/protocol.rs#SessionConfiguredEvent`
- Rust source confirms that app-server request/event structs use
  `AskForApproval`, whose variants include `Granular(GranularApprovalConfig)`.

## Python changes

- `pycodex/exec/session.py`
  - `ExecSessionConfig`, `ThreadStartParams`, `ThreadResumeParams`, and
    `TurnStartParams` now accept `GranularApprovalConfig`.
  - Request serialization now emits `{"granular": {...}}` instead of dropping
    non-enum approval policies.
- `pycodex/exec/config_plan.py`
  - `ExecHarnessOverrides` and exec-session config mapping now preserve
    granular approval policies in JSON-shaped output.
- `pycodex/protocol/protocol.py`
  - `ThreadSettingsOverrides` and `ThreadSettingsSnapshot` now round-trip
    granular approval policies.

## Validation

- `python -m unittest tests.test_exec_session.ExecSessionRequestBuilderTests.test_exec_session_config_serializes_granular_approval_policy_to_thread_and_turn_requests tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_harness_overrides_serializes_granular_approval_policy tests.test_protocol_protocol.ProtocolProtocolTests.test_thread_settings_round_trips_granular_approval_policy`
  - 3 tests passed.
- `python -m unittest tests.test_protocol_protocol tests.test_exec_session tests.test_exec_config_plan tests.test_exec_event_processor`
  - 316 tests passed.
- `python -m py_compile pycodex\exec\session.py pycodex\exec\config_plan.py pycodex\protocol\protocol.py tests\test_exec_session.py tests\test_exec_config_plan.py tests\test_protocol_protocol.py`
  - Passed.
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
  - 94 tests passed.

## Known gaps

- CLI parsing still exposes only the standard approval-policy strings; granular
  values enter through app-server/config-shaped objects for now.
- Display summaries may still render granular policies generically.
