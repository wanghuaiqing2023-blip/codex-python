# pycodex.exec_server

Rust crate: `codex-exec-server`

Rust anchor: `codex/codex-rs/exec-server`

This package mirrors the public crate interface exported from
`exec-server/src/lib.rs`.  Protocol constants and request/response data shapes
are ported for `codex-core` compatibility; the actual process server, remote
transport, and filesystem helper runtime are explicit unported boundaries.
