# codex-sandboxing src/seatbelt.rs Status

Rust crate: `codex-sandboxing`  
Rust module: `src/seatbelt.rs`  
Python module: `pycodex/sandboxing/seatbelt.py`

## Status

`complete_candidate`

## Implemented Contract

- macOS `sandbox-exec` executable constant and argv shape: `-p <policy>`,
  `-DKEY=value` definitions, `--`, then child command.
- Proxy environment inspection for loopback proxy ports, including default
  scheme ports and lowercase/uppercase proxy aliases.
- Dynamic network policy generation for restricted proxy routing, full network,
  managed-network fail-closed behavior, local binding, and DNS carveouts.
- Unix-domain-socket allowlist and allow-all policy generation, including stable
  `UNIX_SOCKET_PATH_N` definition names.
- Split filesystem read/write Seatbelt policy construction using readable roots,
  writable roots, read-only subpaths, unreadable roots, and protected metadata
  name regex carveouts.
- Unreadable glob translation to anchored Seatbelt regex deny rules for
  `file-read*` and `file-write-unlink`.
- Legacy `SandboxPolicy` adapter into `FileSystemSandboxPolicy` plus
  `NetworkSandboxPolicy`.

## Evidence

- Rust source: `codex/codex-rs/sandboxing/src/seatbelt.rs`
- Rust tests: `codex/codex-rs/sandboxing/src/seatbelt_tests.rs`
- Python syntax/import smoke:
  - `python -m py_compile pycodex/sandboxing/seatbelt.py pycodex/sandboxing/__init__.py`
  - Minimal import/semantic smoke for proxy ports, glob regex, Unix socket
    policy, and argv shape.

## Deferred

Actual pytest execution is deferred by the crate automation rule until the crate
functional code is complete.

`src/manager.rs` still needs a separate module pass to replace its macOS
Seatbelt placeholder with this module's `create_seatbelt_command_args` helper.
That integration is intentionally not included in this module-scoped pass.
