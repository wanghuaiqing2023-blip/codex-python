# codex-exec src/exec_events.rs status

Status: complete_candidate

Rust crate: `codex-exec`
Rust module: `codex/codex-rs/exec/src/exec_events.rs`
Rust tests: none dedicated; behavior is exercised through JSONL processor tests.
Python module: `pycodex/exec/events.py`
Python tests: `tests/test_exec_event_processor.py`

## Behavior contract

Rust `exec_events.rs` owns the JSONL event schema emitted by `codex exec`:

- top-level tagged `ThreadEvent` variants: `thread.started`,
  `turn.started`, `turn.completed`, `turn.failed`, `item.started`,
  `item.updated`, `item.completed`, and `error`;
- `Usage` token fields and `ThreadErrorEvent`;
- canonical thread item payloads for agent messages, reasoning, command
  execution, file changes, MCP tool calls, collab tool calls, web search,
  todo lists, and non-fatal error items;
- snake_case status/tool/kind enums for command execution, MCP calls, collab
  calls, collab agent state, patch status, and patch change kind;
- MCP result serialization with `_meta` and `structured_content`.

## Python alignment

`pycodex.exec.events` mirrors the Rust tagged JSON shape with small
standard-library dataclasses and enum helpers. `ThreadEvent.to_mapping()`,
`ThreadEvent.to_json_line()`, `ExecThreadItem.to_mapping()`, `Usage`, and item
factory functions preserve the Rust external wire shape used by
`JsonEventProcessor`.

`tests/test_exec_event_processor.py` covers this module through:

- direct `ThreadEvent` serialization checks;
- command/MCP/collab/file/web-search/todo item mapping checks;
- `_meta` and `structured_content` preservation;
- `Usage` serialization and turn completion payloads;
- final-message extraction from agent-message and plan turn items;
- unsupported item filtering through JSONL processor integration.

## Known adaptations

Rust derives `Serialize`, `Deserialize`, and TypeScript schemas with serde and
`ts-rs`; Python exposes explicit `to_mapping()` and `to_json_line()` helpers
instead. Python also accepts a few app-server compatibility aliases where
neighboring Python protocol shims need them, but the emitted exec JSON shape
stays aligned with the Rust module contract.

## Evidence

- Rust source inspected: `codex/codex-rs/exec/src/exec_events.rs`.
- Python implementation inspected: `pycodex/exec/events.py`.
- Python tests inspected: `tests/test_exec_event_processor.py`.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
