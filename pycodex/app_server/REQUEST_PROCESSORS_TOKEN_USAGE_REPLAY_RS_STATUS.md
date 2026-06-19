# codex-app-server src/request_processors/token_usage_replay.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/token_usage_replay.rs`

Python module:

- `pycodex/app_server/request_processors_token_usage_replay.py`

Parity tests:

- `tests/test_app_server_request_processors_token_usage_replay_rs.py`

## Behavior contract

- Replays rollout history through `ThreadHistoryBuilder` while snapshotting the
  active turn before each `TokenCount` event, matching Rust's attribution order.
- Returns the original loaded turn id when it still exists in the current turn
  list, otherwise falls back to the rebuilt turn at the same position.
- Provides Rust's fallback replay turn id selection: latest completed/failed
  turn, then last turn, then an empty string.
- Maps core `TokenUsageInfo` into app-server v2 `ThreadTokenUsage` fields.
- Sends `ThreadTokenUsageUpdated` to only the requested connection and skips
  sending when the conversation has no token usage info.

## Notes

This module intentionally keeps conversation storage and concrete outgoing
transport as injected dependencies. The parent message processor decides when
token-usage replay is allowed; this module owns notification construction and
turn attribution only.

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_token_usage_replay_rs.py -q`
  -> 8 passed.
- `python -m py_compile pycodex/app_server/request_processors_token_usage_replay.py tests/test_app_server_request_processors_token_usage_replay_rs.py`
