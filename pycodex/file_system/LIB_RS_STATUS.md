# codex-file-system src/lib.rs status

Rust coordinate: `codex/codex-rs/file-system/src/lib.rs`

Python coordinate: `pycodex/file_system/__init__.py`

Status: `complete`

Behavior contract:

- expose operation option records, metadata records, directory entries, and `FileSystemResult`-equivalent exception behavior through Python I/O errors.
- expose `FileSystemSandboxContext` constructors and sandbox/cwd predicates.
- project legacy `SandboxPolicy` values through the protocol permission-profile conversion layer.
- expose `ExecutorFileSystem` async trait shape with `read_file_text` default behavior.

Evidence:

- `tests/test_file_system_lib_rs.py` covers the Rust source contract for record equality, context construction, cwd-dependent policy detection, UTF-8 text reads, and local executor behavior.
