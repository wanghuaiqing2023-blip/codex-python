# codex-utils-sandbox-summary src/config_summary.rs status

Rust coordinate: `codex/codex-rs/utils/sandbox-summary/src/config_summary.rs`

Python coordinate: `pycodex/utils/sandbox_summary/__init__.py`

Status: `complete`

Behavior contract:

- `create_config_summary_entries` returns base effective-config entries in Rust order: `workdir`, `model`, `provider`, `approval`, and `sandbox`.
- `approval` uses the approval policy value string.
- `sandbox` is rendered through `summarize_sandbox_policy` over the permissions legacy sandbox policy for the config cwd.
- configs whose model provider uses the Responses wire API append `reasoning effort` and `reasoning summaries`.
- missing reasoning effort or summary values render as `none`.

Evidence:

- `tests/test_utils_sandbox_summary.py` includes source-contract tests for the base entry list and Responses-only reasoning entries.
- Actual test execution is deferred until the remaining crate module `src/lib.rs` is certified.
