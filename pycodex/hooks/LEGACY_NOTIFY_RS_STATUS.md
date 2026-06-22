# codex-hooks src/legacy_notify.rs Status

Rust crate: `codex-hooks`

Rust module: `src/legacy_notify.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `legacy_notify_json(payload)` projects `HookPayload::AfterAgent` into the
  historical `UserNotification::AgentTurnComplete` JSON shape.
- The serialized notification keeps kebab-case field names:
  `thread-id`, `turn-id`, `input-messages`, and `last-assistant-message`.
- `client` is omitted when absent; `last-assistant-message` remains present
  and may carry a JSON null value.
- `notify_hook(argv)` builds a hook named `legacy_notify`, returns success for
  an empty command, appends the legacy JSON payload to argv, redirects stdio to
  null handles, and maps spawn errors to a non-aborting failed-continue result.

## Rust Evidence

- `codex/codex-rs/hooks/src/legacy_notify.rs`
- Rust tests:
  - `tests::test_user_notification`
  - `tests::legacy_notify_json_matches_historical_wire_shape`

## Python Evidence

- `tests/test_hooks_legacy_notify_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_legacy_notify_rs.py -q --tb=short
```

Passed on 2026-06-21 with `5 passed`.
