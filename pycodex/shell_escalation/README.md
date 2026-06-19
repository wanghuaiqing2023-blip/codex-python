# pycodex.shell_escalation

Rust crate: `codex-shell-escalation`

Rust anchor: `codex/codex-rs/shell-escalation`

Current certified modules:

- `shell-escalation/src/lib.rs`
- `shell-escalation/src/bin/main_execve_wrapper.rs`
- `shell-escalation/src/unix/escalate_client.rs`
- `shell-escalation/src/unix/escalate_protocol.rs`
- `shell-escalation/src/unix/escalate_server.rs`
- `shell-escalation/src/unix/escalation_policy.rs`
- `shell-escalation/src/unix/execve_wrapper.rs`
- `shell-escalation/src/unix/socket.rs`
- `shell-escalation/src/unix/stopwatch.rs`

This package mirrors the Unix-only public crate facade exported from
`shell-escalation/src/lib.rs`. Protocol constants and decision shapes are
present as compatibility surfaces. Protocol records, socket framing helpers,
the policy interface, and stopwatch cancellation and pause accounting are
ported; the execve wrapper entrypoint is wired to the client wrapper function,
and the client/server handshake/request/response flow is represented. The
wrapper binary entrypoint is also represented.
