# pycodex.utils.stream_parser

Python port of the core modules from Rust `codex-utils-stream-parser`.

Rust coordinate:

- Crate: `codex-utils-stream-parser`
- Modules currently ported:
  - `src/stream_text.rs`
  - `src/inline_hidden_tag.rs`
  - `src/citation.rs`
  - `src/utf8_stream.rs`
  - `src/tagged_line_parser.rs` as an internal helper
  - `src/proposed_plan.rs`
  - `src/assistant_text.rs`

Behavior preserved:

- Incremental chunks expose visible text and extracted hidden payloads.
- Inline hidden tags are literal, case-sensitive, non-nested, and can span chunk boundaries.
- Unterminated active hidden tags auto-close on `finish()`.
- Incomplete opener/closer prefixes are buffered until a later chunk or flushed at EOF.
- Citation helpers wrap `<oai-mem-citation>...</oai-mem-citation>`.
- UTF-8 byte streams buffer split code points, roll back an entire invalid pushed chunk, and report incomplete UTF-8 at EOF.
- Proposed-plan blocks are recognized only when `<proposed_plan>` and `</proposed_plan>` appear alone on trimmed lines, can stream across chunk boundaries, are hidden from visible text, and auto-close at EOF.
- Assistant text parsing composes citation stripping first, then proposed-plan stripping when plan mode is enabled, preserving citation and plan segment side channels.

Deferred Rust modules:

- None for the current Rust crate public surface.

Runtime integration with `pycodex.core.stream_events_utils` remains a separate core module contract.
