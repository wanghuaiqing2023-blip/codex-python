# Local HTTP review disabled tool set

## Source slice

- Used the upstream graph as the navigation index for the core review sub-turn path.
- Confirmed behavior in `codex/codex-rs/core/src/session/review.rs`.
- Rust review turns disable `Feature::WebSearchRequest`, `Feature::WebSearchCached`, and `Feature::Goals`, and force `WebSearchMode::Disabled`. The source comment also calls out `view_image` as disabled for reviews.

## Python changes

- Added `LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES` for the local HTTP review model view.
- `LocalHttpReviewModelInfo` now exposes that disabled-tool set instead of inlining the names.
- `LocalHttpShellToolRouter` filters base-router specs by disabled tool name, covering existing `view_image`, `web_search`, and goal tool specs before adding the local shell/write/patch tools.
- `local_http_model_allows_view_image_tool` now respects both the compatibility boolean and the generic disabled-tool set.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_model_image_helpers_match_rust_defaults tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_hides_view_image_for_review_model tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tools_built_tools_filters_review_disabled_base_tools`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_spec_plan tests.test_core_view_image_handler tests.test_exec_config_plan tests.test_exec_session`

## Deferred

- This remains a local HTTP compatibility slice. It does not implement web search, goal tools, or other extension runtimes; it only preserves Rust review visibility behavior when those specs are present.
