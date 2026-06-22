# codex-linux-sandbox src/launcher.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/launcher.rs`

Python module: `pycodex/linux_sandbox/launcher.py`

Status: `complete`

Implemented behavior:

- System bubblewrap capability shape (`supports_argv0`, `supports_perms`).
- System launcher selection requires an existing file and `--perms` support.
- `--argv0` support is preserved but not required for system launcher use.
- Preferred launcher selection checks system bwrap before bundled/unavailable.
- `preferred_bwrap_supports_argv0()` mirrors Rust's system-vs-bundled/default
  behavior.
- `exec_system_bwrap()` preserves file descriptors and validates argv before
  calling `os.execv`.

Runtime boundary:

- Tests do not execute `exec_bwrap()` or `exec_system_bwrap()` because they
  replace the current process, matching the Rust `execv` boundary.
- Full bundled bwrap verification is owned by sibling `src/bundled_bwrap.rs`.

Validation:

- `python -m py_compile pycodex/linux_sandbox/launcher.py tests/test_linux_sandbox_launcher_rs.py`
  (passed)

Focused crate validation is recorded in `TEST_ALIGNMENT.md`.
