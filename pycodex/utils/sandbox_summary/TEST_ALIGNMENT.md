# codex-utils-sandbox-summary test alignment

Rust crate: `codex-utils-sandbox-summary`

Python module: `pycodex/utils/sandbox_summary/__init__.py`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs`
- `codex/codex-rs/utils/sandbox-summary/src/config_summary.rs`
- `codex/codex-rs/utils/sandbox-summary/src/lib.rs`

Rust-derived coverage added for `src/sandbox_summary.rs`:

- `tests::summarizes_external_sandbox_without_network_access_suffix`
- `tests::summarizes_external_sandbox_with_enabled_network`
- `tests::summarizes_read_only_with_enabled_network`
- `tests::workspace_write_summary_still_includes_network_access`
- `tests::permission_profile_summary_uses_runtime_workspace_roots_and_hides_internal_writes`

Source-contract coverage added for `src/config_summary.rs`:

- base effective config entries are emitted in Rust order.
- Responses API configs append reasoning effort and reasoning summaries.
- missing reasoning effort and summary values render as `none`.

Source-contract coverage added for `src/lib.rs`:

- crate-root public re-export surface includes `create_config_summary_entries`,
  `summarize_permission_profile`, and `summarize_sandbox_policy`.

Validation:

- `python -m pytest tests/test_utils_sandbox_summary.py -q`
- `python -m py_compile pycodex/utils/sandbox_summary/__init__.py tests/test_utils_sandbox_summary.py`
