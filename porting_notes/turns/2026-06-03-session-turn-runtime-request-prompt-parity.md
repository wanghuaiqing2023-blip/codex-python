## Session turn request prompt parity

- Objective: ensure sampling and HTTP sampling request construction for in-memory sessions carries sandbox/permissions instructions into the model prompt input, not only analytics payloads.
- Scope: `tests/test_core_session_runtime.py`
- Evidence:
  - `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection` now asserts `result.request_plans[0].prompt.get_formatted_input()` includes a developer entry containing `<permissions instructions>` and `Network access is ...`.
  - `test_in_memory_session_runs_user_turn_http_sampling` now asserts the same prompt-shape properties after HTTP path sampling.
  - `test_in_memory_session_prompt_instructions_injection_consistent_between_sampling_variants` compares extracted permissions-prompt developer texts from both request constructors and verifies permissions marker counts align.
- Coverage impact: aligns both sampling transport paths with Rust-style request-construction behavior, reducing the risk that permission context is present in telemetry but missing from actual model input.
- Type: request-shape regression, core-slice parity checkpoint.
