# codex-shell-escalation src/unix/escalate_server.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/escalate_server.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- expose `ShellCommandExecutor`, `ExecParams`, `ExecResult`, `PreparedExec`, `EscalationSession`, and `EscalateServer`.
- create an escalation session with only the wrapper/socket environment overlay.
- close the inherited client socket after shell spawn.
- handle client handshakes, escalation requests, policy decisions, and run/escalate/deny responses.
- prepare and execute escalated commands through the caller-provided command executor.

Evidence:

- `EscalateServer.start_session` and `EscalateServer.exec` mirror the Rust session lifecycle at Python compatibility level.
- `handle_escalate_session_with_policy` mirrors the Rust request/decision/response flow.
- Actual pytest validation is deferred until the crate's remaining wrapper binary module is complete.
