# codex-sandboxing/src/landlock.rs Status

Status: complete_candidate

Rust source:

```text
codex/codex-rs/sandboxing/src/landlock.rs
codex/codex-rs/sandboxing/src/landlock_tests.rs
```

Python mapping:

```text
pycodex/sandboxing/landlock.py
pycodex/linux_sandbox/__init__.py
tests/test_core_spawn_landlock.py
```

Aligned behavior:

- `CODEX_LINUX_SANDBOX_ARG0` is exported at the crate-aligned package path.
- `allow_network_for_proxy(...)` mirrors Rust's managed-network boolean
  forwarding rule.
- `create_landlock_command_args(...)` mirrors Rust's private helper for
  `--sandbox-policy-cwd`, `--command-cwd`, optional
  `--use-legacy-landlock`, optional `--allow-network-for-proxy`, and `--`
  command separator ordering.
- `create_landlock_command_args_for_permission_profile(...)` mirrors Rust's
  public permission-profile helper, including compact JSON profile emission
  before feature flags.
- `linux_sandbox_arg0(...)` preserves the helper basename aliasing used by the
  manager transform path.

Evidence:

- Existing Rust-derived coverage lives in `tests/test_core_spawn_landlock.py`
  for `permission_profile_flag_is_included`,
  `legacy_landlock_flag_is_included_when_requested`,
  `proxy_flag_is_included_when_requested`, and
  `proxy_network_requires_managed_requirements`.

Validation:

- Actual pytest validation deferred by the crate automation rule until
  `codex-sandboxing` functional code is complete.
