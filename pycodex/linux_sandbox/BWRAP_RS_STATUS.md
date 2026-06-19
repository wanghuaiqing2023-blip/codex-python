# linux-sandbox/src/bwrap.rs

Status: `complete_candidate`

Python module:

- `pycodex/linux_sandbox/bwrap.py`

Implemented Rust anchors:

- `BwrapOptions` defaults, including uncapped unreadable glob expansion depth.
- `BwrapNetworkMode` and `should_unshare_network()`.
- `BwrapArgs`, `SyntheticMountTargetKind`, `SyntheticMountTarget`, and
  `ProtectedCreateTarget` data-model behavior.
- `create_bwrap_command_args()` fast path for full disk write/full network.
- Full-filesystem bwrap wrapping when network isolation/proxy-only mode is
  requested.
- `split_pattern_for_ripgrep()` root-prefix rejection and unclosed `[` escape.
- Initial `create_filesystem_args()` overlay planning for full-read baselines,
  scoped readable roots, existing writable roots, missing writable root skips,
  missing read-only subpath empty-file binds, transient empty metadata files,
  protected metadata directory masks, unreadable root masks, and unreadable glob
  match masks.
- Nested carveout ordering for unreadable parent directories with writable
  descendants and for read-only parent paths followed by nested writable binds.
- Root-read file and directory carveout masks.
- Missing child `.git` protected-create target behavior under a parent repo.
- Unreadable glob expansion with configured max depth and canonical targets for
  symlink matches.
- Symlinked writable root remapping to real mount targets.
- Fail-closed handling for protected read-only symlinked metadata paths and
  deny-read paths that cross writable symlinks.
- Missing user project-root subpath rule enforcement.
- Split-policy writable-file and nested writable-root re-enable ordering under
  unreadable parents.
- Symlinked missing-child `.git` under parent repo uses the effective mount root.
- Missing protected metadata project-root carveouts use metadata path masks.
- Minimal/platform-default read policies include existing Linux platform roots.

Validation:

- `python -m py_compile pycodex/linux_sandbox/bwrap.py tests/test_linux_sandbox_bwrap_rs.py`
