# codex-config src/mcp_types.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/mcp_types.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/mcp_types.rs` |
| Python module | `pycodex/config/mcp_types.py` |
| Python tests | `tests/test_config_mcp_types.py` |
| Status | `complete_candidate` |

`src/mcp_types.rs` owns MCP server configuration data shapes and validation: stdio and streamable-http transport selection, env var source metadata, timeout fields, tool approval config, OAuth config, tool filters, and disabled-reason display. MCP runtime startup, OAuth flows, tool registration, and transport execution remain outside this module boundary.

## Covered Behavior Areas

- `DEFAULT_MCP_SERVER_ENVIRONMENT_ID` defaults omitted `environment_id` to `local`.
- `AppToolApproval` parses `auto`, `prompt`, and `approve`.
- `McpServerDisabledReason` displays `unknown` and `requirements (<source>)`.
- `McpServerEnvVar` accepts legacy string entries and `{ name, source }` tables.
- Env var sources validate only `local` and `remote`; unknown sources are rejected.
- Stdio transport parses `command`, `args`, `env`, `env_vars`, and `cwd`.
- Streamable-http transport parses `url`, bearer token env var, static headers, and env-sourced headers.
- Transport-specific unsupported fields produce targeted errors.
- Remote stdio servers require an absolute `cwd`.
- `startup_timeout_sec` takes precedence over `startup_timeout_ms`.
- Enabled/required/parallel flags, tool timeouts, tool allow/deny filters, default and per-tool approval mode, OAuth client id, scopes, and OAuth resource are preserved.
- Compatibility field behavior for unknown server fields is covered by Python tests.

## Rust Test Inventory

Representative Rust tests covered in Python include:

- `deserialize_stdio_command_server_config`
- `deserialize_stdio_command_server_config_with_arg_with_args_and_env`
- `deserialize_stdio_command_server_config_with_cwd`
- `deserialize_stdio_command_server_config_with_env_var_sources`
- `deserialize_stdio_command_server_config_rejects_unknown_env_var_source`
- `deserialize_remote_stdio_server_requires_absolute_cwd`
- `deserialize_remote_stdio_server_accepts_absolute_cwd`
- `deserialize_disabled_server_config`
- `deserialize_required_server_config`
- `deserialize_streamable_http_server_config`
- `deserialize_streamable_http_server_config_with_env_var`
- `deserialize_streamable_http_server_config_with_headers`
- `deserialize_streamable_http_server_config_with_oauth_resource`
- `deserialize_streamable_http_server_config_with_oauth_client_id`
- `deserialize_rejects_command_and_url`
- `deserialize_rejects_env_for_http`
- `deserialize_rejects_headers_for_stdio`
- `deserialize_rejects_bearer_token`

Additional Python coverage records timeout precedence, tool filters, per-tool approval config, `is_local_environment`, `oauth_client_id`, and disabled-reason display.

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
