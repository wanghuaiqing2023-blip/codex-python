# codex-tools src/tool_output.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_output.rs`
Rust tests: none in `codex-tools`
Python module: `pycodex/tools/tool_output.py`
Python behavior implementation: `pycodex/core/tools/context.py`
Python tests: `tests/test_core_tool_context.py`, `tests/test_core_tool_registry.py`, `tests/test_core_tool_router.py`

## Behavior contract

`src/tool_output.rs` owns the model-facing output contract for executable tool
runtimes:

- `ToolOutput` requires `log_preview`, `success_for_logging`, and
  `to_response_item`.
- Default hook-facing methods expose call id, optional tool input, optional
  stable response payload, and code-mode conversion.
- `JsonToolOutput::new` defaults success to `Some(true)`.
- `JsonToolOutput::with_success` preserves explicit success, including `None`.
- `JsonToolOutput` serializes JSON values into function or custom tool outputs
  depending on `ToolPayload`, returns the raw value for post-tool-use response,
  and returns the raw value for code-mode result.
- `telemetry_preview` truncates output by byte and line budget with the Rust
  truncation notice.

## Python alignment

`pycodex.core.tools.context` already implements the shared Python `ToolOutput`
protocol, `JsonToolOutput`, boxed boundary validation, telemetry preview, and
the related concrete output classes used by runtime dispatch. The new
`pycodex.tools.tool_output` module re-exports the Rust-owned public anchors from
the canonical tools-crate package path while preserving a single shared runtime
type.

## Evidence

Existing Python coverage validates the Rust behavior contract:

- `tests/test_core_tool_context.py` covers boxed output validation,
  function/custom response conversion, `JsonToolOutput` success handling,
  post-tool-use response value, code-mode raw value, telemetry preview byte and
  line truncation, and related content-item conversion.
- `tests/test_core_tool_registry.py` and `tests/test_core_tool_router.py` cover
  downstream use of `ToolOutput` objects in registry, hook, router, telemetry,
  and code-mode paths.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
