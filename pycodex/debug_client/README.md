# pycodex.debug_client

Rust crate: `codex-debug-client`

Rust anchor: `codex/codex-rs/debug-client`

Module map:

- `codex/codex-rs/debug-client/src/commands.rs` ->
  `pycodex/debug_client/commands.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/output.rs` ->
  `pycodex/debug_client/output.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/state.rs` ->
  `pycodex/debug_client/state.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/reader.rs` ->
  `pycodex/debug_client/reader.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/client.rs` ->
  `pycodex/debug_client/client.py` (`complete_candidate`)
- `codex/codex-rs/debug-client/src/main.rs` ->
  `pycodex/debug_client/main.py` and `pycodex/debug_client/__main__.py`
  (`complete_candidate`)

The current Python package exposes the interactive command parser and output
coordination/state helpers, the server reader loop helpers, and the
app-server process client facade. CLI entrypoint behavior is mapped through
`main.py` and the package executable shim.
