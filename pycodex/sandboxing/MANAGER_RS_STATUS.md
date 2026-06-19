# codex-sandboxing/src/manager.rs Status

Status: complete_candidate

Rust source:

```text
codex/codex-rs/sandboxing/src/manager.rs
codex/codex-rs/sandboxing/src/manager_tests.rs
```

Python mapping:

```text
pycodex/sandboxing/manager.py
pycodex/core/sandboxing.py
pycodex/core/sandbox_tags.py
pycodex/linux_sandbox/__init__.py
pycodex/protocol/models.py
```

Aligned behavior:

- `SandboxType`, platform sandbox tag selection, and `SandboxablePreference`
  mirror Rust manager selection semantics through the existing
  `pycodex.core.sandbox_tags` helpers.
- `SandboxCommand`, `SandboxTransformRequest`, `SandboxExecRequest`, and
  `SandboxManager.transform(...)` preserve the Rust request/response shape for
  no-sandbox, macOS Seatbelt, Linux seccomp helper, and Windows restricted-token
  projections.
- Additional permission profiles are merged into the effective permission
  profile before runtime policy extraction, preserving denied entries and
  explicit network enable/restrict overrides.
- `compatibility_sandbox_policy_for_permission_profile(...)` is exposed through
  the crate package and delegates to the already ported core compatibility
  projection used by Rust-derived core tests.
- Linux helper argv construction delegates to the existing
  `pycodex.linux_sandbox` landlock helper and preserves the Rust arg0 alias
  rule.
- macOS Seatbelt argv construction delegates to
  `pycodex.sandboxing.seatbelt.create_seatbelt_command_args` and prefixes the
  Rust `/usr/bin/sandbox-exec` executable.
- Linux WSL1/bubblewrap prerequisite checking mirrors Rust manager's
  `ensure_linux_bubblewrap_is_supported` branch.

Compatibility:

- `SeatbeltCommandBuilderUnavailable` remains exported for older Python callers,
  but `SandboxManager.transform(...)` no longer raises it.
- Non-macOS Seatbelt behavior still matches Rust by reporting seatbelt as
  unavailable.

Validation:

- `python -m py_compile pycodex/sandboxing/manager.py pycodex/sandboxing/__init__.py`
- Minimal smoke for Darwin Seatbelt argv shape.
- Minimal smoke for WSL1 bubblewrap guard.
- Crate focused validation after functional completion:
  `python -m pytest tests/test_core_sandboxing.py tests/test_core_spawn_landlock.py tests/test_core_sandbox_tags.py tests/test_protocol_permission_models.py`
  passed with 87 tests.
