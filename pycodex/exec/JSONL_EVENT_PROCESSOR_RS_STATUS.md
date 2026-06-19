# codex-exec src/event_processor_with_jsonl_output.rs status

Status: complete_candidate

Rust crate: `codex-exec`
Rust module: `codex/codex-rs/exec/src/event_processor_with_jsonl_output.rs`
Rust tests: `codex/codex-rs/exec/src/event_processor_with_jsonl_output_tests.rs`
Python modules:

- `pycodex/exec/event_processor.py`
- `pycodex/exec/events.py`

Python tests: `tests/test_exec_event_processor.py`

## Behavior contract

Rust `EventProcessorWithJsonOutput` owns the JSONL-facing exec event state
machine:

- emits `thread.started`, warning/error item events, item started/completed,
  todo list updates, turn started/completed/failed, and ignored notification
  classes as JSON thread events;
- allocates stable synthetic `item_N` ids and reuses them across matching raw
  started/completed notifications;
- maps app-server thread items into exec JSON item details for agent messages,
  reasoning summaries, command execution, file changes, MCP calls, collab agent
  calls, and web search;
- preserves MCP tool result `_meta` in JSON output instead of serializing it as
  plain `meta`;
- records token usage updates for the eventual `turn.completed` event;
- tracks final message state and writes `--output-last-message` only after a
  completed turn requests final output.

## Python alignment

`JsonEventProcessor` in `pycodex.exec.event_processor` mirrors the Rust JSONL
processor state machine with standard-library data structures. `ThreadEvent`,
`ExecThreadItem`, MCP result serialization, and related event payload helpers in
`pycodex.exec.events` carry the Rust JSON surface shape.

The two Rust module tests are represented by focused Python tests:

- `failed_turn_does_not_overwrite_output_last_message_file` ->
  `test_failed_turn_does_not_overwrite_output_last_message_file`
- `mcp_tool_call_result_preserves_meta_in_jsonl_event` ->
  `test_mcp_tool_call_result_preserves_meta_as_underscore_meta`

Additional Python coverage in `tests/test_exec_event_processor.py` exercises the
same module-scoped contract for id reuse, unsupported item filtering, todo list
updates, token usage, final-message recovery, failed/interrupted turns, and
notification alias handling.

## Known adaptations

Rust prints JSONL directly to stdout and uses concrete app-server protocol
types. Python keeps collection methods testable by returning
`CollectedThreadEvents` and accepts either typed protocol objects or compatible
mapping payloads before emitting JSON lines.

Human-output behavior remains owned by
`event_processor_with_human_output.rs`; this status file only claims the JSONL
output module.

## Evidence

- Rust source inspected:
  `codex/codex-rs/exec/src/event_processor_with_jsonl_output.rs`.
- Rust tests inspected:
  `codex/codex-rs/exec/src/event_processor_with_jsonl_output_tests.rs`.
- Python implementation inspected:
  `pycodex/exec/event_processor.py`, `pycodex/exec/events.py`.
- Python tests inspected: `tests/test_exec_event_processor.py`.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
