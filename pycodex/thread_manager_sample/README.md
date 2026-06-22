# pycodex.thread_manager_sample

Python alignment target for Rust crate `codex-thread-manager-sample`.

Rust coordinates:

- `codex/codex-rs/thread-manager-sample/src/main.rs`

Python mapping:

- `pycodex/thread_manager_sample/__init__.py`

Current status: complete.

Certified modules:

- `src/main.rs`: complete. The Python module mirrors the sample binary's CLI
  parser, prompt/stdin handling, config construction defaults, single-turn
  ThreadManager lifecycle, event-to-server-notification mapping, JSONL output,
  shutdown/remove ordering, and fatal event branches.

Validation:

- Focused crate validation:
  `python -m pytest tests/test_thread_manager_sample_main_rs.py -q` -> `7 passed`
