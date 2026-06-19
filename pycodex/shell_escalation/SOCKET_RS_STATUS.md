# codex-shell-escalation src/unix/socket.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/socket.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- expose the socket protocol limits: max FDs per message, length-prefix size, and max datagram size.
- encode stream frame lengths as little-endian `u32`, rejecting oversized messages.
- provide async stream socket helpers for JSON-framed send/receive with optional FD passing.
- provide async datagram socket helpers for bytes send/receive with optional FD passing.
- reject excessive FD counts before attempting ancillary-data writes.

Evidence:

- `AsyncSocket`, `AsyncDatagramSocket`, and `encode_length` mirror the Rust module's public helper surface at Python compatibility level.
- SCM_RIGHTS behavior is runtime-gated by platform support so the package remains importable on non-Unix hosts.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
