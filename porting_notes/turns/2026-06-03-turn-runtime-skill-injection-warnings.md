# 2026-06-03 Turn-runtime skill injection warning propagation

## Context
During user-turn context preparation, upstream Rust emits warning events for all
`skill_injections.warnings`, even when `build_skill_injections` itself succeeds.
`pycodex` previously only sent warnings when `build_skill_injections` raised.

## Change
- Updated `pycodex/core/turn_runtime.py::_prepare_user_turn_skill_plugin_items`:
  - After successful `build_skill_injections`, iterate through
    `skill_injections.warnings` and emit each warning through
    `_send_warning_event(...)`.
- Added regression coverage in
  `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_forwards_skill_injection_warnings_as_events`
  using a patched `build_skill_injections` return value with warnings.

## Notes
- This keeps behavior within the core execution path and avoids changing MCP/plugin
  runtime behavior beyond warning event compatibility.
- No external dependency changes were introduced.
