# Core apply_patch hook, streaming, and policy path

## Upstream slice

- Used the upstream dependency graph to stay on the common runtime path around direct `apply_patch` custom tools.
- Confirmed behavior in:
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/core/src/tools/runtimes/apply_patch.rs`
  - `codex-rs/apply-patch/src/lib.rs`
  - `codex-rs/apply-patch/src/invocation.rs`

## Rust behavior matched

- Direct `apply_patch` is a custom/freeform tool, not a JSON function payload.
- Pre/post hook payloads use the custom command shape: `{"command": patch_text}`.
- Hook rewrites can replace the custom patch input.
- Streaming patch deltas emit `patch_apply_updated` only when the apply-patch streaming feature is enabled.
- Verified patch hunks are converted into protocol file-change progress entries before the patch is applied.
- Sandbox/approval context must participate before a patch writes to disk.

## Python changes

- Extended `pycodex/core/apply_patch.py` with the direct core runtime pieces:
  - `ApplyPatchHandler.create_diff_consumer`
  - pre/post hook payload helpers
  - hook-input rewrite for custom patch payloads
  - `ApplyPatchArgumentDiffConsumer`
  - `convert_apply_patch_hunks_to_protocol`
  - explicit write-policy rejection before `apply_patch_action_to_disk`
- Exported the new apply-patch helpers from `pycodex/core/__init__.py`.
- Added focused unit coverage for hook payloads, streaming feature gating, hunk-to-protocol conversion, and policy checks.
- Added default local HTTP core-loop coverage proving model-emitted direct `apply_patch` custom calls now run through the core tool dispatch path and return `custom_tool_call_output` to the follow-up model request.

## Validation

- `python -m unittest tests.test_core_apply_patch`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_apply_patch_tool_loop_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_core_apply_patch_respects_read_only_policy tests.test_core_apply_patch`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `python -m py_compile pycodex\core\apply_patch.py pycodex\core\__init__.py tests\test_core_apply_patch.py tests\test_exec_local_runtime.py`

## Known gaps

- The direct Python handler currently returns model-visible approval errors for blocked writes; it does not yet implement a full interactive approval prompt path for direct core `apply_patch`.
- Runtime sandbox execution is still an approximation in Python. This slice prevents unauthorized direct writes in the core path but does not reproduce every Rust sandbox backend behavior.
- App-server/event-daemon details remain intentionally out of scope unless they become required by the CLI/core runtime path.
