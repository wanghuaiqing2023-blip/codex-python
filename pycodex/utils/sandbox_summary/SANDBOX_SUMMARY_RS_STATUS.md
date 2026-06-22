# codex-utils-sandbox-summary src/sandbox_summary.rs status

Rust coordinate: `codex/codex-rs/utils/sandbox-summary/src/sandbox_summary.rs`

Python coordinate: `pycodex/utils/sandbox_summary/__init__.py`

Status: `complete`

Behavior contract:

- `summarize_sandbox_policy` renders danger-full-access, read-only, external-sandbox, and workspace-write policies.
- read-only and workspace-write include a network suffix when network access is enabled.
- external-sandbox includes a network suffix only for enabled network access.
- workspace-write entries include `workdir`, optional `/tmp`, optional `$TMPDIR`, and explicit writable roots.
- `summarize_permission_profile` uses runtime workspace roots for workspace-write summaries and does not expose internal profile writable roots.
- custom permission profiles fall back to custom permission summaries with an optional network suffix.

Evidence:

- `tests/test_utils_sandbox_summary.py` maps the five Rust tests in `src/sandbox_summary.rs`.
- Actual test execution is deferred until the remaining crate modules are certified.
