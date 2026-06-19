# codex-thread-manager-sample src/main.rs status

Rust source:

- `codex/codex-rs/thread-manager-sample/src/main.rs`

Python target:

- `pycodex/thread_manager_sample/__init__.py`

Status: complete.

Implemented contract:

- CLI argument parsing for optional `--model` and trailing prompt tokens.
- Prompt acquisition from args or non-terminal stdin with Rust newline
  normalization and blank-input errors.
- Sample config construction using the existing `core_api` facade, preserving
  the sample's local defaults and arg0 path propagation.
- One-turn ThreadManager lifecycle with state DB initialization, thread store
  creation, environment manager setup, thread start, turn execution,
  shutdown, and thread removal.
- Turn execution submits text user input, tracks the current turn id, maps
  supported item events to app-server server notifications, emits JSONL, and
  errors on Rust's fatal/request event branches.

Validation:

- `python -m pytest tests/test_thread_manager_sample_main_rs.py -q`
  -> `7 passed`
