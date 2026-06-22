# codex-utils-oss test alignment

Rust crate: `codex-utils-oss`

Rust module: `codex/codex-rs/utils/oss/src/lib.rs`

Python module: `pycodex/utils/oss/__init__.py`

Status: `complete`

Validation:

- `python -m pytest tests/test_utils_oss.py -q`
- `python -m py_compile pycodex/utils/oss/__init__.py tests/test_utils_oss.py`

Rust-derived coverage:

- `tests::test_get_default_model_for_provider_lmstudio`
- `tests::test_get_default_model_for_provider_ollama`
- `tests::test_get_default_model_for_provider_unknown`

Additional module-contract coverage:

- unknown providers skip readiness setup.
- LM Studio delegates to `ensure_oss_ready`.
- Ollama calls `ensure_responses_supported` before `ensure_oss_ready`.
- known providers require explicit Python backend facades instead of silently simulating local setup.
- `ensure_oss_ready` failures are wrapped with the Rust wording `OSS setup failed: ...`.

Known gaps: none for `src/lib.rs`. The concrete LM Studio and Ollama provider setup implementations belong to their own Rust crates and are intentionally outside this module boundary.
