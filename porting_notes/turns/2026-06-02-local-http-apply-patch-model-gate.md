# Local HTTP apply_patch model gate

## Upstream slice

- Used `codex/.understand-anything/knowledge-graph.json` to locate the core request tool-planning files:
  - `codex-rs/core/src/tools/spec_plan.rs`
  - `codex-rs/core/src/tools/spec_plan_tests.rs`
  - `codex-rs/core/src/tools/handlers/apply_patch_spec.rs`
- Confirmed from Rust source that `add_core_utility_tools` exposes `apply_patch` only when the turn has an environment and `turn_context.model_info.apply_patch_tool_type.is_some()`.
- Confirmed from `environment_count_controls_environment_backed_tools` that `apply_patch` is omitted when no environment is available and visible when the model advertises `ApplyPatchToolType::Freeform`.

## Python slice

- `LocalHttpModelInfo` now carries a lightweight `apply_patch_tool_type` field, defaulting to `"freeform"` for the local HTTP exec path's synthetic model metadata.
- `local_http_shell_tools_built_tools` accepts `model_info` and only auto-adds the model-visible `apply_patch` custom tool when `local_http_model_allows_apply_patch_tool` returns true.
- Existing compatibility remains: callers without model metadata, or with older model metadata lacking the field, continue to expose `apply_patch`.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_hides_apply_patch_when_model_lacks_support tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_model_allows_apply_patch_tool_matches_rust_model_gate tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_preserves_existing_specs tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_uses_configured_shell_spec_flags tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_exposes_permission_tools_when_configured`
- `python -m unittest tests.test_exec_local_runtime`

## Deferred

- The local HTTP path still treats the local working directory as the active environment. Multi-environment request shaping is covered in shared core helpers but not yet wired into this local exec runtime.
