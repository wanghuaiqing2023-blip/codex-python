# process_id.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/process_id.rs`

Python surface: `pycodex.exec_server.ProcessId`

Status: `complete`

## Rust anchors

- `ProcessId(String)` with `#[serde(transparent)]`
- `ProcessId::new`
- `ProcessId::as_str`
- `ProcessId::into_inner`
- `Deref<Target = str>`, `Borrow<str>`, `AsRef<str>`, `Display`
- `From<String>`, `From<&str>`, `From<&String>`, and `From<ProcessId> for String`
- Derived `Eq`, `Hash`, and `Ord`

## Python evidence

- `tests/test_exec_server_process_id_runtime_paths_rs.py::test_process_id_string_newtype_contract`
- `tests/test_exec_server_process_id_runtime_paths_rs.py::test_process_id_protocol_fields_keep_transparent_value`

## Notes

Python keeps compatibility with the former `str` alias by allowing comparison
between `ProcessId` and `str`, while the explicit newtype API now matches the
Rust module boundary.

## Validation

- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m pytest tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short`
  passed on 2026-06-21 with `149 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_id_runtime_paths_rs.py`
  passed on 2026-06-21.
