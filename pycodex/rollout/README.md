# pycodex.rollout

Python port target for Rust `codex-rollout`.

## Module mapping

- Rust `codex/codex-rs/rollout/src/metadata.rs` maps to metadata helpers in `pycodex/rollout/__init__.py`.
- `ThreadMetadataBuilder` is a semantic model for Rust `codex_state::ThreadMetadataBuilder`; it does not copy Rust storage types, but keeps the same required fields and defaults used by rollout metadata extraction and backfill.
