# Tool Event Stage And Review Decision Boundaries

## Scope

- Continued the graph-guided core runtime path around tool dispatch, approval decisions, and user-facing tool events.
- Focused on shared boundaries used by shell/unified exec/apply-patch event emission and approval orchestration.

## Upstream Graph/Source Slice

- Graph-guided files used:
  - `codex-rs/core/src/tools/events.rs`
  - `codex-rs/protocol/src/protocol.rs`
  - `codex-rs/core/src/session/handlers.rs`
- Rust source confirmed:
  - `ToolEventStage` is a three-variant enum: `Begin`, `Success { output, applied_patch_delta }`, and `Failure(ToolEventFailure)`.
  - Success stages carry output and optional patch delta but never a failure payload; begin stages carry no payload.
  - `ReviewDecision` variants are keyed by their snake-case variant names, and approval orchestration needs the decision kind independent of payload data.

## Python Changes

- `pycodex/core/tool_events.py`
  - Reworked `ToolEventStage` construction so the Python `failure` classmethod no longer collides with the instance `failure` field default.
  - Preserved the existing public constructors `begin()`, `success()`, and `failure()` while restoring the Rust-like enum validation rules.
- `pycodex/protocol/approvals.py`
  - Added a `ReviewDecision.kind` compatibility property backed by `type`, matching downstream approval orchestration expectations.

## Validation

- `python -m unittest tests.test_core_tool_orchestrator tests.test_core_tool_events`
  - 29 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_core_unified_exec_handler tests.test_core_shell_handler`
  - 86 tests passed, 1 skipped.
- `python -m unittest discover -s tests -p "test_protocol_*.py"`
  - 300 tests passed.
- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 502 tests passed, 1 skipped.

## Follow-up Debt

- Broader whole-suite discovery still needs a separate pass because the workspace contains many actively modified modules and extension-area tests outside the current core slice.
