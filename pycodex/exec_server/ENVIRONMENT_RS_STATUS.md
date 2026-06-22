# codex-exec-server src/environment.rs Status

Rust source: `codex/codex-rs/exec-server/src/environment.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Covered Contract

- `Environment.create(...)` and `Environment.create_for_tests(...)` preserve
  the Rust local/remote/disabled selection rules after
  `normalize_exec_server_url(...)`.
- Local environments carry `ExecServerRuntimePaths`, expose a local process
  backend, and select `LocalFileSystem.with_runtime_paths(...)` when runtime
  paths are configured.
- Remote environments record websocket transport metadata and expose explicit
  lazy remote process/filesystem/HTTP boundaries without opening a connection
  during construction.
- `EnvironmentManager.default_for_tests`, `without_environments`,
  `create_for_tests`, and `create_for_tests_with_local` preserve default,
  local, and remote lookup behavior.
- `EnvironmentManager.from_snapshot(...)` validates empty ids, reserved
  `local`, duplicate ids, unknown defaults, included local runtime paths, and
  disabled defaults with Rust-shaped protocol errors.
- `default_environment`, `default_environment_id`,
  `default_environment_ids`, `try_local_environment`,
  `default_or_local_environment`, and `get_environment` mirror Rust lookup
  semantics.
- `upsert_environment(...)` normalizes remote URLs, rejects empty/disabled
  URLs and empty ids, replaces existing named remote environments, and leaves
  default selection unchanged.

## Evidence

- Rust tests in `src/environment.rs`:
  `create_local_environment_does_not_connect`,
  `environment_manager_normalizes_empty_url`,
  `disabled_environment_manager_has_no_default_or_local_environment`,
  `environment_manager_reports_remote_url`,
  `environment_manager_builds_from_snapshot`,
  `environment_manager_uses_explicit_provider_default`,
  `environment_manager_disables_provider_default`,
  snapshot rejection tests,
  `environment_manager_omits_default_provider_local_lookup_when_default_disabled`,
  `environment_manager_carries_local_runtime_paths`,
  and `environment_manager_upserts_named_remote_environment`.
- Python parity tests:
  `tests/test_exec_server_environment_rs.py`.

Focused validation:

```text
python -m pytest tests/test_exec_server_environment_rs.py -q --tb=short
```

Result on 2026-06-21: `11 passed`.

Adjacent validation:

```text
python -m pytest tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short
```

Result on 2026-06-21: `41 passed`.

Exec-server focused regression:

```text
python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short
```

Result on 2026-06-21: `317 passed, 1 skipped`.

## Remaining Boundaries

`src/environment.rs` is complete as an environment registry and
environment-construction module. Concrete remote process/filesystem execution,
relay/harness transport, websocket serving, and full remote client connection
semantics remain owned by sibling modules.

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
