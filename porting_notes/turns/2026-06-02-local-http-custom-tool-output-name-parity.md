# local HTTP custom tool output name parity

## Upstream graph and source slice

- Graph path: `exec -> model response items -> tool dispatch -> tool response input items`
- Source: `codex/codex-rs/core/src/tools/parallel.rs`
- Source: `codex/codex-rs/core/src/tools/context.rs`
- Source: `codex/codex-rs/core/src/stream_events_utils.rs`

Rust converts both normal custom tool results and custom tool failure results to
`ResponseInputItem::CustomToolCallOutput` with `name: None`. The subsequent
`response_input_to_response_item` helper preserves that field exactly when the
tool output is fed back into the next model request.

## Python changes

- `_local_http_unsupported_tool_call_output` no longer emits `name` for
  `custom_tool_call_output` mappings.
- `_local_http_incompatible_tool_payload_output` no longer emits `name` for
  `custom_tool_call_output` mappings.
- Added coverage that raw local HTTP outputs, `ResponseItem` conversion, and
  follow-up request bodies omit the custom output name while preserving
  `success: false`.

## Validation

- `$env:PYTHONPATH='.'; uvx pytest tests/test_exec_local_runtime.py -k "unknown_custom_tool or custom_exec_command_payload_is_not_executed or unknown_tool_error or apply_patch_followup_request_omits_custom_output_name"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_exec_local_runtime.py`
