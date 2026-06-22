# codex-tools `src/lib.rs` alignment

Status: `complete`

Rust owner:

- Crate: `codex-tools`
- Module: `codex/codex-rs/tools/src/lib.rs`

Python owner:

- Package root: `pycodex/tools/__init__.py`

Behavior covered:

- The Python package root exposes the same canonical helper surface owned by
  Rust `src/lib.rs`: code-mode adapters, dynamic/MCP parsers, shared tool
  errors, image-detail helpers, JSON Schema helpers, request-plugin-install
  helpers, response-history helpers, Responses API primitives, tool call/config
  definition/discovery/executor/output/payload/spec types, and `ToolName`.
- Module-specific behavior remains owned by the individual Python modules and
  status files; this crate-root status records the re-export/public-surface
  contract only.

Rust tests:

- No direct Rust tests for `src/lib.rs`; behavior is covered by child module
  tests and downstream imports.

Python tests:

- Focused `codex-tools` validation passed on 2026-06-17:
  `313 passed, 2 skipped, 5 subtests passed`.

Notes:

- Python intentionally exposes a few compatibility helpers beyond the exact
  Rust root exports where existing callers already depend on them.
