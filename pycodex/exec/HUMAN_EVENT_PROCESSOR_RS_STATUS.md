# codex-exec src/event_processor_with_human_output.rs status

Status: complete_candidate

Rust crate: `codex-exec`
Rust module: `codex/codex-rs/exec/src/event_processor_with_human_output.rs`
Rust tests: `codex/codex-rs/exec/src/event_processor_with_human_output_tests.rs`
Python module: `pycodex/exec/event_processor.py`
Python tests: `tests/test_exec_event_processor.py`

## Behavior contract

Rust `EventProcessorWithHumanOutput` owns the human-readable exec output
surface:

- config summary ordering and sandbox/approval/model/session display;
- warning, error, deprecation, hook, model-reroute, diff, plan, item-started,
  and item-completed stderr rendering;
- reasoning visibility rules for summary vs raw reasoning text;
- command/file/MCP/web-search/context-compaction human item lines;
- final message tracking from streamed agent messages and completed turn items,
  including plan fallback;
- failed/interrupted turn cleanup of stale final-message state;
- final output routing to last-message files, stdout, or tty stderr;
- token total display using the Rust blended-token formula.

## Python alignment

`HumanEventProcessor` in `pycodex.exec.event_processor` mirrors the Rust human
processor with plain-text output helpers rather than ANSI styling. The same file
also carries the Rust helper contracts for `config_summary_entries`,
`config_summary_lines`, `reasoning_text_from_notification_item`,
`final_message_from_notification_items`, `should_print_final_message_to_stdout`,
`should_print_final_message_to_tty`, and `blended_total`.

The Rust module tests are represented by focused Python coverage in
`tests/test_exec_event_processor.py`, including:

- final stdout/tty decision helpers;
- summary/raw reasoning selection and hidden reasoning behavior;
- disabled/external/workspace-write/read-only sandbox summaries through
  `summarize_permission_profile`;
- config summary entry ordering and runtime workspace root display;
- latest agent-message and plan fallback final-message selection;
- completed/failed/interrupted turn state transitions;
- human notification dispatch and item started/completed line rendering;
- final message stdout rendering when stdout is not a terminal.

## Known adaptations

Rust uses `owo_colors` styles and writes directly to process stdout/stderr.
Python keeps deterministic plain-text helpers and accepts either typed protocol
objects or app-server-like mappings so the behavior can be tested without an
ANSI terminal or full Rust protocol runtime.

JSONL output behavior remains owned by
`event_processor_with_jsonl_output.rs`; this status file only claims the human
output module.

## Evidence

- Rust source inspected:
  `codex/codex-rs/exec/src/event_processor_with_human_output.rs`.
- Rust tests inspected:
  `codex/codex-rs/exec/src/event_processor_with_human_output_tests.rs`.
- Python implementation inspected: `pycodex/exec/event_processor.py`.
- Python tests inspected: `tests/test_exec_event_processor.py`.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
