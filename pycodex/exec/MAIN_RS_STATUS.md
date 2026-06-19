# codex-exec src/main.rs status

Status: complete_candidate

Rust crate: `codex-exec`
Rust module: `codex/codex-rs/exec/src/main.rs`
Rust tests: `codex/codex-rs/exec/src/main_tests.rs`
Python module: `pycodex/exec/cli.py`
Python tests: `tests/test_exec_cli.py`

## Behavior contract

Rust `src/main.rs` owns the `codex-exec` binary wrapper:

- `TopCli` parses root-level `CliConfigOverrides` alongside the inner
  `codex_exec::Cli`;
- root config overrides are prepended into the inner CLI before `run_main`;
- global exec flags remain accepted after the `resume` subcommand in the same
  way the inner CLI expects;
- `arg0_dispatch_or_else` routes `codex-linux-sandbox` arg0 invocations to the
  sandbox executable path instead of normal `codex exec`.

## Python alignment

`pycodex.exec.cli.parse_exec_args(..., root_config_overrides=...)` mirrors the
tested `TopCli` merge behavior by seeding root overrides before exec-specific
`-c/--config` options. `tests/test_exec_cli.py` covers root override ordering
and the Rust `main_tests.rs` resume/global-flag prompt shape.

`pycodex.exec.cli.exec_main_dispatch_plan(...)` mirrors the `src/main.rs`
binary wrapper decision: normal `codex-exec` argv is parsed into the inner
exec CLI, while argv0 named `codex-linux-sandbox` is routed to a sandbox branch
without parsing normal exec options. The actual linux sandbox runtime remains
owned by the arg0/linux-sandbox crate boundary; this module claims the exec
binary's branch selection and `TopCli` merge contract.

## Evidence

- Rust source inspected: `codex/codex-rs/exec/src/main.rs`.
- Rust tests inspected: `codex/codex-rs/exec/src/main_tests.rs`.
- Python implementation inspected: `pycodex/exec/cli.py`.
- Python tests inspected: `tests/test_exec_cli.py`.
- Validation deferred by current crate automation rule until `codex-exec`
  functional module code is complete.
