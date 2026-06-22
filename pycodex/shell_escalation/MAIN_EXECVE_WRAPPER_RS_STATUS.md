# codex-shell-escalation src/bin/main_execve_wrapper.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/bin/main_execve_wrapper.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- on Unix, expose the binary main behavior by delegating to library `main_execve_wrapper`.
- on non-Unix, report that `codex-execve-wrapper` is only implemented for UNIX and exit with status 1.

Evidence:

- `codex_execve_wrapper_main` mirrors the binary module boundary and delegates to `main_execve_wrapper` on POSIX.
- Focused crate validation runs after this module because it completes the crate functional surface.
