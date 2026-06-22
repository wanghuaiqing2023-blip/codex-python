# codex-shell-escalation src/unix/escalate_protocol.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/escalate_protocol.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- expose `ESCALATE_SOCKET_ENV_VAR` and `EXEC_WRAPPER_ENV_VAR`.
- model request/response protocol records for intercepted exec calls.
- represent run/escalate/deny actions, including optional deny reasons.
- model super-exec file-descriptor forwarding and exit-code result records.

Evidence:

- `EscalateRequest`, `EscalateResponse`, `EscalateAction`, `SuperExecMessage`, and `SuperExecResult` mirror the Rust protocol items.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
