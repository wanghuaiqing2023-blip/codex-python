# codex-cloud-requirements

Rust crate: `codex-cloud-requirements`

Rust anchor: `codex/codex-rs/cloud-requirements`

Current certified modules:

- `cloud-requirements/src/lib.rs`

The single Rust module is represented by `pycodex/cloud_requirements/__init__.py`.
It implements the cloud requirements service boundary, including backend fetch
helpers, business/enterprise auth eligibility, timeout/retry/auth recovery,
TOML parsing through `pycodex.config.ConfigRequirementsToml`, signed cache
read/write behavior, and loader factory exports.

Remaining Rust modules: none.
