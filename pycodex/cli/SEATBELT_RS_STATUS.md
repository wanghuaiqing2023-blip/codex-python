# codex-cli src/debug_sandbox/seatbelt.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/debug_sandbox/seatbelt.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/debug_sandbox/seatbelt.rs` |
| Python module | `pycodex/cli/debug_sandbox.py` |
| Python exports | `pycodex/cli/__init__.py` Seatbelt denial helpers |
| Python tests | `tests/test_cli_debug_sandbox.py` |
| Status | `complete_candidate` |

`src/debug_sandbox/seatbelt.rs` owns the optional macOS Seatbelt denial logger:
starting the `log stream --style ndjson` process, attaching a PID tracker after
the sandbox child spawns, stopping both streams after the child exits, parsing
`eventMessage` strings, filtering denials to tracked PIDs, and de-duplicating
`(process name, capability)` pairs.

Python keeps native macOS process/log streaming behind the existing
debug-sandbox injectable boundary. The module-local parsing, PID filtering,
deduplication, lifecycle plan, and user-facing summary formatting are mirrored
without adding non-standard dependencies.

## Completed Behavior Areas

- `SandboxDenial` is represented by `DebugSandboxSeatbeltDenial`.
- Rust `parse_message` is mirrored by
  `parse_debug_sandbox_seatbelt_denial_message`.
- `DenialLogger::finish` log parsing, PID filtering, and `(name, capability)`
  de-duplication are represented by `collect_debug_sandbox_seatbelt_denials`.
- Denial logger lifecycle planning remains represented by
  `DebugSandboxDenialLoggerPlan` and `build_debug_sandbox_denial_logger_plan`.
- User-facing denial summary output remains represented by
  `format_debug_sandbox_denial_summary`.

## Rust Test Inventory

The Rust module has no `#[cfg(test)]` tests of its own. Its behavior is covered
by source-contract parity against:

- `DenialLogger::new`
- `DenialLogger::on_child_spawn`
- `DenialLogger::finish`
- `start_log_stream`
- `parse_message`

Python coverage entries:

- `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_seatbelt_parse_message_matches_rust_regex`
- `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_seatbelt_collect_denials_filters_pid_and_deduplicates_like_rust`
- Existing denial logger lifecycle/summary/finish tests in
  `tests/test_cli_debug_sandbox.py`.

## Remaining Gaps

- Python does not spawn the macOS `log stream` process directly in this module;
  that native runtime remains behind the injectable debug-sandbox boundary.
- The long-running PID tracking fidelity is tracked separately in
  `pycodex/cli/PID_TRACKER_RS_STATUS.md`.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
