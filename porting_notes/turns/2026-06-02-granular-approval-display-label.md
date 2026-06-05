# Granular Approval Display Label

## Scope

Aligned user-facing approval policy labels for granular approval policies across
the exec summary and local HTTP tool-output paths.

## Upstream references

- Graph/source slice:
  - `codex-rs/protocol/src/protocol.rs#AskForApproval`
  - `codex-rs/protocol/src/protocol.rs#GranularApprovalConfig`
  - `codex-rs/exec/src/event_processor_with_human_output.rs#config_summary_entries`
- Rust behavior confirmed from source:
  - Human config summary prints `config.permissions.approval_policy.value().to_string()`.
  - `AskForApproval` uses kebab-case display labels; the granular variant
    displays as `granular`.

## Python changes

- `pycodex/protocol/protocol.py`
  - Added `approval_policy_display_value()` for Rust-style human labels.
  - Exported the helper from `pycodex.protocol`.
- `pycodex/exec/event_processor.py`
  - Config summary now renders granular approval as `granular`.
- `pycodex/exec/local_runtime.py`
  - Local HTTP config summaries and approval/forbidden tool outputs now render
    granular approval as `granular` instead of a Python dataclass string.
- `pycodex/core/apply_patch.py`
  - Direct apply_patch policy rejection output uses the same display helper.

## Validation

- `python -m unittest tests.test_protocol_protocol.ProtocolProtocolTests.test_approval_policy_display_value_matches_rust_labels tests.test_core_apply_patch.CoreApplyPatchTests.test_apply_patch_handler_forbids_read_only_policy_when_granular_disallows_sandbox_approval tests.test_exec_event_processor.ExecEventProcessorTests.test_config_summary_entries_render_granular_approval_like_rust_display tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_approval_outputs_render_granular_label_like_rust_display tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_config_summary_renders_granular_approval_label`
  - 5 tests passed.
- `python -m unittest tests.test_protocol_protocol tests.test_core_apply_patch tests.test_exec_event_processor tests.test_exec_local_runtime`
  - 372 tests passed.
- `python -m py_compile pycodex\protocol\protocol.py pycodex\protocol\__init__.py pycodex\core\apply_patch.py pycodex\exec\event_processor.py pycodex\exec\local_runtime.py tests\test_protocol_protocol.py tests\test_core_apply_patch.py tests\test_exec_event_processor.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
  - 94 tests passed.

## Known gaps

- Full CLI parsing still exposes only the non-granular approval strings.
- Some peripheral UI/config surfaces outside the active core exec path may still
  need granular-specific rendering later.
