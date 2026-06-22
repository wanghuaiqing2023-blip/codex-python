# codex-shell-escalation src/lib.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/lib.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- expose the Unix-only shell escalation public API from `src/unix/mod.rs`.
- preserve `ESCALATE_SOCKET_ENV_VAR` and public decision/action/execution shapes.
- keep execve wrapper and socket server runtime as documented unported submodule debt.

Evidence:

- `pycodex.shell_escalation.__all__` mirrors the Rust `pub use` surface from `src/lib.rs` and `src/unix/mod.rs`.
- Focused runtime tests are deferred until the remaining `src/unix/*` behavior modules are ported.
