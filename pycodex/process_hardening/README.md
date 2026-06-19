# pycodex.process_hardening

Python port of Rust crate `codex-process-hardening`.

Rust coordinate:

- `codex/codex-rs/process-hardening/src/lib.rs`

Python coordinate:

- `pycodex/process_hardening/__init__.py`

Status: complete for the single Rust module.

Notes:

- Rust is designed for `#[ctor]` pre-main hardening. Python exposes the same behavior as explicit functions.
- Tests monkeypatch platform and system calls so they do not change the current Python process hardening state.
