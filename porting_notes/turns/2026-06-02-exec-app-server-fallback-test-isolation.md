# 2026-06-02: exec app-server fallback test isolation

## Upstream slice

- Graph query for the common exec path identified `codex/codex-rs/exec/src/lib.rs` nodes such as `run_main`, `run_exec_session`, `resolve_prompt`, and the exec request/session configuration helpers.
- Rust `exec/src/lib.rs` confirms that non-interactive `codex exec` prepares config and request state before starting the runtime path, with app-server/remote startup behavior separated from prompt/config preparation.

## Python slice

- `pycodex.cli.parser._run_noninteractive_exec` now has two test-covered runtime branches:
  - local HTTP exec when `PYCODEX_EXEC_LOCAL_HTTP` or API-key based local execution is enabled;
  - remote/local app-server fallback when local HTTP exec is disabled.
- The app-server fallback tests now explicitly set `PYCODEX_EXEC_LOCAL_HTTP=0`, so host `OPENAI_API_KEY`/`CODEX_API_KEY` values cannot accidentally route the tests into the local HTTP path.
- The `exec-server` conflict assertion was aligned with the current parser-layer error path, which reports the `--listen`/`--remote` conflict before `_run_exec_server` executes.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_missing_prints_start_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_state_not_running_prints_state_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_state_is_invalid_prints_state_read_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_state_is_unreadable_prints_state_read_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_connection_is_refused_prints_refused_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_generic_connect_error_prints_generic_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_permission_is_denied_prints_permission_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_connection_timed_out_prints_timed_out_hint tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_state_running_but_socket_missing_warns_stale_state tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_server_rejects_listen_with_remote` passes.

## Known gaps

- Local app-server daemon and remote-control implementation remain compatibility-shim level and are still outside the active core runtime target.
- The full CLI parser suite still contains failures in deferred areas such as cloud, doctor, plugin, remote-control, MCP/app-server details, and desktop app launch behavior.
