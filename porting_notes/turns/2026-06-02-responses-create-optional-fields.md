# 2026-06-02 - Responses create optional field serialization

## Scope

- Core path: HTTP/WebSocket Responses request payloads used by `exec` turn sampling.
- Upstream graph slice: `codex-rs/codex-api/src/common.rs#ResponsesApiRequest`, `#ResponseCreateWsRequest`, and `codex-rs/core/src/client.rs#build_responses_request`.

## Rust behavior confirmed

- `ResponsesApiRequest` skips empty `instructions`.
- It preserves top-level `reasoning: null` because `reasoning` is not marked with `skip_serializing_if`.
- It skips `service_tier`, `prompt_cache_key`, `text`, and `client_metadata` when absent.
- `ResponseCreateWsRequest` also skips absent `previous_response_id` and `generate`, while preserving `generate: false` for warmup requests.

## Python changes

- `pycodex.core.client.serialize_responses_request` now omits absent `previous_response_id` and `generate` in addition to existing optional request fields.
- `generate=False` is preserved.
- Added pytest-style coverage in `tests/test_core_client.py`; the environment currently lacks `pytest`, so the touched behavior was also validated with a stdlib assertion script.

## Validation

- Passed direct stdlib assertion script for optional field omission and `generate=False` preservation.
- Passed:
  - `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_run tests.test_exec_event_processor tests.test_core_tool_router tests.test_core_unified_exec_handler tests.test_core_view_image_handler tests.test_core_turn_request tests.test_core_session_runtime`
