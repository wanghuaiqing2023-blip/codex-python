# pycodex.utils.sandbox_summary

Python alignment target for Rust crate `codex-utils-sandbox-summary`.

Rust coordinates:

- `codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs`
- `codex/codex-rs/utils/sandbox-summary/src/config_summary.rs`
- `codex/codex-rs/utils/sandbox-summary/src/lib.rs`

Python mapping:

- `pycodex/utils/sandbox_summary/__init__.py`

Current status: complete.

Certified modules:

- `src/sandbox_summary.rs`: sandbox policy summaries and permission profile summaries.
- `src/config_summary.rs`: effective config summary entry construction.
- `src/lib.rs`: crate-root public re-export surface.

Focused validation:

- `python -m pytest tests/test_utils_sandbox_summary.py -q`
- `python -m py_compile pycodex/utils/sandbox_summary/__init__.py tests/test_utils_sandbox_summary.py`
