# codex-sandboxing/src/bwrap.rs Status

Status: complete_candidate

Rust source:

```text
codex/codex-rs/sandboxing/src/bwrap.rs
codex/codex-rs/sandboxing/src/bwrap_tests.rs
```

Python mapping:

```text
pycodex/sandboxing/bwrap.py
```

Aligned behavior:

- Bubblewrap warning constants match the Rust user-facing strings.
- `system_bwrap_warning(...)` only warns when the permission profile requires a
  platform sandbox.
- `system_bwrap_warning_for_path(...)` preserves Rust warning precedence:
  WSL1, missing system `bwrap`, user-namespace failure, then no warning.
- `system_bwrap_has_user_namespace_access(...)` runs the same helper probe argv
  shape and treats spawn errors and timeouts as non-warning outcomes.
- `proc_version_indicates_wsl1(...)` mirrors Rust detection for legacy
  `Microsoft` kernels and explicit `WSL1` markers while excluding WSL2/native
  Linux markers.
- `find_system_bwrap_in_search_paths(...)` scans executable `bwrap` candidates
  and skips workspace-local helpers unless the cwd is root.

Validation:

- Actual pytest validation deferred by the crate automation rule until
  `codex-sandboxing` functional code is complete.
