# codex-file-system test alignment

Rust crate: `codex-file-system`

Python package: `pycodex/file_system`

Status: `complete`

Certified modules:

- `codex/codex-rs/file-system/src/lib.rs` -> `pycodex/file_system/__init__.py`

Rust-test/source-contract coverage:

- option and metadata records preserve value equality and immutable record semantics.
- `FileSystemSandboxContext` constructors preserve permission profile, cwd, Windows sandbox defaults, and legacy sandbox projection.
- `should_run_in_sandbox`, `has_cwd_dependent_permissions`, and `drop_cwd_if_unused` match the Rust predicate contract.
- `file_system_policy_has_cwd_dependent_entries` returns true only for relative glob entries and `ProjectRoots` special paths.
- `ExecutorFileSystem.read_file_text` delegates to `read_file` and decodes UTF-8.

Validation:

- `python -m pytest tests/test_file_system_lib_rs.py -q`
- `python -m py_compile pycodex/file_system/__init__.py tests/test_file_system_lib_rs.py`
