# 2026-06-02 - Guardian developer context isolation

## Scope

- Core path: session initial context construction before `exec`/turn sampling.
- Upstream graph slice: `codex-rs/core/src/session/mod.rs#build_initial_context` plus guardian reviewer source detection.

## Rust behavior confirmed

- For normal sessions, `turn_context.developer_instructions` are appended to the aggregated developer context after permissions instructions.
- For guardian reviewer subagent sessions, those developer instructions are not merged into the aggregated developer bundle.
- Instead, Rust emits them as a separate developer item after contextual user sections, keeping the guardian policy prompt isolated and easier to audit.

## Python changes

- `pycodex.core.session_runtime._build_initial_context_items` now uses the existing `is_guardian_reviewer_source` helper.
- Guardian reviewer sessions emit developer instructions as a final separate developer message.
- Normal session ordering remains unchanged.

## Validation

- Passed:
  - `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_initial_context_includes_developer_instructions_after_permissions tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_guardian_source_separates_developer_instructions tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_initial_context_includes_collaboration_mode_after_permissions`
  - `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_run tests.test_exec_event_processor tests.test_core_tool_router tests.test_core_unified_exec_handler tests.test_core_view_image_handler tests.test_core_turn_request tests.test_core_session_runtime`
