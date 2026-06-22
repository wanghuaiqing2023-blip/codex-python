# codex-shell-escalation src/unix/execve_wrapper.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/execve_wrapper.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- parse an executable `file` followed by trailing argv entries.
- expose a `main_execve_wrapper` entrypoint that delegates to `run_shell_escalation_execve_wrapper`.
- preserve the returned exit code as the entrypoint result instead of implementing client execution in this module.

Evidence:

- `ExecveWrapperCli.parse` mirrors the Rust clap struct shape.
- `main_execve_wrapper` is async and delegates to the client wrapper function, matching the Rust module boundary.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
