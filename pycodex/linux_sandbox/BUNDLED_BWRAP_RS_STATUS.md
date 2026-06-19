# codex-linux-sandbox src/bundled_bwrap.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/bundled_bwrap.rs`

Python module: `pycodex/linux_sandbox/bundled_bwrap.py`

Status: `complete_candidate`

Implemented behavior:

- Package-layout bundled `codex-resources/bwrap` discovery through
  `InstallContext.bundled_resource("bwrap")`.
- Legacy candidate ordering next to the current executable, next to the npm
  target/vendor directory, adjacent dev `bwrap`, and Bazel runfiles candidate.
- Executable-file filtering through file type plus executable permission bits.
  On Windows, regular files are accepted because Unix executable mode bits are
  not a reliable filesystem signal for this Linux-only helper test surface.
- `CODEX_BWRAP_SHA256` parsing, null digest opt-out, hex formatting, and digest
  verification.
- `BundledBwrapLauncher.exec()` verifies digest, preserves file descriptors,
  validates argv, and models the `/proc/self/fd/<fd>` exec boundary.

Runtime boundary:

- Tests do not execute `BundledBwrapLauncher.exec()` because it replaces the
  current process via `execv`.

Validation:

- `python -m py_compile pycodex/linux_sandbox/bundled_bwrap.py tests/test_linux_sandbox_bundled_bwrap_rs.py`
  (passed)
- `python -m pytest tests/test_linux_sandbox_bundled_bwrap_rs.py -q --tb=short`
  (passed: `9 passed`)

Crate-level validation remains pending on sibling module failures.
