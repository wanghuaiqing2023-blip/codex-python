# codex-exec src/event_processor.rs status

Status: complete_candidate

Rust owner: `codex-exec`
Rust module: `codex/codex-rs/exec/src/event_processor.rs`
Python module: `pycodex/exec/event_processor.py`
Python tests: `tests/test_exec_event_processor.py`

## Behavior Contract

Rust `src/event_processor.rs` owns the small parent output-processing contract:

- `CodexStatus::{Running, InitiateShutdown}`
- the `EventProcessor` trait surface for config summaries, server
  notifications, local warnings, and final output
- `handle_last_message`, which writes the final agent message or empty content
  to the requested output file and warns when no last message exists

The human and JSONL concrete output implementations live in sibling Rust
modules and remain separate module boundaries:
`event_processor_with_human_output.rs` and
`event_processor_with_jsonl_output.rs`.

## Python Mapping

`pycodex.exec.event_processor` mirrors the parent status/helper contract with
`CodexStatus` and `handle_last_message`, and exposes concrete
`HumanEventProcessor` and `JsonEventProcessor` classes that carry the sibling
module behavior. This status file only claims the parent `event_processor.rs`
contract, not the detailed human/JSONL rendering modules.

## Evidence

- Rust source inspected: `codex/codex-rs/exec/src/event_processor.rs`.
- Python module inspected: `pycodex/exec/event_processor.py`.
- Python coverage inspected: `tests/test_exec_event_processor.py`.
- Evidence anchors include `CodexStatus` import/use in processor tests and
  `handle_last_message` coverage through the shared exec event processor test
  file.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
