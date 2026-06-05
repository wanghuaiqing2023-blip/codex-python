# 2026-06-02 turn runtime mailbox preemption follow-up

## Upstream slice

- Used the upstream graph to continue the core turn stream path through:
  - `codex-rs/core/src/session/turn.rs#try_run_sampling_request`
  - `codex-rs/core/src/stream_events_utils.rs#handle_output_item_done`
- Confirmed from Rust source that `OutputItemDone` for assistant commentary and reasoning can preempt the current request when mailbox items are pending:
  - `preempt_for_mailbox_mail && sess.input_queue.has_pending_mailbox_items().await`
  - returns `SamplingRequestResult { needs_follow_up: true, last_agent_message }`.

## Python changes

- Wired `pycodex.core.turn_runtime` to query `input_queue.has_pending_mailbox_items()` while building stream apply plans.
- Added per-batch stream apply-plan follow-up detection for mailbox preemption.
- Updated stream output-result projection so completed assistant items carry `last_agent_message`, matching Rust `handle_output_item_done`.
- Kept tool-call follow-up out of the apply-plan loop decision to avoid sticky synthetic follow-ups; tool follow-up remains driven by actual tool response items.
- Updated runtime state from non-stream response items so later final answers override earlier streamed commentary/preemption messages.

## Validation

- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_stream_events_utils`

