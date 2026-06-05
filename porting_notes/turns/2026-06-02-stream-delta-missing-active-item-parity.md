# Stream delta missing-active-item parity

## Rust sources checked

- `codex/codex-rs/core/src/session/turn.rs`
- `codex/codex-rs/core/src/stream_events_utils.rs`
- `codex/codex-rs/core/src/util.rs`

## Behavior confirmed

- `ResponseEvent::OutputTextDelta` requires an active streamed item. If no active item exists, Rust calls `error_or_panic("OutputTextDelta without active item")`.
- `ResponseEvent::ReasoningSummaryDelta`, `ReasoningSummaryPartAdded`, and `ReasoningContentDelta` follow the same missing-active-item pattern with their event-specific messages.
- If an item exists but is not streaming to the client, Rust silently skips those deltas.
- `ResponseEvent::ToolCallInputDelta` without an active tool argument diff consumer is intentionally ignored.

## Python changes

- Updated `pycodex/core/stream_events_utils.py` so output-text and reasoning delta plan helpers call `error_or_panic` when the event arrives without an active item.
- Kept non-streaming active items as silent skips.
- Kept tool-call input delta behavior unchanged: missing diff consumer returns no plan, matching Rust.
- Updated `tests/test_core_stream_events_utils.py` to assert the Rust panic/log branch for missing active items.
- Updated one turn-runtime TTFT fixture to use the Rust stream order (`output_item_added` before `output_text_delta`).

## Validation

- `python -m py_compile pycodex/core/stream_events_utils.py tests/test_core_stream_events_utils.py`
- `python -m py_compile pycodex/core/stream_events_utils.py tests/test_core_stream_events_utils.py tests/test_core_turn_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_stream_events_utils.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_records_ttft_from_stream_events -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py tests/test_core_client.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_http_transport.py tests/test_core_turn_timing.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_stream_events_utils.py tests/test_core_http_transport.py tests/test_core_turn_timing.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`

Full smoke gate was rerun after an isolated `doctor --json` failure passed on single-test retry. Final smoke result: `744 passed, 1 skipped, 98 subtests passed`.

## Known gaps

- This slice only aligns stream delta missing-active-item behavior. Broader session turn loop parity remains ongoing.
