# codex-hooks src/events/compact.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/compact.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Rust Anchors

- `PreCompactRequest`
- `PostCompactRequest`
- `PreCompactOutcome`
- `StatelessHookOutcome`
- `pre_command_input_json`
- `post_command_input_json`
- `parse_pre_completed`
- `parse_post_completed`
- Dispatcher registrations for `HookEventName::PreCompact` and
  `HookEventName::PostCompact`

## Behavior Covered

- Pre/PostCompact command input serialization preserves session id, turn id,
  optional subagent fields, transcript path, cwd, hook event name, model, and
  compaction trigger.
- Completed-output parsing mirrors Rust's `deny_unknown_fields` compact output
  schema, so JSON-looking stdout with unsupported fields fails instead of
  becoming a no-op.
- Universal `systemMessage` becomes a warning entry; `suppressOutput` is parsed
  and ignored; `continue:false` stops execution with either `stopReason` or the
  Rust event-specific default stop message.
- Plain non-JSON stdout is ignored for both PreCompact and PostCompact.
- Process errors, nonzero exit codes, missing exit status, and stderr fallback
  error text match the Rust module contract.

## Python Tests

- `tests/test_hooks_events_compact_rs.py`

## Validation

- `python -m pytest tests/test_hooks_events_compact_rs.py -q --tb=short`
  passed on 2026-06-21 with `11 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_events_compact_rs.py`
  passed on 2026-06-21.
- Hooks module validation passed on 2026-06-21 with `111 passed`.
- Hooks plus core hooks regression validation passed on 2026-06-21 with
  `134 passed`.

## Remaining Debt

No module-local debt remains for `src/events/compact.rs`. `codex-hooks` remains
`module_progress` while `src/engine/*` and `src/schema.rs` remain open.
