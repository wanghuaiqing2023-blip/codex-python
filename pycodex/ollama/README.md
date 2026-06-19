# pycodex.ollama

Rust crate: `codex-ollama`

Rust anchor: `codex/codex-rs/ollama`

Module map:

- `codex/codex-rs/ollama/src/url.rs` ->
  `pycodex/ollama/url.py` (`complete`)
- `codex/codex-rs/ollama/src/parser.rs` ->
  `pycodex/ollama/parser.py` (`complete`)
- `codex/codex-rs/ollama/src/client.rs` ->
  `pycodex/ollama/client.py` (`complete`)
- `codex/codex-rs/ollama/src/pull.rs` ->
  `pycodex/ollama/pull.py` (`complete`)
- `codex/codex-rs/ollama/src/lib.rs` ->
  `pycodex/ollama/__init__.py` (`complete`)

The current Python package exposes the URL helper slice, the Ollama HTTP
client, the pull-update parser used by streaming model downloads, and CLI/TUI
pull progress reporter behavior. The crate-root readiness helpers are also
mapped; focused crate validation determines final completion status.
