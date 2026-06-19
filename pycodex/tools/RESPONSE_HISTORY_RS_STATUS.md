# codex-tools src/response_history.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/response_history.rs`
Rust tests: inline `#[cfg(test)]` tests in `response_history.rs`
Python module: `pycodex/tools/response_history.py`
Python tests: deferred; Rust-derived coverage should mirror the inline Rust
tests for tail retention and assistant output token-budget truncation.

## Behavior contract

`src/response_history.rs` owns two mutation helpers for response history:

- `retain_tail_from_last_n_user_messages`, which keeps items from the earliest
  retained user message through the latest user message and drops later items.
- `truncate_assistant_output_text_to_token_budget`, which spends one shared
  approximate token budget across assistant `output_text` content items,
  truncates the first over-budget text item, and drops later assistant output
  text/items when no budget remains.

## Python alignment

`pycodex.tools.response_history` mirrors the Rust mutation semantics for
`ResponseItem` objects and mapping-shaped items. It uses the existing protocol
`ResponseItem`/`ContentItem` model and the shared output truncation helpers for
approximate token counting and token-budget text truncation.

## Evidence

The Rust behavior contract is described by the inline tests in
`codex/codex-rs/tools/src/response_history.rs`. Focused Python test migration
is deferred by the current crate automation rule until `codex-tools` functional
module code is complete.
