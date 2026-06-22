# pycodex.feedback

Rust crate: `codex-feedback`

Rust anchor: `codex/codex-rs/feedback`

This package mirrors the public interface from `feedback/src/lib.rs` and the
connectivity diagnostics helper from `feedback/src/feedback_diagnostics.rs`.

Module map:

- `codex/codex-rs/feedback/src/feedback_diagnostics.rs` ->
  `pycodex/feedback/feedback_diagnostics.py` (`complete`)
- `codex/codex-rs/feedback/src/lib.rs` -> `pycodex/feedback/__init__.py`
  (`complete`)

Local feedback tag and log-buffer shapes are ported; remote feedback/Sentry
upload is represented by an injectable upload-event boundary so the crate keeps
standard-library-only behavior while preserving Rust's event/tag/attachment
construction semantics.
