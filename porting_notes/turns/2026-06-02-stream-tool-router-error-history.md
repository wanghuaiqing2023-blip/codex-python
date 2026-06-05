## Stream tool-router error history

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> streamed `OutputItemDone` -> `stream_events_utils::handle_output_item_done`.
- Rust behavior confirmed from `codex/codex-rs/core/src/stream_events_utils.rs`: when building a tool call returns a model-visible `FunctionCallError::RespondToModel`, the completed response item is recorded and a model-visible failure output is appended so the next sampling request can recover.

### Python change

- `pycodex/core/turn_runtime.py` now records stream-only tool-call items before returning a model-visible error output when `ToolRouter.build_tool_call` fails recoverably.
- This primarily affects stream-only malformed tool calls such as a bad `tool_search_call`; the next prompt now contains the original call plus the normalized failure output.
- Fatal tool-router errors remain fatal and are not converted into model-visible responses.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k "bad_tool_search_arguments or stream_only_tool_call" -q`
- `uvx --with pytest pytest tests\test_core_stream_events_utils.py -k "router_error or tool_call_error_handling" -q`
- `uvx --with pytest pytest tests\test_core_turn_runtime.py -k "bad_tool_search_arguments or stream_only_tool_call or streamed_last_agent_message or follows_stream_completed_end_turn_false or default_followups_continue_until_final_answer or maps_fatal_tool_error" -q`
- `uvx --with pytest pytest tests\test_core_stream_events_utils.py tests\test_core_tool_parallel.py tests\test_core_tool_router.py -q`
- Smoke gate: `744 passed, 1 skipped, 98 subtests passed`.

### Notes

- This keeps the fix on the core stream/tool/follow-up path and does not expand MCP/plugin behavior.
