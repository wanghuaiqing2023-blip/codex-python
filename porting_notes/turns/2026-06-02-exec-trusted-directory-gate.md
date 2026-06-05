# 2026-06-02: exec trusted-directory gate in CLI runtime path

## Upstream slice

- Knowledge-graph lookup for the exec path identified `codex/codex-rs/exec/src/lib.rs` functions including `run_main`, `run_exec_session`, and the initial operation/request setup helpers.
- Rust `run_exec_session` resolves the initial operation and then enforces the trusted-directory gate before starting the app-server runtime:
  - block when the selected cwd is outside a git repository;
  - allow when `--skip-git-repo-check` is set;
  - allow when `--dangerously-bypass-approvals-and-sandbox` is set.

## Python slice

- `pycodex.cli.parser._run_noninteractive_exec` now calls `ensure_exec_trusted_directory(exec_trusted_directory_check(...))` after config/prompt preparation and before entering either local HTTP exec or app-server fallback runtime.
- This moves the existing Python parity helper from an isolated planning API into the user-facing `codex exec` runtime path.
- `tests.test_cli_parser` now covers that untrusted cwd blocks before runtime startup, and a local HTTP exec-policy test marks its temporary project as a git repository so it remains aligned with the Rust gate.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_enforces_trusted_directory_gate_before_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_loads_default_execpolicy_rules tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_prepares_noninteractive_plan tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_trusted_directory_check_matches_upstream_gate`
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_enforces_trusted_directory_gate_before_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_loads_default_execpolicy_rules tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_missing_prints_start_hint tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_groups_same_turn_tool_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_session_accepts_write_stdin`

Both targeted runs pass.

## Known gaps

- This only wires the trusted-directory gate into the non-interactive `exec` path. Interactive TUI startup remains outside the current Python core target.
- Full app-server daemon behavior remains shim-level; local HTTP exec continues to be the main in-process Python runtime path.
