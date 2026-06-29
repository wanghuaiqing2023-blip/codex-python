# codex-exec test alignment

This ledger records Rust module-scoped behavior contracts for `codex-exec`
as they are reconciled against Python modules and focused tests.

## complete_candidate

### `src/lib.rs` orchestration and export surface

- Rust owner: `codex-exec`
- Rust module: `codex/codex-rs/exec/src/lib.rs`
- Rust tests: `codex/codex-rs/exec/src/lib_tests.rs`
- Python modules:
  `pycodex/exec/__init__.py`, `pycodex/exec/run.py`,
  `pycodex/exec/session.py`, `pycodex/exec/config_plan.py`
- Python tests:
  `tests/test_exec_run.py`, `tests/test_exec_session.py`,
  `tests/test_exec_config_plan.py`
- Python status file: `pycodex/exec/LIB_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors the public export surface and Rust-tested helper
  contracts for prompt decoding, review requests, thread/session request
  construction, resume lookup, backfill helpers, MCP elicitation cancel
  responses, and session-configured mapping. Python `ExecRunMainPlan` mirrors
  Rust `run_main` startup decisions for processor selection, telemetry/logging
  defaults, runtime paths, environment-manager source, config warnings, and
  in-process app-server start args. The exec bootstrap/session projection also
  carries effective `tui.keymap` values from config.toml and root `-c`
  overrides into `ExecSessionConfig.tui_keymap`, matching the path consumed by
  the TUI runtime for keymap dispatch.
- Focused validation: `python -m pytest tests/test_exec_cli.py
  tests/test_exec_run.py tests/test_exec_session.py
  tests/test_exec_config_plan.py tests/test_exec_event_processor.py -q` ->
  `320 passed, 12 subtests passed`.

### `src/main.rs` binary wrapper

- Rust owner: `codex-exec`
- Rust module: `codex/codex-rs/exec/src/main.rs`
- Rust tests: `codex/codex-rs/exec/src/main_tests.rs`
- Python module: `pycodex/exec/cli.py`
- Python tests: `tests/test_exec_cli.py`
- Python status file: `pycodex/exec/MAIN_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python `parse_exec_args(..., root_config_overrides=...)` mirrors
  the tested `TopCli` behavior that prepends root config overrides before inner
  exec overrides, and it preserves resume prompt parsing after subcommand global
  flags. Python `exec_main_dispatch_plan(...)` mirrors the binary wrapper branch
  selection for normal `codex-exec` argv versus argv0 named
  `codex-linux-sandbox`.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.

### `src/exec_events.rs` JSONL schema

- Rust owner: `codex-exec`
- Rust module: `codex/codex-rs/exec/src/exec_events.rs`
- Rust tests: no dedicated `exec_events` test module; behavior is covered
  through JSONL processor tests.
- Python module: `pycodex/exec/events.py`
- Python tests: `tests/test_exec_event_processor.py`
- Python status file: `pycodex/exec/EXEC_EVENTS_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors the Rust `ThreadEvent`, `Usage`,
  `ThreadErrorEvent`, thread item payload, status enum, MCP result `_meta`, and
  JSON serialization shape used by `codex exec --json`.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.

### `src/event_processor_with_human_output.rs` human processor

- Rust owner: `codex-exec`
- Rust module:
  `codex/codex-rs/exec/src/event_processor_with_human_output.rs`
- Rust tests:
  `codex/codex-rs/exec/src/event_processor_with_human_output_tests.rs`
- Python module: `pycodex/exec/event_processor.py`
- Python tests: `tests/test_exec_event_processor.py`
- Python status file: `pycodex/exec/HUMAN_EVENT_PROCESSOR_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust `EventProcessorWithHumanOutput` config
  summary, human notification/item line rendering, reasoning visibility,
  final-message recovery and routing decisions, failed/interrupted cleanup, and
  blended token total helpers. ANSI styling is intentionally adapted to stable
  plain text.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.

### `src/event_processor_with_jsonl_output.rs` JSONL processor

- Rust owner: `codex-exec`
- Rust module:
  `codex/codex-rs/exec/src/event_processor_with_jsonl_output.rs`
- Rust tests:
  `codex/codex-rs/exec/src/event_processor_with_jsonl_output_tests.rs`
- Python modules: `pycodex/exec/event_processor.py`, `pycodex/exec/events.py`
- Python tests: `tests/test_exec_event_processor.py`
- Python status file: `pycodex/exec/JSONL_EVENT_PROCESSOR_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust `EventProcessorWithJsonOutput` JSONL event
  collection/emission semantics, synthetic item id reuse, MCP result `_meta`
  serialization, usage/final-message state, todo-list updates, and failed-turn
  last-message protection. The two Rust module tests have direct Python
  counterparts.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.

### `src/event_processor.rs` parent processor contract

- Rust owner: `codex-exec`
- Rust module: `codex/codex-rs/exec/src/event_processor.rs`
- Python module: `pycodex/exec/event_processor.py`
- Python tests: `tests/test_exec_event_processor.py`
- Python status file: `pycodex/exec/EVENT_PROCESSOR_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors the parent Rust `CodexStatus` running/shutdown
  status contract and `handle_last_message` helper while keeping concrete
  human and JSONL rendering behavior scoped to the sibling Rust modules
  `event_processor_with_human_output.rs` and
  `event_processor_with_jsonl_output.rs`.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.

### `src/cli.rs` command-line surface

- Rust owner: `codex-exec`
- Rust module: `codex/codex-rs/exec/src/cli.rs`
- Rust tests: `codex/codex-rs/exec/src/cli_tests.rs`
- Python module: `pycodex/exec/cli.py`
- Python tests: `tests/test_exec_cli.py`
- Python status file: `pycodex/exec/CLI_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust root `Cli`, `Command`, `ResumeArgs`,
  `ReviewArgs`, `Color`, hidden `--full-auto` warning/conflict behavior,
  global flag handling after `resume`, output-schema/last-message globals
  after subcommands, config isolation flags, resume `--last` positional
  reinterpretation, and review target conflict/title requirements.
- Focused validation: deferred by current crate automation rule until
  `codex-exec` functional module code is complete.
