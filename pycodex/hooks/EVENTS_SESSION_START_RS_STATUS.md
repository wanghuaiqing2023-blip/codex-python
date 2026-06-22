# codex-hooks src/events/session_start.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/session_start.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `SessionStartSource.as_str()` returns Rust's lowercase matcher strings:
  `startup`, `resume`, `clear`, and `compact`.
- `StartHookTarget` maps `SessionStart` targets to `SessionStart` and the
  source matcher; `SubagentStart` targets map to `SubagentStart` and the agent
  type matcher.
- Completed `SessionStart`/`SubagentStart` hook output parsing handles plain
  stdout as model context, valid JSON warnings/context, invalid JSON-looking
  stdout as failure, non-zero/no-status process results as failure, and
  `continue:false` as a stop only for `SessionStart`.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/session_start.rs`
- Rust tests:
  - `plain_stdout_becomes_model_context`
  - `continue_false_preserves_context_for_later_turns`
  - `invalid_json_like_stdout_fails_instead_of_becoming_model_context`
  - `subagent_start_plain_stdout_becomes_model_context`
  - `subagent_start_continue_false_is_ignored`

## Python Evidence

- `tests/test_hooks_events_session_start_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_session_start_rs.py -q --tb=short
```

Passed on 2026-06-21 with `6 passed`.
