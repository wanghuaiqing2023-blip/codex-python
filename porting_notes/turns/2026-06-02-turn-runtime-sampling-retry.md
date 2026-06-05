# Turn Runtime Sampling Retry

## Upstream graph/source slice

- Used `codex/.understand-anything/knowledge-graph.json` to navigate the core turn path:
  - `codex-rs/core/src/session/turn.rs#run_turn`
  - `codex-rs/core/src/session/turn.rs#run_sampling_request`
  - `codex-rs/core/src/responses_retry.rs#handle_retryable_response_stream_error`
- Confirmed from Rust source that sampling requests retry retryable stream errors up to the provider's `stream_max_retries`, notify the UI when retrying, and then rebuild/reuse the prompt loop rather than treating a transient stream disconnect as a terminal turn error.

## Python changes

- `pycodex/core/turn_runtime.py`
  - Added `_sample_with_retry` for injected sampler paths used by the Python turn runtime skeleton.
  - Initial sampling and tool follow-up sampling now both retry retryable `CodexErr` values using the existing Rust-shaped `response_stream_retry_decision` helper.
  - Added local provider `stream_max_retries` parsing with the same default/cap behavior used by the HTTP sampling path.
  - Retry notifications call `sess.notify_stream_error(...)` when available, or emit a `stream_error` event fallback.
  - Tests can override retry sleeping with `sess.sleep_for_sampling_retry(...)`; production falls back to `asyncio.sleep`.
- `tests/test_core_turn_runtime.py`
  - Added session hooks for stream-error and retry-sleep capture.
  - Added coverage for one retryable stream failure followed by a successful assistant response.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_retries_retryable_stream_error tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_responses_retry tests.test_core_turn_sampler`
- `python -m compileall -q pycodex`

## Known gaps

- This implements retry for the injected Python sampler path without fallback transport switching, because that path does not own a `ModelClientSession` transport stack. The lower HTTP sampler still covers transport fallback behavior.
- Broader real-network retry smoke testing remains future work once the core runtime is ready for controlled end-to-end API runs.
