# environment_provider.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/environment_provider.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `EnvironmentProvider`
- `EnvironmentProviderSnapshot`
- `EnvironmentDefault::{Disabled, EnvironmentId}`
- `DefaultEnvironmentProvider::{new, from_env, snapshot_inner}`
- `normalize_exec_server_url`
- `CODEX_EXEC_SERVER_URL_ENV_VAR`
- `LOCAL_ENVIRONMENT_ID`
- `REMOTE_ENVIRONMENT_ID`

## Python evidence

- `tests/test_exec_server_environment_provider_rs.py::test_default_provider_requests_local_environment_when_url_is_missing`
- `tests/test_exec_server_environment_provider_rs.py::test_default_provider_requests_local_environment_when_url_is_empty`
- `tests/test_exec_server_environment_provider_rs.py::test_default_provider_omits_local_environment_for_none_value`
- `tests/test_exec_server_environment_provider_rs.py::test_default_provider_adds_remote_environment_for_websocket_url`
- `tests/test_exec_server_environment_provider_rs.py::test_default_provider_normalizes_exec_server_url`
- `tests/test_exec_server_environment_provider_rs.py::test_normalize_exec_server_url_matches_rust_helper`

## Notes

Python keeps `snapshot()` synchronous because the current implementation is
purely in-memory and environment-variable backed. This preserves the Rust
snapshot data contract without introducing an async runtime dependency. The
configured TOML provider is owned by `src/environment_toml.rs` and remains a
separate module-scoped follow-up.

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
