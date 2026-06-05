# Core request_permissions auto-deny policy

## Upstream slice

- Used the upstream graph around `request_permissions_for_cwd` on the common core runtime path.
- Confirmed behavior in `codex-rs/core/src/session/mod.rs#request_permissions_for_cwd`.

## Rust behavior matched

- `AskForApproval::Never` returns an empty `RequestPermissionsResponse` immediately.
- `AskForApproval::Granular` with `request_permissions=false` also returns an empty response immediately.
- These auto-deny branches do not call the client/request callback and do not record grants.

## Python changes

- `InMemoryCodexSession.request_permissions_for_cwd` now checks the active/fallback approval policy before invoking `request_permissions_callback`.
- Added support for `GranularApprovalConfig` in that policy check.
- Added session-level coverage proving callback bypass and no grant recording.
- Added default local HTTP core-loop coverage proving model-visible `request_permissions` output is an empty successful turn-scoped response under `approval_policy=never`.

## Validation

- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_request_permissions_auto_denies_when_approval_never tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_request_permissions_auto_denies_when_granular_disallows_tool tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_auto_denies_when_approval_never tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_unblocks_apply_patch`
- `python -m unittest tests.test_core_session_runtime tests.test_core_request_permissions_handler tests.test_core_apply_patch tests.test_core_spec_plan tests.test_core_turn_runtime tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_auto_denies_when_approval_never tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_unblocks_apply_patch`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
- `python -m py_compile pycodex\core\session_runtime.py tests\test_core_session_runtime.py tests\test_exec_local_runtime.py`

## Known gaps

- This preserves the Rust auto-deny behavior in the in-memory CLI/core runtime. Full app-server pending-event behavior remains separate deeper parity work.
- Guardian review routing for `request_permissions` is still outside this focused core CLI slice.
