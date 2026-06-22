# codex-shell-escalation src/unix/escalate_client.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/escalate_client.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- read the inherited escalation datagram socket from `CODEX_ESCALATE_SOCKET`.
- reject negative socket file descriptors.
- duplicate file descriptors before transferring them.
- filter internal protocol environment variables from `EscalateRequest.env`.
- send the client handshake, then send `EscalateRequest`.
- handle `Escalate`, `Run`, and `Deny` responses with the same high-level semantics as Rust.

Evidence:

- `get_escalate_client`, `duplicate_fd_for_transfer`, `shell_escalation_request_env`, and `run_shell_escalation_execve_wrapper` mirror the Rust client module boundary.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
