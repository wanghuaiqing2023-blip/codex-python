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
and `execvp` behavior remains an explicit runtime boundary. The package has a
`unittest` fallback validation entry for environments where pytest is not
installed; current crate completion evidence is tracked in `TEST_ALIGNMENT.md`.
On 2026-06-21, the fallback direct validation entrypoint and unittest wrapper
both exited with code 0 in the current workspace, covering the pure Python
Rust-derived module tests while native Linux integration suites remain a
runtime boundary.

Module map:

- `codex/codex-rs/linux-sandbox/src/lib.rs` ->
  `pycodex/linux_sandbox/__init__.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/main.rs` ->
  `pycodex/linux_sandbox/__main__.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/bazel_bwrap.rs` ->
  `pycodex/linux_sandbox/bazel_bwrap.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/bundled_bwrap.rs` ->
  `pycodex/linux_sandbox/bundled_bwrap.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/exec_util.rs` ->
  `pycodex/linux_sandbox/exec_util.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/launcher.rs` ->
  `pycodex/linux_sandbox/launcher.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/landlock.rs` ->
  `pycodex/linux_sandbox/landlock.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/proxy_routing.rs` ->
  `pycodex/linux_sandbox/proxy_routing.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/bwrap.rs` ->
  `pycodex/linux_sandbox/bwrap.py` (`complete`)
- `codex/codex-rs/linux-sandbox/src/linux_run_main.rs` ->
  `pycodex/linux_sandbox/linux_run_main.py` (`complete`)

Crate-level validation status is tracked in `TEST_ALIGNMENT.md`.
