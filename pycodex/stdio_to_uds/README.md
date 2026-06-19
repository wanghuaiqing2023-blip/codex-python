# codex-stdio-to-uds

Rust crate: `codex-stdio-to-uds`

Rust anchor: `codex/codex-rs/stdio-to-uds`

Current certified modules:

- `stdio-to-uds/src/lib.rs`
- `stdio-to-uds/src/main.rs`

This package mirrors the library relay surface from `src/lib.rs`: connecting to
a Unix domain socket path, copying stdin to the socket, copying socket data to
stdout, flushing stdout, and treating a socket-writer shutdown `NotConnected`
race as benign while preserving other relay errors.

The binary entrypoint from `src/main.rs` is represented by `main`: it preserves
the exact argument-count diagnostics and delegates the single socket-path
argument to the library relay entrypoint without option parsing.

Remaining Rust modules: none.
