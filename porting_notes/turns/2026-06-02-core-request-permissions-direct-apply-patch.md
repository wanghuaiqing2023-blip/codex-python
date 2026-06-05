# Core request_permissions unblocks direct apply_patch

## Upstream slice

- Used the upstream graph around `request_permissions` and direct `apply_patch` on the common core runtime path.
- Confirmed behavior in:
  - `codex-rs/core/src/codex_delegate.rs#handle_request_permissions`
  - `codex-rs/core/src/session/mod.rs#request_permissions_for_cwd`
  - `codex-rs/core/src/session/mod.rs#notify_request_permissions_response`
  - `codex-rs/core/src/session/mod.rs#record_granted_request_permissions_for_turn`
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`

## Rust behavior matched

- `request_permissions` is exposed only when the feature gate allows it.
- A successful `request_permissions` response is normalized against the requested profile and recorded at turn or session scope.
- Later shell-like write operations in the same turn can use those recorded grants.
- Direct `apply_patch` must still respect the base sandbox policy, but recorded grants can authorize writes that the base policy would otherwise reject.

## Python changes

- The default core environment tool router now registers `request_permissions` when `Feature.REQUEST_PERMISSIONS_TOOL` is enabled.
- Direct `ApplyPatchHandler` now checks merged turn/session grants before returning a sandbox approval error.
- Added a focused handler test for read-only base policy plus granted write permission.
- Added a default local HTTP core-loop test covering:
  - model emits `request_permissions`
  - Python callback grants write access
  - model emits direct `apply_patch`
  - patch writes the file
  - final model answer is returned after successful tool output

## Validation

- `python -m unittest tests.test_core_apply_patch.CoreApplyPatchTests.test_apply_patch_handler_allows_granted_write_permissions_for_read_only_policy tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_unblocks_apply_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_apply_patch_respects_read_only_policy`
- `python -m unittest tests.test_core_apply_patch tests.test_core_spec_plan tests.test_core_turn_runtime tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_request_permissions_unblocks_apply_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_apply_patch_tool_loop_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_apply_patch_respects_read_only_policy`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite tests.test_exec_local_http_runtime_smoke_suite`
- `python -m py_compile pycodex\core\apply_patch.py pycodex\core\spec_plan.py pycodex\core\turn_runtime.py tests\test_core_apply_patch.py tests\test_exec_local_runtime.py`

## Known gaps

- This slice uses already-recorded grants to unblock direct `apply_patch`; it does not implement the full Rust pending-event/interactive client response machinery for every app-server surface.
- The direct Python `apply_patch` approval-required path still returns a model-visible error when no grant exists instead of prompting interactively.
- Guardian review and strict auto-review behavior remain deeper parity work outside this focused CLI/core slice.
