# codex-sandboxing/src/policy_transforms.rs Status

Status: complete_candidate

Rust source:

```text
codex/codex-rs/sandboxing/src/policy_transforms.rs
codex/codex-rs/sandboxing/src/policy_transforms_tests.rs
```

Python mapping:

```text
pycodex/sandboxing/policy_transforms.py
pycodex/core/tools/handlers/utils.py
pycodex/core/sandbox_tags.py
pycodex/protocol/models.py
```

Aligned behavior:

- `normalize_additional_permissions(...)` removes empty nested profiles,
  rejects non-deny glob permissions, canonicalizes simple path entries while
  preserving symlink spelling, and de-duplicates filesystem entries.
- `merge_permission_profiles(...)` and `intersect_permission_profiles(...)`
  expose the Rust additional-permission merge/intersection contract from the
  crate-aligned package path, reusing the existing core handler implementation.
- `merge_file_system_policy_with_additional_permissions(...)`,
  `effective_file_system_sandbox_policy(...)`,
  `effective_network_sandbox_policy(...)`, and
  `effective_permission_profile(...)` mirror Rust runtime policy projection,
  including restricted-network fallback whenever additional permissions are
  present without an enabled network grant.
- `merge_glob_scan_max_depth(...)` and `effective_glob_scan_depth(...)` preserve
  bounded/unbounded deny-glob scan-depth semantics.
- `should_require_platform_sandbox(...)` is re-exported from the existing core
  sandbox-tag implementation under the `codex-sandboxing` package path.

Evidence:

- Existing Rust-derived tests cover this behavior in
  `tests/test_core_sandbox_tags.py`, `tests/test_core_state_turn.py`,
  `tests/test_core_handler_utils.py`, and `tests/test_core_tool_runtimes.py`.

Validation:

- Actual pytest validation deferred by the crate automation rule until
  `codex-sandboxing` functional code is complete.
