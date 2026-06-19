# pycodex.linux_sandbox

Canonical Python package for the Rust workspace crate:

- Rust crate: `codex/codex-rs/linux-sandbox`
- Python package: `pycodex/linux_sandbox`

The implementation currently includes crate-root `src/lib.rs` delegation
behavior, the binary `src/main.rs` delegation surface, Bazel runfiles lookup
for the sandbox `bwrap` helper, bundled bubblewrap discovery, low-level exec
helpers, bubblewrap launcher selection helpers, Landlock/seccomp decision
helpers, managed proxy routing helpers, bubblewrap argument construction, and
the `linux_run_main` helper CLI/dispatch planning surface. Native Linux syscall
and `execvp` behavior remains an explicit runtime boundary.

Module map:

- `codex/codex-rs/linux-sandbox/src/lib.rs` ->
  `pycodex/linux_sandbox/__init__.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/main.rs` ->
  `pycodex/linux_sandbox/__main__.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/bazel_bwrap.rs` ->
  `pycodex/linux_sandbox/bazel_bwrap.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/bundled_bwrap.rs` ->
  `pycodex/linux_sandbox/bundled_bwrap.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/exec_util.rs` ->
  `pycodex/linux_sandbox/exec_util.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/launcher.rs` ->
  `pycodex/linux_sandbox/launcher.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/landlock.rs` ->
  `pycodex/linux_sandbox/landlock.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/proxy_routing.rs` ->
  `pycodex/linux_sandbox/proxy_routing.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/bwrap.rs` ->
  `pycodex/linux_sandbox/bwrap.py` (`complete_candidate`)
- `codex/codex-rs/linux-sandbox/src/linux_run_main.rs` ->
  `pycodex/linux_sandbox/linux_run_main.py` (`complete_candidate`)

Crate-level validation status is tracked in `TEST_ALIGNMENT.md`.
