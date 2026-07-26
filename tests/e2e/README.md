# End-to-end tests

This tree verifies complete user-visible product paths. It is intentionally
separate from `parity_harness`, which owns static architecture contracts.

- `support/` contains process drivers, deterministic Responses fixtures, VT
  projection, and captured evidence.
- `tui/` groups terminal scenarios by user-facing workflow.
- `app_server/` covers the real stdio command boundary.
- `windows_sandbox/` covers the conversation-to-sandbox execution path.

Native Rust/Python comparisons remain opt-in through the existing
`PYCODEX_RUN_*` environment gates. Unit checks for the E2E drivers run without
those gates.
