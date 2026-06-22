# codex-process-hardening test alignment

Rust crate: `codex-process-hardening`

Python package: `pycodex/process_hardening`

Status: `complete`

Certified modules:

- `codex/codex-rs/process-hardening/src/lib.rs` -> `pycodex/process_hardening/__init__.py`

Rust-test/source-contract coverage:

- `env_keys_with_prefix_handles_non_utf8_entries`.
- `env_keys_with_prefix_filters_only_matching_keys`.
- platform dispatch for Linux/macOS/BSD/Windows hardening branches.
- Rust exit codes for Linux `prctl`, macOS `ptrace`, and core-limit failures.
- LD_/DYLD_ environment variable removal prefixes.

Validation:

- `python -m pytest tests/test_process_hardening_lib_rs.py -q`
- `python -m py_compile pycodex/process_hardening/__init__.py tests/test_process_hardening_lib_rs.py`
