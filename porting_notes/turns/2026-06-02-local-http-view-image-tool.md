# Local HTTP view_image tool

## Upstream slice

- Used `codex/.understand-anything/knowledge-graph.json` to locate the core image-viewing tool path:
  - `codex-rs/core/src/tools/spec_plan.rs`
  - `codex-rs/core/src/tools/handlers/view_image_spec.rs`
  - `codex-rs/core/src/tools/handlers/view_image.rs`
- Confirmed from `add_core_utility_tools` that Rust exposes `view_image` when the turn has an environment.
- Confirmed from `ViewImageHandler` that successful calls return a `function_call_output` whose body is an `input_image` content item, and invalid paths/details are model-visible tool errors.
- Confirmed `ViewImageToolOptions` only includes the `detail` enum when original image detail is supported.

## Python slice

- Reused the existing Python core `ViewImageHandler`, `ViewImageToolOptions`, and `create_view_image_tool` implementation.
- Added `view_image` to the local HTTP exec model-visible tool wrapper after shell/write/apply_patch planning.
- Added local model metadata helpers for image input support and original-detail support.
- Added `view_image` execution to the local HTTP tool loop so image files are read from the exec cwd and returned as `input_image` content items in follow-up model requests.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_view_image_tool_spec_shape tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_preserves_existing_specs tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_uses_configured_shell_spec_flags tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_hides_apply_patch_when_model_lacks_support tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_model_image_helpers_match_rust_defaults tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_view_image_tool_loop_returns_image_output`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_view_image_handler tests.test_core_spec_plan`

## Deferred

- The local HTTP runtime still models a single local environment. Multi-environment `environment_id` routing for `view_image` remains covered by core helpers but is not wired into this local exec bridge.
