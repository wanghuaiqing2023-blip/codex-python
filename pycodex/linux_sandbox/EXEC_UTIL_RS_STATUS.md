# codex-linux-sandbox src/exec_util.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/exec_util.rs`

Python module: `pycodex/linux_sandbox/exec_util.py`

Status: `complete`

Implemented behavior:

- `argv_to_cstrings(argv)` converts string argv entries to CString-compatible
  UTF-8 byte payloads.
- Interior NUL bytes are rejected with the Rust panic message prefix.
- `make_files_inheritable(files)` clears close-on-exec behavior for file-like
  objects or raw file descriptors.
- `clear_cloexec(fd)` is exposed as the direct fd helper used by the module.

Adaptation note:

- Rust returns `Vec<CString>`; Python represents CString payloads as `bytes`
  without a trailing NUL because Python's process APIs operate on strings or
  bytes at their own boundary.

Validation:

- `python -m py_compile pycodex/linux_sandbox/exec_util.py tests/test_linux_sandbox_exec_util_rs.py`
  (passed)

Focused crate validation is recorded in `TEST_ALIGNMENT.md`.
