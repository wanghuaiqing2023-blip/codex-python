# Local HTTP apply_patch declined status

## Source slice

- Checked the Rust tool event path in:
  - `codex-rs/core/src/tools/events.rs`
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
- Rust emits `PatchApplyStatus::Declined` for rejected patch application, distinct from execution failure.

## Python changes

- Local HTTP apply_patch approval-required outputs now produce final file-change status `declined` instead of `failed`.
- `pycodex.exec.events.PatchApplyStatus` now includes `DECLINED`.
- Exec JSON file-change status normalization now preserves `declined` instead of folding it into `failed`.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py pycodex\exec\events.py pycodex\exec\event_processor.py tests\test_exec_local_runtime.py tests\test_exec_event_processor.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure tests.test_exec_event_processor.ExecEventProcessorTests.test_exec_json_file_change_mappings_preserve_unknown_values tests.test_exec_event_processor.ExecEventProcessorTests.test_json_processor_file_change_declined_status_matches_upstream_enum`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor`
- `python -m unittest tests.test_core_tool_events tests.test_protocol_items tests.test_core_apply_patch tests.test_exec_config_plan`
