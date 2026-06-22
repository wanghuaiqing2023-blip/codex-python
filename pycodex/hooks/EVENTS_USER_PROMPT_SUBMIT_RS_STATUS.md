# codex-hooks src/events/user_prompt_submit.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/user_prompt_submit.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- Completed `UserPromptSubmit` hook output parsing handles plain stdout as
  model context and invalid JSON-looking stdout as failure.
- Valid JSON output preserves `systemMessage` warnings, additional model
  context, `continue:false` stop reasons, and Claude-style
  `decision:block` feedback.
- `decision:block` without a non-empty `reason` fails without injecting
  additional context, matching Rust's `invalid_block_reason` branch.
- Exit code 2 with non-empty stderr blocks processing; exit code 2 without a
  reason, other non-zero exits, missing status code, and command errors fail.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/user_prompt_submit.rs`
- Rust tests:
  - `continue_false_preserves_context_for_later_turns`
  - `claude_block_decision_blocks_processing`
  - `claude_block_decision_requires_reason`
  - `exit_code_two_blocks_processing`

## Python Evidence

- `tests/test_hooks_events_user_prompt_submit_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short
```

Passed on 2026-06-21 with `8 passed`.

Related hooks validation also passed with:

```text
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short
```

Results: `50 passed` and `73 passed`.
