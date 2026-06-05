# Exec notification details aliases

## Upstream slice

- Graph-guided target: `codex-rs/exec/src/event_processor_with_jsonl_output.rs` and `event_processor_with_human_output.rs`.
- Rust source confirmed:
  - Config warnings render `summary` plus optional `details`.
  - Deprecation notices render `summary` plus optional `details`.
  - Error-like notifications preserve extra detail text in the user-visible output.

## Python port

- Added `_notification_details` in `pycodex.exec.event_processor`.
- `configWarning` / `warning` and `deprecationNotice` now accept:
  - `details`
  - `additionalDetails`
  - `additional_details`
- Updated both JSON event collection and human notification rendering to use the same helper.

## Validation

- `python -m py_compile pycodex\exec\event_processor.py tests\test_exec_event_processor.py`
- `python -m unittest tests.test_exec_event_processor.ExecEventProcessorTests.test_json_processor_config_warning_uses_additional_details_alias tests.test_exec_event_processor.ExecEventProcessorTests.test_human_deprecation_notice_uses_additional_details_alias tests.test_exec_event_processor.ExecEventProcessorTests.test_json_processor_dispatches_app_server_notifications tests.test_exec_event_processor.ExecEventProcessorTests.test_human_processor_dispatches_notifications_and_failed_turns`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_exec_core_runtime`

## Known gaps

- This is an exec event-output compatibility slice only.
- Broader app-server notification coverage remains incremental and should stay tied to the common `exec` path.
