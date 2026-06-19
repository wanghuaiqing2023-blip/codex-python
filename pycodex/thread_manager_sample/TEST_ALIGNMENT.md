# codex-thread-manager-sample test alignment

Rust crate: `codex-thread-manager-sample`

Python package: `pycodex/thread_manager_sample`

Status: `complete`

Module mapping:

- `codex/codex-rs/thread-manager-sample/src/main.rs` -> `pycodex/thread_manager_sample/__init__.py` (`complete`)

Rust tests:

- Rust test scan found no crate-local test functions.

Source-contract coverage:

- `Args` parser supports `--model` and trailing prompt tokens.
- Missing prompt behavior matches Rust: terminal stdin errors, piped blank stdin
  errors, piped CRLF/CR text normalizes to LF, prompt args join with spaces.
- `new_config(...)` preserves the sample defaults that are local to this crate:
  OpenAI provider selection, read-only/no-approval permissions intent,
  ephemeral config, disabled analytics/feedback, workspace roots, arg0 paths,
  disabled web search, and 300-second background terminal timeout.
- `run_turn(...)` submits `Op.user_input`, tracks `TurnStarted`, writes mapped
  server notifications as newline-delimited JSON, returns on `TurnComplete`,
  and errors on the same request/approval/fatal event classes as Rust.
- `run_main(...)` preserves the start-thread, run-turn, shutdown, and remove
  ordering with injectable runtime adapters.

Validation:

- `python -m pytest tests/test_thread_manager_sample_main_rs.py -q`
  -> `7 passed`
