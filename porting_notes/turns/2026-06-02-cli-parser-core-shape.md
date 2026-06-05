# 2026-06-02 - CLI parser core shape cleanup

## Scope

- Core path: CLI command parsing around common runtime entrypoints.
- Upstream graph slice: `codex/codex-rs/cli/src/main.rs` nodes for `MultitoolCli`, `AppServerCommand`, `DebugCommand`, and `DebugAppServerCommand`.
- Extension/runtime depth intentionally deferred: no app-server daemon, MCP, plugin marketplace, or websocket runtime implementation was added.

## Changes

- Preserved root `app-server` websocket/auth flags in parsed `command_args` while still validating the stripped subcommand payload.
- Adjusted root websocket auth validation to expose the Rust-like `--ws-auth` requirement as a clear user-facing error.
- Matched `debug app-server` no-payload behavior to the only supported debug subcommand shape, requiring `send-message-v2` user payload.
- Kept `apply` strict about requiring a `TASK_ID` outside help mode.

## Validation

- Passed:
  - `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_parse_debug_app_server_send_message_requires_message tests.test_cli_parser.TopLevelCliParserTests.test_parse_debug_app_server_send_message_accepts_payload tests.test_cli_parser.TopLevelCliParserTests.test_parse_app_server_rejects_websocket_auth_flags_without_mode tests.test_cli_parser.TopLevelCliParserTests.test_parse_app_server_root_websocket_auth_combinations_are_valid tests.test_cli_parser.TopLevelCliParserTests.test_parse_app_server_root_options tests.test_cli_parser.TopLevelCliParserTests.test_parse_app_server_proxy_accepts_optional_socket`
  - `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_parse_apply_requires_task_id tests.test_cli_parser.TopLevelCliParserTests.test_parse_debug_app_server_send_message_requires_message tests.test_cli_parser.TopLevelCliParserTests.test_parse_app_server_root_websocket_auth_combinations_are_valid tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec`

## Known remaining parser-suite failures

Full `tests.test_cli_parser` currently still has failures in wider or deferred areas:

- desktop app launcher behavior on Windows;
- cloud fallback/help behavior;
- doctor/update checks;
- remote-control JSON/start-stop output;
- MCP server runtime argument rejection;
- responses-api-proxy header ordering.

These should be handled as separate graph-selected slices only when they unblock the common `exec -> context -> model request -> stream handling -> tool dispatch -> final answer` path.
