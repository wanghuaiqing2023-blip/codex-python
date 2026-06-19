# codex-tools src/function_call_error.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/function_call_error.rs`
Rust tests: none in `codex-tools`
Python module: `pycodex/tools/function_call_error.py`
Python behavior implementation: `pycodex/core/function_tool.py`
Python tests: `tests/test_core_function_tool.py`, `tests/test_core_tool_router.py`, `tests/test_core_stream_events_utils.py`

## Behavior contract

`src/function_call_error.rs` owns the shared error type returned while executing
model-visible tool invocations:

- `RespondToModel(String)` formats as the contained message and marks a
  recoverable model-visible tool failure.
- `Fatal(String)` formats as `Fatal error: {message}` and marks an internal
  fatal tool failure.
- Core re-exports this tools-crate error type so routers, handlers, and stream
  response helpers share one boundary.

## Python alignment

`pycodex.core.function_tool` already implements the shared Python
`FunctionCallError` type used by the router and stream layers. The new
`pycodex.tools.function_call_error` module re-exports that exact type from the
canonical tools-crate package path, avoiding duplicate exception classes while
matching Rust ownership.

## Evidence

Existing Python coverage validates the Rust behavior contract:

- `tests/test_core_function_tool.py` covers `respond_to_model`, `fatal`, and
  fatal string formatting.
- `tests/test_core_tool_router.py` covers non-string constructor guards and
  fatal incompatible-payload formatting.
- `tests/test_core_stream_events_utils.py` covers model-visible versus fatal
  error handling in response conversion.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
