# codex-app-server src/bespoke_event_handling.rs status

Rust module: `codex/codex-rs/app-server/src/bespoke_event_handling.rs`

Python module: `pycodex/app_server/bespoke_event_handling.py`

Status: `complete`

## Covered

- `handle_turn_diff` notification payload construction.
- `handle_turn_plan_update` mapping from update-plan arguments to
  `TurnPlanUpdatedNotification` and `TurnPlanStep` values.
- `emit_turn_completed_with_status` empty `Turn` payload construction with
  `TurnItemsView::NotLoaded`, status, error, timestamps, and duration.
- `maybe_emit_hook_prompt_item_completed` local filtering and hook-prompt item
  payload projection for user hook prompt messages.
- `mcp_server_elicitation_response_from_client_result` fallback behavior:
  valid client response forwarding, turn-transition cancel, and decline on
  client/deserialization errors.
- `request_permissions_response_from_client_result` fallback behavior:
  turn-transition drop, default turn-scoped empty grants on errors, and
  rejection of session-scoped strict auto-review grants.
- `render_review_output_text` explanation/findings composition and fallback
  message behavior.
- `map_file_change_approval_decision` mapping to core review-decision variants.
- `now_unix_timestamp_ms` millisecond timestamp helper.

## Deferred

- The full `apply_bespoke_event_handling` async dispatcher, concrete
  `CodexThread::submit(...)`, watcher/permit lifetimes, outgoing transport
  emission, and thread-state mutation remain runtime integration work.
- Command execution approval completion side effects, rollback store loading,
  and permission-profile intersection with concrete policy objects remain
  injected/runtime-owned boundaries for this module slice.

## Python parity tests

- `tests/test_app_server_bespoke_event_handling_rs.py`

- `python -m pytest tests/test_app_server_bespoke_event_handling_rs.py -q`
  passed on 2026-06-19 with 8 tests.
- `python -m py_compile pycodex/app_server/bespoke_event_handling.py
  tests/test_app_server_bespoke_event_handling_rs.py` passed on 2026-06-19.
