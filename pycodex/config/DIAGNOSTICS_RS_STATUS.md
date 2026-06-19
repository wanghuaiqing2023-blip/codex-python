# codex-config src/diagnostics.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/diagnostics.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/diagnostics.rs` |
| Python module | `pycodex/config/diagnostics.py` |
| Python exports | `pycodex.config.ConfigError`, `pycodex.config.ConfigLoadError`, `pycodex.config.TextPosition`, `pycodex.config.TextRange`, diagnostic formatting and first-layer helpers |
| Python tests | `tests/test_config_diagnostics.py` |
| Status | `complete_candidate` |

`src/diagnostics.rs` owns config parse/validation diagnostic locations,
1-based text ranges, user-facing error rendering, and first concrete config
layer error discovery.

## Covered Behavior Areas

- `TextPosition`, `TextRange`, and `ConfigError` preserve 1-based line/column
  coordinates.
- `ConfigLoadError` displays as `path:line:column: message` and exposes the
  underlying `ConfigError`.
- TOML decode errors map to a `ConfigError` with source path, message, and a
  best available text range.
- Typed TOML validation errors return `ConfigError` rather than raising.
- `first_layer_config_error_from_entries` skips missing/unreadable layers and
  returns the first concrete file error.
- `text_range_from_span` uses `span.end - 1` for non-empty spans.
- `format_config_error` renders the header, source line, gutter, and caret
  span; `format_config_error_with_source` falls back to the header when source
  text cannot be read.
- TOML key-path span helpers provide lightweight source anchoring for strict
  config diagnostics.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from source-level contracts and downstream strict-config usage.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused diagnostics tests
  and promote this module from `complete_candidate` to `complete`.
