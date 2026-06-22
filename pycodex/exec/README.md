# pycodex.exec

This package contains Python counterparts for Rust non-interactive exec
entrypoint behavior.

## Rust Counterpart

```text
Primary Rust crate: codex-exec
Primary Rust path: codex/codex-rs/exec
```

## Alignment Role

`pycodex.exec` should own exec-specific CLI orchestration, bootstrap planning,
backend selection, local HTTP/remote fallback integration, event processing,
and final output/exit behavior.

It should not own generic tool dispatch, protocol data models, or shell command
safety behavior. Those belong in `pycodex.core`, `pycodex.protocol`, and
`pycodex.shell_command`.

## Rust Module Areas

Typical Rust module counterparts include:

```text
codex/codex-rs/exec/src/cli.rs
codex/codex-rs/exec/src/main.rs
codex/codex-rs/exec/src/lib.rs
codex/codex-rs/exec/tests/
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
exec.cli_args
exec.bootstrap_plan
exec.backend_selection
exec.session_start_resume
exec.event_processing
exec.output_and_exit
```

## Test Source Policy

Prefer Rust exec integration tests under `codex/codex-rs/exec/tests/` before
Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-exec
# Rust module: tests/suite/prompt_stdin.rs
# Rust test: tests::example_test_name
# Contract: exec.cli_args
```

## Current Movement Status

`codex-exec/src/main.rs` is recorded as `complete_candidate` in
`MAIN_RS_STATUS.md`: Python mirrors the tested `TopCli` root config override
merge and resume/global flag parse behavior in `parse_exec_args`, and
`exec_main_dispatch_plan` mirrors the binary wrapper branch selection for
normal `codex-exec` argv versus argv0 named `codex-linux-sandbox`.

`codex-exec/src/lib.rs` is recorded as `complete_candidate` in
`LIB_RS_STATUS.md`: Python covers the export surface and Rust-tested helper
contracts across `__init__`, `run`, `session`, and `config_plan`. The remaining
`run_main` startup orchestration is mirrored as `ExecRunMainPlan`, including
processor selection, telemetry/logging defaults, runtime paths,
environment-manager source, config warnings, and in-process start args.

`codex-exec/src/cli.rs` is recorded as `complete_candidate` in
`CLI_RS_STATUS.md`: `pycodex.exec.cli` mirrors the Rust `codex exec`
command-line surface, including root/global flags, `resume`, `review`,
`--full-auto` compatibility, and subcommand global option behavior.

`codex-exec/src/event_processor.rs` is recorded as `complete_candidate` in
`EVENT_PROCESSOR_RS_STATUS.md`: `pycodex.exec.event_processor` mirrors the
parent output processor status/helper contract, while detailed human and JSONL
rendering remain separate sibling module boundaries.

`codex-exec/src/event_processor_with_jsonl_output.rs` is recorded as
`complete_candidate` in `JSONL_EVENT_PROCESSOR_RS_STATUS.md`:
`JsonEventProcessor` and exec event payload helpers mirror the Rust JSONL event
state machine, including item id reuse, `_meta` preservation, turn completion
state, and last-message output gating.

`codex-exec/src/event_processor_with_human_output.rs` is recorded as
`complete_candidate` in `HUMAN_EVENT_PROCESSOR_RS_STATUS.md`:
`HumanEventProcessor` mirrors the Rust human-readable output contract for
config summaries, item/notification rendering, reasoning visibility,
final-message routing, failed/interrupted cleanup, and blended token totals.

`codex-exec/src/exec_events.rs` is recorded as `complete_candidate` in
`EXEC_EVENTS_RS_STATUS.md`: `pycodex.exec.events` mirrors the Rust JSONL event
schema, including top-level event tags, item payloads, usage/error shapes,
status enums, and MCP result `_meta` serialization.

`pycodex.exec` should remain an entrypoint/orchestration package, not a
dumping ground for runtime or protocol behavior. Focused exec validation passed
on 2026-06-17 with `320 passed, 12 subtests passed`.
