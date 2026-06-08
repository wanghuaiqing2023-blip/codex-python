# pycodex.shell_escalation

Rust crate: `codex-shell-escalation`

Rust anchor: `codex/codex-rs/shell-escalation`

This package mirrors the Unix-only public crate interface exported from
`shell-escalation/src/lib.rs` and `src/unix/mod.rs`.  Protocol constants and
decision shapes are ported; the patched-shell socket server and execve wrapper
runtime are explicit unported boundaries.
