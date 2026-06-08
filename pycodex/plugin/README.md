# pycodex.plugin

Rust crate: `codex-plugin`

Rust anchor: `codex/codex-rs/plugin`

This package mirrors the public crate interface exported from
`plugin/src/lib.rs`.  Plugin identifiers, descriptions, capability summaries,
and path/namespace helpers are ported; plugin loading/runtime remains a
compatibility interface unless implemented by a selected module slice.
