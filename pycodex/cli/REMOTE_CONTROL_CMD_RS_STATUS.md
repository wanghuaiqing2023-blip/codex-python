# codex-cli src/remote_control_cmd.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/remote_control_cmd.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/remote_control_cmd.rs` |
| Python parser/runner module | `pycodex/cli/parser.py` |
| Python tests | `tests/test_cli_parser.py` |
| Status | `complete_candidate` |

`src/remote_control_cmd.rs` owns the CLI-facing `codex remote-control` shell:
foreground start, daemon start, daemon stop, `--json` output, human status
messages, and Ctrl-C foreground hinting.

The real foreground app-server process, Unix socket readiness loop, daemon
lifecycle execution, and remote-control transport internals are app-server
crate behavior. Python keeps this module as a compatibility shim backed by
local state and stable output formatting.

## Completed Behavior Areas

- `remote-control`, `remote-control start`, and `remote-control stop` parser
  surfaces are represented.
- `--json` is accepted globally before or after subcommands.
- Human start messages mirror Rust connected, connecting, errored, and disabled
  wording with the server name.
- Foreground output includes `Press Ctrl-C to stop.`; daemon output does not.
- Start/stop JSON payloads distinguish foreground/daemon and stopped/notRunning
  states through the Python compatibility runner.

## Rust Test Inventory

The Rust module contains local tests for:

- `remote_control_human_start_messages_use_server_name`
- `remote_control_human_lines_include_foreground_stop_hint_only`
- `daemon_app_server_human_lines_include_path_and_version`
- `remote_control_json_output_marks_foreground_or_daemon`
- `remote_control_daemon_json_rejects_unstartable_status`
- foreground wait/stop task behavior

They are represented by:

- `tests/test_cli_parser.py::CliParserTests::test_remote_control_human_start_messages_match_rust`
- `tests/test_cli_parser.py::CliParserTests::test_remote_control_human_lines_match_rust_foreground_hint`
- `tests/test_cli_parser.py::CliParserTests::test_main_remote_control_start_and_stop_json`
- `tests/test_cli_parser.py::CliParserTests::test_main_remote_control_stop_when_not_running`
- `tests/test_cli_parser.py::CliParserTests::test_main_remote_control_stop_not_running_json`

## Remaining Gaps

- No known module-owned CLI output/parser gaps remain.
- Foreground async app-server task scheduling, socket readiness retries, daemon
  lifecycle commands, and transport internals remain app-server crate behavior
  and are not claimed by this `codex-cli` module.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
