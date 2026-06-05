# Local HTTP review view_image filtering

## Upstream slice

- Rechecked `codex-rs/core/src/session/review.rs`.
- Rust review turns explicitly disable `web_search` and `view_image` regardless of global settings before building the child review turn context.

## Python slice

- `LocalHttpShellToolRouter.model_visible_specs()` now filters an existing/base-router `view_image` spec when the model view marks `view_image_tool_disabled`.
- This completes the local HTTP review gate from the previous slice: review no longer merely avoids auto-adding `view_image`; it also removes a preexisting `view_image` spec supplied by an underlying tool router.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_hides_view_image_for_review_model tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_filters_existing_view_image_for_review_model tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_shell_tools_hide_view_image tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_view_image_tool_loop_returns_image_output`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_spec_plan tests.test_core_view_image_handler tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- Local HTTP review still has no web-search bridge to filter. If a future local web-search wrapper is added, it should use the same review-disabled pattern.
