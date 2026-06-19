# pycodex.utils.oss

Python alignment target for Rust crate `codex-utils-oss`.

Rust coordinate:

- `codex/codex-rs/utils/oss/src/lib.rs`

Python mapping:

- `pycodex/utils/oss/__init__.py`

The module preserves Rust's OSS provider utility contract:

- LM Studio and Ollama provider ids map to their Rust default OSS model names.
- unknown providers have no default model and skip readiness setup.
- LM Studio readiness delegates to an injected `ensure_oss_ready` backend.
- Ollama readiness first checks responses API support, then delegates to `ensure_oss_ready`.
- backend readiness failures are reported as `OSS setup failed: ...`, matching the Rust IO error wording.
