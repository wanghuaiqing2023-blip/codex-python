# codex-linux-sandbox test alignment

Rust crate: `codex-linux-sandbox`

Python package: `pycodex/linux_sandbox`

Status: `partial`

Module mapping:

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

Rust behavior prepared in `tests/test_linux_sandbox_lib_rs.py`:

- non-Linux `run_main()` unsupported-target error
- Linux `run_main()` delegation to sibling `linux_run_main.run_main`

Rust behavior prepared in `tests/test_linux_sandbox_main_rs.py`:

- binary `main()` direct delegation to crate-root `run_main()`

Rust behavior prepared in `tests/test_linux_sandbox_bazel_bwrap_rs.py`:

- release/non-debug `candidate()` returns no Bazel bwrap candidate
- Bazel package and runfiles environment gates
- absolute `CARGO_BIN_EXE_bwrap` return
- `RUNFILES_DIR`/`TEST_SRCDIR` runfile resolution with `TEST_WORKSPACE`
- `RUNFILES_MANIFEST_FILE` key/value resolution

Rust behavior prepared in `tests/test_linux_sandbox_exec_util_rs.py`:

- `argv_to_cstrings()` conversion to CString-compatible byte payloads
- interior NUL rejection
- `make_files_inheritable()` clearing close-on-exec behavior for file objects
- raw fd handling for preserved descriptors

Rust behavior prepared in `tests/test_linux_sandbox_bundled_bwrap_rs.py`:

- package-layout `codex-resources/bwrap` discovery through `InstallContext`
- legacy standalone, npm target/vendor, and adjacent dev `bwrap` discovery
- missing expected digest skips verification
- matching digest verifies; mismatched digest fails
- SHA256 hex parsing and null digest opt-out
- executable-file filtering remains strict on POSIX and accepts regular files
  on Windows where Unix mode bits are not reliable

Rust behavior prepared in `tests/test_linux_sandbox_launcher_rs.py`:

- system bwrap launcher accepted when `--perms` is supported
- `--argv0` capability is preserved but not required
- system bwrap without `--perms` is ignored
- missing system bwrap path is ignored
- unavailable/bundled launcher path defaults to argv0 support

Rust behavior prepared in `tests/test_linux_sandbox_landlock_rs.py`:

- managed network enforces seccomp even for full-network policy
- full network without managed proxy skips network seccomp
- restricted network always installs network seccomp
- managed proxy routes use proxy-routed seccomp mode
- restricted network without proxy routing uses restricted mode
- current-thread application plan invokes explicit OS-boundary hooks

Rust behavior prepared in `tests/test_linux_sandbox_proxy_routing_rs.py`:

- proxy env keys are recognized case-insensitively
- loopback proxy endpoints are parsed and non-loopback endpoints ignored
- route planning includes only valid loopback endpoints
- proxy URLs rewrite to local loopback ports
- proxy route spec serialization omits original proxy URLs
- proxy socket dir owner pid parsing and stale cleanup
- pid liveness overflow during platform pid conversion is treated as a dead pid

Rust behavior prepared in `tests/test_linux_sandbox_bwrap_rs.py`:

- `BwrapOptions::default()` leaves unreadable glob scanning uncapped
- `BwrapNetworkMode::should_unshare_network()` for full, isolated, and proxy modes
- full disk write/full network returns the original command unwrapped
- full disk write/proxy-only keeps full filesystem access but adds bwrap network unshare
- `SyntheticMountTarget` and `ProtectedCreateTarget` constructor/accessor behavior
- ripgrep glob splitting rejects root-prefix scans and escapes unclosed classes
- full disk write with unreadable glob still wraps and masks matched files
- missing read-only subpaths use empty-file bind-data synthetic targets
- transient empty metadata files are preserved and not cleaned up after bwrap
- missing writable roots are skipped
- restricted read-only policies use scoped read roots
- `/dev` is mounted before explicit writable `/dev` binds
- unreadable parent directories recreate writable child mount targets before
  remounting read-only, then rebind the writable child
- unreadable carveouts nested under writable roots are re-applied after the
  writable root bind
- read-only parent subpaths are applied before nested writable subpath binds
- missing child `.git` under a parent repo uses protected-create cleanup instead
  of shadowing parent repo discovery
- root-read directory and file carveouts are masked
- unreadable glob expansion honors configured max depth and includes canonical
  targets for symlink matches
- symlinked writable roots bind real targets and remap carveouts
- protected metadata symlinks and deny-read symlink escapes fail closed
- missing user project-root subpath rules remain enforced
- writable file and nested writable root split-policy combinations are reopened
  after unreadable parent masks
- symlinked missing child `.git` under a parent repo uses the effective mount root
- missing protected metadata project-root carveouts use metadata path masks
- minimal/platform-default read policies include existing Linux platform roots

Rust behavior prepared in `tests/test_linux_sandbox_linux_run_main_rs.py`:

- `LandlockCommand` CLI parsing for required, hidden, optional, and trailing
  command arguments
- missing command and missing/invalid permission profile validation
- `--apply-seccomp-then-exec` incompatibility with `--use-legacy-landlock`
- `/proc` mount failure stderr classification
- bwrap network-mode selection, including proxy-only precedence over full
  network policy
- inner helper `--argv0` insertion and fallback command rewriting
- inner seccomp command construction and permission-profile JSON serialization
- legacy Landlock rejection for direct runtime enforcement policies
- bwrap outer-stage planning and `run_main()` delegation through injected
  bwrap/exec runtime hooks

Validation:

- `python -m py_compile pycodex/linux_sandbox/__init__.py tests/test_linux_sandbox_lib_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/__main__.py tests/test_linux_sandbox_main_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/bazel_bwrap.py tests/test_linux_sandbox_bazel_bwrap_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/exec_util.py tests/test_linux_sandbox_exec_util_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/bundled_bwrap.py tests/test_linux_sandbox_bundled_bwrap_rs.py`
  (passed)
- `python -m pytest tests/test_linux_sandbox_bundled_bwrap_rs.py -q --tb=short`
  (passed: `9 passed`)
- `python -m py_compile pycodex/linux_sandbox/launcher.py tests/test_linux_sandbox_launcher_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/landlock.py tests/test_linux_sandbox_landlock_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/proxy_routing.py tests/test_linux_sandbox_proxy_routing_rs.py`
  (passed)
- `python -c "from pycodex.linux_sandbox.proxy_routing import is_pid_alive; print(is_pid_alive(2**32-1))"`
  (passed: `False`)
- `python -m py_compile pycodex/linux_sandbox/bwrap.py tests/test_linux_sandbox_bwrap_rs.py`
  (passed)
- `python -m py_compile pycodex/linux_sandbox/linux_run_main.py tests/test_linux_sandbox_linux_run_main_rs.py`
  (passed)
- `python -m pytest tests/test_linux_sandbox_linux_run_main_rs.py -q`
  (passed: `14 passed`)
- `python -m pytest @files -q` over expanded `tests/test_linux_sandbox_*.py`
  (attempted after all functional modules were present: `77 passed, 12 failed`;
  failures were in sibling modules `bundled_bwrap`, `bwrap`, and
  `proxy_routing`; `bundled_bwrap` focused validation now passes, and the
  observed `proxy_routing` overflow path has since been patched, but full crate
  pytest has not yet been rerun to completion)

Deferred validation:

- Resolve sibling-module focused test failures before promoting
  `codex-linux-sandbox` from `partial` to `complete`.
- Rust integration suites under `codex/codex-rs/linux-sandbox/tests/`.
