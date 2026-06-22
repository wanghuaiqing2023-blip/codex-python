# runtime_paths.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/runtime_paths.rs`

Python surface: `pycodex.exec_server.ExecServerRuntimePaths`

Status: `complete`

## Rust anchors

- `ExecServerRuntimePaths { codex_self_exe, codex_linux_sandbox_exe }`
- `ExecServerRuntimePaths::from_optional_paths`
- `ExecServerRuntimePaths::new`
- `absolute_path(...)` wrapping `AbsolutePathBuf::from_absolute_path`
- Missing `codex_self_exe` error text: `Codex executable path is not configured`

## Python evidence

- `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_from_optional_paths_requires_codex_self_exe`
- `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_new_absolutizes_configured_paths`
- `tests/test_exec_server_process_id_runtime_paths_rs.py::test_runtime_paths_accepts_missing_linux_sandbox_path`
- `tests/test_exec_config_plan.py::ExecConfigPlanTests::test_build_exec_run_main_plan_matches_in_process_startup_defaults`
- `tests/test_thread_manager_sample_main_rs.py::test_run_main_starts_thread_runs_turn_shutdown_and_removes`

## Notes

The Python type now uses Rust field names and `AbsolutePathBuf` values rather
than the older placeholder `fs_helper` field. Adjacent core startup tests pass
with explicit `codex_self_exe` fixtures, matching the Rust requirement that the
Codex executable path be configured before local runtime paths are built.

## Validation

- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
  passed on 2026-06-21 with `149 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_id_runtime_paths_rs.py`
  passed on 2026-06-21.
