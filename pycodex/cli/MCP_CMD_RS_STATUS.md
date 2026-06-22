# codex-cli src/mcp_cmd.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/mcp_cmd.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/mcp_cmd.rs` |
| Python parser/runner module | `pycodex/cli/parser.py` |
| Python tests | `tests/test_cli_parser.py` |
| Status | `complete_candidate` |

`src/mcp_cmd.rs` owns the CLI-facing `codex mcp` command shell: `list`,
`get`, `add`, `remove`, `login`, and `logout`, along with MCP add transport
argument parsing, `KEY=VALUE` env parsing, server-name validation, and stable
user-facing command messages.

MCP runtime discovery, OAuth execution, token storage, and effective server
management delegate to `codex-mcp`, `codex-core`, and RMCP client crates. Those
extension/runtime internals are outside the active core CLI priority here, so
Python keeps this module as a compatibility shim.

## Completed Behavior Areas

- `mcp list`, `get`, `add`, `remove`, `login`, and `logout` parser surfaces are
  represented.
- `mcp add` supports mutually exclusive `--url` and stdio command modes.
- `mcp add --env KEY=VALUE` now mirrors Rust `parse_env_pair`: key is trimmed,
  empty values are allowed, and missing `=` or empty keys are rejected.
- Add/remove server names now mirror Rust `validate_server_name`: non-empty
  ASCII letters, digits, `-`, and `_` only.
- Local config add/list/get/remove compatibility behavior is represented in
  `pycodex/cli/parser.py`.

## Rust Test Inventory

The Rust module currently has no local `#[cfg(test)]` tests, so parity evidence
comes from source-level behavior contracts:

- `McpCli` and `McpSubcommand`
- `AddMcpTransportArgs`, `AddMcpStdioArgs`, `AddMcpStreamableHttpArgs`
- `parse_env_pair`
- `validate_server_name`
- list/get/add/remove/login/logout user-facing command branches

Python coverage and evidence:

- `tests/test_cli_parser.py::CliParserTests::test_parse_mcp_list_json`
- `tests/test_cli_parser.py::CliParserTests::test_parse_mcp_get_allows_json`
- `tests/test_cli_parser.py::CliParserTests::test_parse_mcp_add_supports_env_in_command_mode`
- `tests/test_cli_parser.py::CliParserTests::test_parse_mcp_add_url_and_command_modes`
- `tests/test_cli_parser.py::CliParserTests::test_mcp_add_requires_url_or_command`
- `tests/test_cli_parser.py::CliParserTests::test_mcp_env_pair_matches_rust`
- `tests/test_cli_parser.py::CliParserTests::test_mcp_server_name_validation_matches_rust`

## Remaining Gaps

- No known module-owned parser/helper gaps remain.
- Full MCP runtime discovery, OAuth login/logout execution, token deletion, and
  effective server auth status remain extension/runtime behavior outside this
  `codex-cli` module.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
