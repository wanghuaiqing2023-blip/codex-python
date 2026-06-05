# Exec file-change declined JSON status

## Upstream slice

- Graph-guided target: `codex-rs/exec/src/event_processor_with_jsonl_output.rs#map_item_with_id`.
- Rust source confirmed:
  - `ThreadItem::FileChange` maps `PatchApplyStatus::Declined` to exec JSON `PatchApplyStatus::Failed`.
  - Human output in `event_processor_with_human_output.rs` still renders declined patches as `declined`.

## Python port

- Restored `pycodex.exec.event_processor._patch_status_for_exec_json` so `declined` maps to `failed`.
- Added `file_change` to the raw app-server notification boundary so `item/completed` notifications use the JSONL-specific mapping before typed `TurnItem` normalization.
- Kept typed/timeline `TurnItem::FileChange` normalization unchanged so local runtime timeline items still report `declined`.
- Kept human rendering unchanged so `patch: declined` remains visible in non-JSON output.

## Validation

- `python -m py_compile pycodex\exec\event_processor.py pycodex\exec\events.py tests\test_exec_event_processor.py`
- `python -m unittest tests.test_exec_event_processor.ExecEventProcessorTests.test_exec_json_file_change_mappings_preserve_unknown_values tests.test_exec_event_processor.ExecEventProcessorTests.test_json_processor_file_change_declined_maps_to_failed_status_like_upstream_jsonl tests.test_exec_event_processor.ExecEventProcessorTests.test_human_item_completed_lines_uses_turn_item_app_server_mapping`
- `python -m unittest tests.test_exec_event_processor`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_exec_core_runtime tests.test_exec_local_http_runtime_smoke_suite`
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_session tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_exec_core_runtime`

## Known gaps

- This covers exec event-output parity only.
- Patch application behavior itself is handled by the core/apply-patch runtime and remains tested separately.
