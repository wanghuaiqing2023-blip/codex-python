# codex-utils-sandbox-summary src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/sandbox-summary/src/lib.rs`

Python coordinate: `pycodex/utils/sandbox_summary/__init__.py`

Status: `complete`

Behavior contract:

- crate root declares `config_summary` and `sandbox_summary` modules.
- crate root publicly re-exports `create_config_summary_entries`.
- crate root publicly re-exports `summarize_permission_profile`.
- crate root publicly re-exports `summarize_sandbox_policy`.

Evidence:

- `tests/test_utils_sandbox_summary.py::test_lib_rs_public_reexports_match_python_public_surface` verifies the Python public surface matches the Rust crate-root re-export surface.
- With `src/sandbox_summary.rs` and `src/config_summary.rs` already certified, this completes the crate module set.
