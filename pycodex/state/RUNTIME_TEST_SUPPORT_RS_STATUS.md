# `codex-state/src/runtime/test_support.rs` Python alignment

Status: `complete`

Rust owner:

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/runtime/test_support.rs`

Python owner:

- Module: `pycodex/state/runtime/test_support.py`
- Package exports: `pycodex.state.runtime`, `pycodex.state`

## Behavior contract

This module mirrors the Rust `#[cfg(test)]` runtime helper surface:

- `unique_temp_dir()` returns a path under the system temporary directory with
  the prefix `codex-state-runtime-test-`, a nanosecond timestamp component, and
  a random UUID suffix.
- `test_thread_metadata(codex_home, thread_id, cwd)` returns a
  `ThreadMetadata` fixture with the same fixed values as Rust:
  - timestamp `1_700_000_000` UTC for `created_at` and `updated_at`
  - rollout path `codex_home / f"rollout-{thread_id}.jsonl"`
  - source `cli`
  - provider `test-provider`
  - model `gpt-5`
  - reasoning effort `medium`
  - CLI version `0.0.0`
  - empty title, preview and first user message `hello`
  - read-only sandbox policy and on-request approval mode encoded through the
    same `enum_to_string` helper used by `extract.rs`
  - zero tokens and no archived/git metadata.

## Scope notes

Rust compiles this module only for tests. The Python port keeps it as a small
runtime test-support helper for parity fixtures; it does not expand runtime
store behavior.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_runtime_test_support_rs.py -q
# 4 passed

python -m py_compile pycodex\state\runtime\test_support.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py tests\test_state_runtime_test_support_rs.py
```

Coverage includes temp-dir prefix/timestamp/UUID shape, fixed
`ThreadMetadata` fixture fields, string-path convenience with `ThreadId`
validation, and runtime/package-root helper re-exports.
