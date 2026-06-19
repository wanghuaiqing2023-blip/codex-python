# codex-lmstudio

Rust crate: `codex-lmstudio`

Rust anchor: `codex/codex-rs/lmstudio`

Current certified modules:

- `lmstudio/src/client.rs`
- `lmstudio/src/lib.rs`

Python maps `client.rs` to `pycodex/lmstudio/client.py`. The module covers the
LM Studio client surface: provider-based construction, `/models` server checks,
model listing, `/responses` model-load probe, `lms` discovery, and `lms get
--yes <model>` download command execution.

Python maps `lib.rs` to `pycodex/lmstudio/__init__.py`. The crate root exports
`LMStudioClient`, exposes the Rust default OSS model constant, and implements
`ensure_oss_ready(...)` orchestration: provider construction, missing-model
download, nonfatal model-listing failures, and background model loading.

Remaining Rust modules: none.
