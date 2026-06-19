# linux_run_main.rs alignment status

Rust module: `codex/codex-rs/linux-sandbox/src/linux_run_main.rs`

Python module: `pycodex/linux_sandbox/linux_run_main.py`

Status: `complete_candidate`

Implemented behavior:

- `LandlockCommand`-style CLI parsing for `--sandbox-policy-cwd`,
  `--command-cwd`, `--permission-profile`, `--use-legacy-landlock`,
  `--apply-seccomp-then-exec`, `--allow-network-for-proxy`,
  `--proxy-route-spec`, `--no-proc`, `--`, and trailing command args.
- Permission profile JSON parsing and runtime filesystem/network permission
  resolution.
- Inner seccomp stage validation, legacy Landlock/direct-runtime enforcement
  compatibility checks, bwrap network-mode selection, and full-disk direct exec
  shortcut planning.
- Inner seccomp helper argv construction, bwrap argv construction wrapper, and
  `codex-linux-sandbox` argv0 insertion/fallback behavior.
- Proc-mount failure classification and `run_main()` dispatch to injectable
  bwrap, proxy-route, Landlock, and exec runtime boundaries.

Validation:

- `python -m py_compile pycodex/linux_sandbox/linux_run_main.py tests/test_linux_sandbox_linux_run_main_rs.py`
  passed.
- `python -m pytest tests/test_linux_sandbox_linux_run_main_rs.py -q`
  passed (`14 passed`).
- Crate-focused `python -m pytest @files -q` over `tests/test_linux_sandbox_*.py`
  was attempted after all functional modules were present: `77 passed, 12
  failed`. Failures are currently in sibling modules `bundled_bwrap`, `bwrap`,
  and `proxy_routing`, so crate completion remains validation-pending.
