# fs_sandbox.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/fs_sandbox.rs`

Python surface: `pycodex.exec_server`

Status: `complete` for helper policy/env/cwd planning,
SandboxManager transform handoff, dependency-injected runner responses, and
subprocess helper execution

## Rust anchors

- `FileSystemSandboxRunner::{new, sandbox_exec_request}` planning inputs
- `FileSystemSandboxRunner::run`
- `run_command`
- `json_error`
- `sandbox_cwd`
- `helper_read_roots`
- `add_helper_runtime_permissions`
- `helper_env`
- `helper_env_from_vars`
- `helper_env_key_is_allowed`

## Python evidence

- `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_enable_minimal_reads_for_restricted_profiles`
- `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_preserve_writes_and_add_helper_read_roots`
- `tests/test_exec_server_fs_sandbox_rs.py::test_helper_env_preserves_allowlist_without_leaking_secrets`
- `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_cwd_uses_context_cwd`
- `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_cwd_rejects_dynamic_profile_without_context_cwd`
- `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_include_helper_read_root_without_additional_permissions`
- `tests/test_exec_server_fs_sandbox_rs.py::test_helper_permissions_include_linux_sandbox_alias_parent`
- `tests/test_exec_server_fs_sandbox_rs.py::test_sandbox_exec_request_carries_helper_env`
- `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_encodes_request_and_decodes_ok_response`
- `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_returns_helper_error_response`
- `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_maps_nonzero_status_and_invalid_json`
- `tests/test_exec_server_fs_sandbox_rs.py::test_runner_run_rejects_empty_sandbox_command`
- `tests/test_exec_server_fs_sandbox_rs.py::test_run_command_spawns_helper_subprocess_and_decodes_stdout`

## Notes

This status covers helper planning, policy mutation, request JSON
encoding, helper response decoding, helper error response forwarding,
non-zero status mapping, invalid helper JSON mapping, empty command rejection,
the concrete `pycodex.sandboxing.SandboxManager` transform handoff, and real
subprocess helper stdin/stdout/stderr execution. Platform-specific sandbox
backend enforcement remains owned by the sibling sandboxing/linux-sandbox
crates.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_fs_sandbox_rs.py -q --tb=short
13 passed

python -m pytest tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
36 passed, 1 skipped

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_fs_sandbox_rs.py
passed
```
