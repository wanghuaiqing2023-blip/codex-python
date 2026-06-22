# pycodex.file_system

Python port of Rust crate `codex-file-system`.

Rust coordinate:

- `codex/codex-rs/file-system/src/lib.rs`

Python coordinate:

- `pycodex/file_system/__init__.py`

Status: complete for the single Rust module.

Notes:

- `FileSystemSandboxContext` delegates legacy sandbox and permission-profile conversion to the completed `pycodex.protocol` permission model.
- `ExecutorFileSystem` mirrors the Rust async trait surface. `LocalExecutorFileSystem` is a small Python local implementation used for parity tests and local callers.
