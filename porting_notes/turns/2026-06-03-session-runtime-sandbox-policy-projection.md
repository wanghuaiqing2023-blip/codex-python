## Session runtime sandbox-policy projection

- Date: 2026-06-03
- Scope: `pycodex/core/session_runtime.py`

## What changed
- Added `_permission_profile_from_sandbox_policy(...)` helper to map `SandboxPolicy` updates to an effective
  `PermissionProfile` using compatibility projection.
- On settings updates:
  - When `permission_profile` is provided, session updates now sync `file_system_sandbox_policy` and refresh
    `sandbox_policy` from legacy mapping when available.
  - When only `sandbox_policy` is provided, it is converted to `permission_profile` through
    `SandboxEnforcement.from_legacy_sandbox_policy`, preserving existing deny entries from the current file-system
    profile via `from_legacy_sandbox_policy_preserving_deny_entries`.
- Snapshot paths (`_snapshot_for_settings`) now apply the same `sandbox_policy`→`permission_profile` projection for
  preview-only settings, so analytics and turn-config snapshots reflect the projected runtime state.

## Why
- Rust session apply logic writes `sandbox_policy` updates through `permission_profile` projection rather than treating
  policy and profile as independent fields.
- This change closes a consistency gap where snapshot-based analytics and turn-context construction could diverge when
  `sandbox_policy` was updated without an explicit `permission_profile`.
