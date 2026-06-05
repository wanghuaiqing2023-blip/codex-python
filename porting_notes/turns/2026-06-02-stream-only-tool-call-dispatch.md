## Stream-only tool-call dispatch

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> `try_run_sampling_request` -> streamed `OutputItemDone` -> `handle_output_item_done` -> `ToolCallRuntime::handle_tool_call` -> tool output recorded before the next sampling request.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs` and `codex/codex-rs/core/src/tools/parallel.rs`: completed streamed tool-call items start tool execution, record the tool call in conversation history, drain tool outputs, and keep the model loop running for a follow-up request.

### Python change

- `pycodex/core/turn_runtime.py` now handles tool calls that arrive only through sampler `stream_events` `output_item_done` entries.
- Stream tool calls are skipped when the same call id is already present in normalized `response_items`, so HTTP/SSE results that expose both views do not dispatch the same tool twice.
- Stream-only tool calls record the model tool-call item into session history and then append the tool output for the next model request.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k stream_only_tool_call -q`
- `uvx --with pytest pytest tests\test_core_stream_events_utils.py tests\test_core_tool_parallel.py tests\test_core_tool_router.py -q`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k "stream_only_tool_call or default_followups_continue_until_final_answer or dispatches_parallel_tool_calls_concurrently or follows_stream_completed_end_turn_false or applies_stream_server_model" -q`
- `uvx --with pytest pytest tests\test_core_session_runtime.py tests\test_core_turn_runtime.py -k "http_sampling_uses_pending_input_followup or tool_dispatch_increments_active_turn_tool_calls or stream_only_tool_call or bad_tool_search_arguments or maps_fatal_tool_error" -q`
- Smoke gate: `744 passed, 1 skipped, 98 subtests passed`.

### Notes

- A full `tests\test_core_turn_runtime.py -q` run was interrupted after exceeding a reasonable wait with no failure output; the focused turn-runtime slices and smoke gate completed successfully.
