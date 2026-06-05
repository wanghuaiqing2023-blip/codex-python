# Local HTTP review view_image gate

## Upstream slice

- Used `codex/.understand-anything/knowledge-graph.json` to locate the review and image-viewing paths:
  - `codex-rs/core/src/session/review.rs`
  - `codex-rs/core/src/tools/spec_plan.rs`
  - `codex-rs/core/src/tools/handlers/view_image.rs`
- Confirmed from Rust `spawn_review_thread` that review turns disable `WebSearchRequest`, `WebSearchCached`, and `Goals`, and set web search mode to disabled.
- The source comment explicitly states that reviews disable `web_search` and `view_image` regardless of global settings.

## Python slice

- `LocalHttpReviewModelInfo` now marks the local review model view with `view_image_tool_disabled = True`.
- `local_http_shell_tools_built_tools` and `LocalHttpShellToolRouter` now honor a lightweight `local_http_model_allows_view_image_tool()` gate.
- Normal local HTTP exec still exposes `view_image`; local HTTP review with shell tools hides it while keeping core shell/apply_patch tools available.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_model_image_helpers_match_rust_defaults tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_hides_view_image_for_review_model tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_review_http_sampling_shell_tools_hide_view_image tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_view_image_tool_loop_returns_image_output`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_view_image_handler tests.test_core_spec_plan tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- Local HTTP review currently has no dedicated web-search tool wrapper, so this slice only needed to gate `view_image`. Broader web-search parity remains outside the current local HTTP core-tool bridge.
