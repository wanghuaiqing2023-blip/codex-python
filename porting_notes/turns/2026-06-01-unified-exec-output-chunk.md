# Unified Exec Output Chunk Processing

## Scope

- Continued the graph-guided core runtime path around unified exec streaming output.
- Focused on the Rust `process_chunk` behavior that bridges raw PTY bytes into retained transcript bytes and stdout delta events.

## Upstream Graph/Source Slice

- Graph-guided files used:
  - `codex-rs/core/src/unified_exec/async_watcher.rs`
  - `codex-rs/core/src/unified_exec/head_tail_buffer.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- Rust source confirmed:
  - `process_chunk` extends a pending byte buffer, repeatedly splits only valid UTF-8 prefixes, pushes every emitted prefix into `HeadTailBuffer`, and emits stdout deltas only while `MAX_EXEC_OUTPUT_DELTAS_PER_CALL` has not been reached.
  - Incomplete UTF-8 bytes remain pending until a later chunk completes them; invalid or non-progressing data eventually emits one byte so the stream cannot stall.
  - Transcript retention is independent of the delta emission cap, so final aggregated output still has retained bytes after delta events are capped.

## Python Changes

- `pycodex/core/unified_exec.py`
  - Added `ProcessOutputChunk` and `process_output_chunk()` to compose pending-buffer handling, transcript retention, and delta-cap decisions.
  - Kept the implementation standard-library only and layered on existing `split_valid_utf8_prefix()`, `HeadTailBuffer`, and `should_emit_exec_output_delta()`.
- `pycodex/core/__init__.py`
  - Exported the new unified exec chunk helper and result type.
- `tests/test_core_unified_exec.py`
  - Added focused parity coverage for transcript updates, UTF-8 boundary buffering, and delta-cap behavior.

## Validation

- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_exec_local_runtime`
  - 148 tests passed, 1 skipped.
- `python -m unittest discover -s tests -p "test_protocol_*.py"`
  - 300 tests passed.
- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 473 tests passed, 1 skipped.

## Follow-up Debt

- The Python helper is synchronous and local; a fuller async watcher integration can reuse it when the local unified exec event loop grows closer to Rust's background PTY watcher.
