## Stream-only response item history

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> `try_run_sampling_request` -> streamed `OutputItemDone` -> `handle_output_item_done` -> `record_completed_response_item`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs`: every completed streamed output item is handled at `OutputItemDone`; non-tool assistant/reasoning items are recorded into conversation history, and assistant text contributes to the turn's final `last_agent_message`.

### Python change

- `pycodex/core/turn_runtime.py` now records non-tool `output_item_done` stream items that are not already present in normalized sampler `response_items`.
- Stream-only assistant messages now appear in `UserTurnSamplingResult.response_items` and session history, while duplicate HTTP/SSE items with the same object/id/call id are skipped.
- Tool-call stream items continue to use the separate stream tool dispatch path added in the previous slice.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k "streamed_last_agent_message or stream_only_tool_call" -q`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k "streamed_last_agent_message or mailbox_preemption or emits_assistant_text_stream_deltas or routes_plan_mode_segments or stop_hook_continuation or stream_only_tool_call or follows_stream_completed_end_turn_false" -q`
- `uvx --with pytest pytest tests\test_core_stream_events_utils.py -k "handle_output_item_done or sampling_output_item_done or record_completed_response_item" -q`
- Smoke gate: `744 passed, 1 skipped, 98 subtests passed`.

### Notes

- This keeps the stream-only path closer to Rust `handle_output_item_done` without expanding MCP/plugin/cloud behavior.
