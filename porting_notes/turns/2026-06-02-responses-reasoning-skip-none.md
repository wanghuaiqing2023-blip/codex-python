# 2026-06-02 - Responses reasoning skip-none request shape

## Scope

- Core path: model request construction for `exec`/turn sampling.
- Upstream graph slice: `codex-rs/core/src/client.rs#build_responses_request` and `codex-rs/codex-api/src/common.rs#Reasoning`.

## Rust behavior confirmed

- `ModelClientSession::build_responses_request` includes a `reasoning` object whenever the model supports reasoning summaries.
- `codex_api::Reasoning` marks both `effort` and `summary` with `#[serde(skip_serializing_if = "Option::is_none")]`.
- A request can therefore include `reasoning: {}` while still requesting `include: ["reasoning.encrypted_content"]`.

## Python changes

- `pycodex.core.client.build_reasoning` now omits `effort` and `summary` when their effective values are absent instead of sending JSON `null`.
- Nested request serialization now drops `None` fields inside mappings, matching Rust struct skip rules while preserving existing top-level request behavior.
- Updated core request/runtime tests that previously expected `summary: None`.

## Validation

- Passed:
  - direct stdlib assertion script for default effort, empty reasoning object, and nested enum serialization.
  - `python -m unittest tests.test_core_turn_request tests.test_core_http_transport tests.test_core_session_runtime`
  - `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_run tests.test_exec_event_processor tests.test_core_tool_router tests.test_core_unified_exec_handler tests.test_core_view_image_handler tests.test_core_turn_request tests.test_core_session_runtime`
- Could not run `tests.test_core_client` directly because this environment does not have `pytest` installed; the touched behavior was covered by stdlib assertion plus adjacent unittest suites.
