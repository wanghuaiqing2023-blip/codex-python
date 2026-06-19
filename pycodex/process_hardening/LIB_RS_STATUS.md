# codex-process-hardening src/lib.rs status

Rust coordinate: `codex/codex-rs/process-hardening/src/lib.rs`

Python coordinate: `pycodex/process_hardening/__init__.py`

Status: `complete`

Behavior contract:

- expose pre-main hardening entrypoints for Linux/Android, macOS, BSD, and Windows.
- map Linux `prctl`, macOS `ptrace`, and core-limit failures to Rust's documented exit codes.
- remove environment variables by raw byte prefix where Python exposes `os.environb`.
- preserve Rust test behavior for non-UTF-8 environment keys.

Evidence:

- `tests/test_process_hardening_lib_rs.py` ports the Rust env-key tests and adds source-contract coverage for branch dispatch, failure exit codes, and environment removal.
