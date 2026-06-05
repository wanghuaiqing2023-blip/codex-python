# 2026-06-02 agent message memory citation finalization

## Upstream slice

- Used the upstream graph to follow the core stream output path through:
  - `codex-rs/core/src/stream_events_utils.rs#handle_output_item_done`
  - `codex-rs/core/src/stream_events_utils.rs#finalize_non_tool_response_item`
- Confirmed from Rust source that finalized assistant messages call
  `strip_hidden_assistant_markup_and_parse_memory_citation`.
- Rust preserves an existing `AgentMessageItem.memory_citation` and only fills it from hidden markup when absent.

## Python changes

- Added a text-level memory citation parser helper in `pycodex.core.stream_events_utils`.
- Updated assistant-message normalization so finalized `TurnItem.AgentMessage` carries parsed memory citations from hidden `<oai-mem-citation>` markup.
- Preserved existing `AgentMessageItem.memory_citation` values from contributors.

## Validation

- `python -m unittest tests.test_core_stream_events_utils`
- `python -m unittest tests.test_core_turn_runtime`

