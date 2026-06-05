# Turn-runtime resolved config analytics: sandbox network fallback

## Why

In the Python in-memory session path, `turn_context` can be created without a fully derived `network_sandbox_policy` value, while the thread snapshot may still carry an effective sandbox policy from session settings.

## Change

- Updated `pycodex/core/turn_runtime.py` in `_build_turn_resolved_config_payload`:
  - after reading `turn_context.network_sandbox_policy` and `permission_profile.network_sandbox_policy`, it now also checks `thread_config.network_sandbox_policy` and then `thread_config.sandbox_policy`.
  - `sandbox_network_access` continues to be derived through `_sandbox_network_access_enabled`.

## Compatibility impact

- This is a compatibility fallback only for analytics payload derivation and is scoped to the core turn path.
- If a `turn_context`-scoped value exists, it still takes precedence over thread-snapshot sources.
