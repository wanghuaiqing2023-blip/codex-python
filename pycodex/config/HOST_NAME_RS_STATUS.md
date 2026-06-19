# codex-config src/host_name.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/host_name.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/host_name.rs` |
| Python module | `pycodex/config/host_name.py` |
| Python export | `pycodex.config.host_name` |
| Python tests | `tests/test_config_host_name.py` |
| Status | `complete_candidate` |

`src/host_name.rs` owns best-effort local host-name normalization for remote
sandbox classification. Python mirrors the module with dependency-light
`socket` calls and a cached public `host_name()` helper.

## Covered Behavior Areas

- Kernel hostname normalization trims whitespace, trims trailing dots,
  lowercases, and rejects empty names.
- Canonical FQDN candidates are accepted only when the normalized name contains
  a dot.
- Short resolver names are rejected as FQDN candidates.
- The computed host name prefers a canonical FQDN when local resolution returns
  one, otherwise falls back to the cleaned kernel hostname.
- The public result is cached, matching Rust's `LazyLock<Option<String>>`
  behavior at the module boundary.

## Rust Test Inventory

The Rust module contains 3 local tests:

- `normalize_fqdn_candidate_accepts_dns_qualified_name`
- `normalize_fqdn_candidate_rejects_short_name`
- `normalize_fqdn_candidate_trims_trailing_dot_and_normalizes_case`

Python additionally covers source-derived fallback/caching behavior around
`compute_host_name`.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused config host-name
  tests and promote this module from `complete_candidate` to `complete`.
