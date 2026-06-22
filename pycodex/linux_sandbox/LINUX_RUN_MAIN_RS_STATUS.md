# linux_run_main.rs alignment status

Rust module: `codex/codex-rs/linux-sandbox/src/linux_run_main.rs`

Python module: `pycodex/linux_sandbox/linux_run_main.py`

Status: `complete`

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
- Managed proxy mode fail-closed preflight errors propagate through the
  `plan_linux_run_main()` entry path when proxy environment variables are
  missing or not parseable as loopback endpoints.
- Managed proxy bwrap outer-stage planning accepts an injected prepared route
  spec, passes it to the inner seccomp helper, and keeps bwrap network
  isolation enabled.

Validation:

- `python -m py_compile pycodex/linux_sandbox/linux_run_main.py tests/test_linux_sandbox_linux_run_main_rs.py`
  passed.
- `python -m pytest tests/test_linux_sandbox_linux_run_main_rs.py -q`
  passed (`14 passed`).
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_linux_sandbox_linux_run_main_rs -v`
  passed on 2026-06-20 (`17 tests`).
- 2026-06-20 direct runner over all `tests/test_linux_sandbox_*.py` functions
  and unittest methods passed with `95 passed, 0 failed, 0 unsupported` under
  the available Python 3.11.4 runtime.
- `python -m pytest tests/test_linux_sandbox_linux_run_main_rs.py -q --tb=short`
  passed on 2026-06-20 with `17 passed`.
- Crate-level validation is recorded in `TEST_ALIGNMENT.md`.
