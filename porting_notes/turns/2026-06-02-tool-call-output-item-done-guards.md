# 2026-06-02 tool call output-item-done guards

## Upstream slice

- Used the upstream graph to continue the core stream/tool path through:
  - `codex-rs/core/src/session/turn.rs#try_run_sampling_request`
  - `codex-rs/core/src/stream_events_utils.rs#handle_output_item_done`
  - `codex-rs/core/src/stream_events_utils.rs#response_input_to_response_item`
- Confirmed from Rust source:
  - normal tool calls reopen mailbox delivery for the current turn before the tool future is queued;
  - `FunctionCallError::RespondToModel` records the original model output item, then records the model-visible tool output response item, and requests a follow-up.

## Python changes

- Added focused guards in `tests.test_core_stream_events_utils` for the Rust ordering and mailbox behavior.
- No production-code change was needed for this slice; the current implementation already matched the checked Rust behavior.

## Validation

- `python -m unittest tests.test_core_stream_events_utils`
- `python -m unittest tests.test_core_turn_runtime`

