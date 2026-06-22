# environment_toml.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/environment_toml.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `ENVIRONMENTS_TOML_FILE`
- `MAX_ENVIRONMENT_ID_LEN`
- `EnvironmentsToml`
- `EnvironmentToml`
- `TomlEnvironmentProvider::{new, new_with_config_dir, snapshot}`
- `parse_environment_toml`
- `normalize_stdio_cwd`
- `normalize_default_environment_id`
- `validate_environment_id`
- `validate_websocket_url`
- `load_environments_toml`
- `environment_provider_from_codex_home`

## Python evidence

- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_includes_local_and_adds_configured_environments`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_default_selection_cases`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_invalid_environments`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_resolves_relative_stdio_cwd_from_config_dir`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_parses_configured_transport_timeouts`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_relative_stdio_cwd_without_config_dir`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_duplicate_overlong_and_unknown_default`
- `tests/test_exec_server_environment_toml_rs.py::test_load_environments_toml_reads_root_environment_list`
- `tests/test_exec_server_environment_toml_rs.py::test_load_environments_toml_rejects_unknown_fields`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_rejects_malformed_websocket_url`
- `tests/test_exec_server_environment_toml_rs.py::test_environment_provider_from_codex_home_uses_file_or_default`
- `tests/test_exec_server_environment_toml_rs.py::test_toml_provider_default_timeout_values`

## Notes

Python uses standard-library `tomllib` to avoid adding dependencies. The Rust
websocket URL validator uses Tungstenite; Python keeps a dependency-light
approximation that preserves scheme/trimming/malformed-empty-url behavior and
the user-facing error prefix covered by tests.

This module constructs remote environment transport params but does not
implement the concrete remote client or transport runtime.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py -q --tb=short
29 passed

python -m pytest tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short
41 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_environment_rs.py tests\test_exec_server_environment_provider_rs.py tests\test_exec_server_environment_toml_rs.py
passed
```
