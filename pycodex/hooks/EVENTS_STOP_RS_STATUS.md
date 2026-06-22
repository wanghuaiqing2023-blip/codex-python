# codex-hooks src/events/stop.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/stop.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `StopHookTarget` maps `Stop` targets to no matcher and `SubagentStop`
  targets to the agent type matcher.
- Completed stop hook output parsing accepts empty stdout, valid JSON
  `systemMessage` warnings, `continue:false` stop reasons, and
  `decision:block` reasons.
- Blocking stop hooks create `HookPromptFragment` continuation prompts tied to
  the completed hook run id.
- Invalid/blank block reasons, invalid non-empty stdout, process errors, other
  non-zero exits, and missing status codes fail with Rust-compatible messages.
- Exit code 2 blocks only when stderr has a non-empty continuation prompt.
- Aggregation preserves declaration order for block reasons/fragments, joins
  block reasons with blank lines, and lets any stop result suppress blocking
  continuation fragments.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/stop.rs`
- Rust tests:
  - `block_decision_with_reason_sets_continuation_prompt`
  - `block_decision_without_reason_is_invalid`
  - `continue_false_overrides_block_decision`
  - `exit_code_two_uses_stderr_feedback_only`
  - `exit_code_two_without_stderr_does_not_block`
  - `block_decision_with_blank_reason_fails_instead_of_blocking`
  - `invalid_stdout_fails_instead_of_silently_nooping`
  - `aggregate_results_concatenates_blocking_reasons_in_declaration_order`

## Python Evidence

- `tests/test_hooks_events_stop_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_stop_rs.py -q --tb=short
```

Passed on 2026-06-21 with `12 passed`.

Related hooks validation also passed with:

```text
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py -q --tb=short
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short
```

Results: `62 passed` and `85 passed`.
