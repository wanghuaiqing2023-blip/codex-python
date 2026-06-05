# 2026-06-02 Core runtime stream metadata side effects

## Upstream behavior

- `codex-rs/core/src/session/turn.rs::try_run_sampling_request` applies
  streamed metadata events while handling a model response:
  - `ServerModel` calls `maybe_warn_on_server_model_mismatch` once.
  - `ModelVerifications` calls `emit_model_verification` once.
  - `ServerReasoningIncluded`, `RateLimits`, and `ModelsEtag` update session
    state used by later token-count and model-cache behavior.

## Python port progress

- The Python stream planner already represented `server_model` and
  `model_verifications` as metadata apply plans, but only
  `server_reasoning_included`, `rate_limits`, and `models_etag` had concrete
  session side effects.
- Added stream metadata side-effect application for `server_model` and
  `model_verifications` in `pycodex.core.turn_runtime`, preserving the Rust
  one-shot behavior and retaining the existing metadata summary.
- Added core turn runtime coverage for streamed server model warnings and model
  verification emission across a tool follow-up turn, so old stream metadata is
  not replayed during the follow-up request.

## Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_applies_stream_server_model_and_verification_metadata tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_applies_stream_metadata_to_session tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_applies_stream_completed_usage_to_session -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
