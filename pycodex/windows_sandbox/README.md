# pycodex.windows_sandbox

Rust crate: `codex-windows-sandbox`

Rust anchor: `codex/codex-rs/windows-sandbox-rs`

This package mirrors the public crate interface exported from
`windows-sandbox-rs/src/lib.rs` at the immutable project baseline
`1c7832ffa37a3ab56f601497c00bfce120370bf9`.

## Status

The native Windows product path is implemented and manually accepted. It
includes permission resolution, restricted and sandbox-user tokens,
capability/ACL setup, deny reconciliation, private desktops, stdio and ConPTY,
Job Object descendant cleanup, offline/online network identities, firewall and
WFP setup, elevated framed transport, and fail-closed raw/unified execution.

Python splits the Rust runner client, command runner, framed IPC, ConPTY, and
unified-exec responsibilities across adapter files. These adapters do not
change the fixed-Rust security contract: setup or spawn failures never retry
through an unrestricted process.

Authoritative evidence:

- `WINDOWS_SANDBOX_ALIGNMENT.md` for the owner map and delivery gates.
- `WINDOWS_SANDBOX_PARITY_EVIDENCE.md` for fixed-Rust/Python probes.
- `WINDOWS_SANDBOX_MANUAL_ACCEPTANCE.md` for Windows Terminal acceptance.
- `tests/test_windows_sandbox_*.py` and the focused core/TUI permission tests
  for Rust-derived regression coverage.
