# 2026-06-02 Core runtime tool argument finish event

## Upstream behavior

- `codex-rs/core/src/session/turn.rs::try_run_sampling_request` keeps an
  active tool argument diff consumer for streamed custom tool inputs.
- On `ResponseEvent::OutputItemDone`, Rust calls `consumer.finish()` via
  `active_tool_argument_diff_consumer.take()` and sends the returned event
  before handling the completed output item.
- This makes streamed tool argument displays, such as apply-patch input
  previews, receive a terminal event instead of only deltas.

## Python port progress

- The Python stream planner already produced
  `SamplingOutputItemDoneTransitionPlan.finished_tool_input_event`, but the
  runtime state application did not emit it.
- Updated `pycodex.core.client` so output-item-done application:
  - appends the finished tool-input event to emitted stream events;
  - clears the active tool argument diff consumer, matching Rust's `take()`;
  - records whether a finish event was present in the state summary.
- Updated core turn runtime coverage so the fake diff consumer emits both the
  streamed delta and the terminal tool-input event.

## Validation

- `python -m py_compile pycodex/core/client.py tests/test_core_client.py tests/test_core_turn_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_projects_sampler_stream_events tests/test_core_stream_events_utils.py::CoreStreamEventsUtilsTests::test_sampling_output_item_done_transition_plan_finishes_consumer_and_flushes_agent -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_client.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
