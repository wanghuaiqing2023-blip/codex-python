# codex-linux-sandbox src/landlock.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/landlock.rs`

Python module: `pycodex/linux_sandbox/landlock.py`

Status: `complete_candidate`

Implemented behavior:

- `should_install_network_seccomp(...)` mirrors Rust's managed-network and
  restricted-network decision.
- `network_seccomp_mode(...)` mirrors the restricted vs proxy-routed mode
  selection.
- `plan_permission_profile_application(...)` computes the current-thread
  sandbox application plan from `PermissionProfile.to_runtime_permissions()`.
- `apply_permission_profile_to_current_thread(...)` invokes optional hooks for
  `no_new_privs`, network seccomp, and filesystem Landlock application.

Runtime boundary:

- Direct `prctl`, seccomp BPF installation, and Landlock ruleset installation
  are OS syscall boundaries in the Python port. They are exposed as explicit
  hook points rather than executed during tests.

Validation:

- `python -m py_compile pycodex/linux_sandbox/landlock.py tests/test_linux_sandbox_landlock_rs.py`
  (passed)

Focused pytest remains deferred until the remaining linux-sandbox functional
modules are complete.
