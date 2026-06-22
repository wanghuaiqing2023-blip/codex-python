# codex-config src/permissions_toml.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/permissions_toml.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/permissions_toml.rs` |
| Python module | `pycodex/config/permissions_toml.py` |
| Python tests | `tests/test_config_permissions_toml.py` |
| Status | `complete_candidate` |

`src/permissions_toml.rs` owns permission profile TOML shapes, profile
inheritance resolution, workspace root filtering, filesystem/network
permission helpers, network proxy application, MITM hook/action validation,
and runtime MITM conversion.

## Covered Behavior Areas

- `WorkspaceRootsToml.enabled_roots` returns only enabled roots.
- Domain and Unix socket permission containers expose allowed/denied entries
  and map fixed lowercase permission values.
- Permission profiles resolve parent chains, merge inherited fields, track
  inherited profile names, and preserve selected-profile metadata.
- Undefined profiles, undefined parents, unsupported built-in parents, and
  inheritance cycles produce Rust-shaped error messages.
- Parent profile metadata is dropped during inheritance merges.
- Network domain keys are normalized when merging profile network domains.
- Profile/network parsers reject unknown fields and invalid enum values.
- `NetworkToml` applies network fields, domain overlays, Unix socket overlays,
  local binding, mode, and MITM hooks to `NetworkProxyConfig`.
- MITM actions and hooks fail closed for empty action definitions, empty hook
  action lists, and undefined action references.
- MITM runtime conversion preserves hook declaration order and selected action
  effects, including stripped and injected headers.
- `overlay_network_domain_permissions` applies allow/deny overlays through the
  network proxy domain permission helper.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from source-level contracts in `permissions_toml.rs` and from downstream Rust
config behavior that consumes these TOML structures.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused permissions TOML
  tests and promote this module from `complete_candidate` to `complete`.
