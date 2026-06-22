# codex-tools src/tool_executor.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_executor.rs`
Rust tests: none in `codex-tools`
Python module: `pycodex/tools/tool_executor.py`
Python tests: `tests/test_core_tool_registry.py`, `tests/test_core_spec_plan.py`

## Behavior contract

`src/tool_executor.rs` owns the shared runtime contract for model-visible
tools:

- `ToolExposure` variants: `Direct`, `Deferred`, `DirectModelOnly`, `Hidden`.
- `ToolExposure::is_direct` for direct and direct-model-only variants.
- `ToolExecutor` default methods for `exposure` and
  `supports_parallel_tool_calls`, plus required `tool_name`, `spec`, and
  async `handle` contract.

## Python alignment

`pycodex.tools.tool_executor` exposes the canonical `codex-tools` package path
for this boundary. It reuses the existing core `ToolExposure` enum, whose
variants and `is_direct` behavior already back registry/spec planning, and
adds a `ToolExecutor` protocol with Rust-equivalent default methods.

## Evidence

Existing Python coverage in `tests/test_core_tool_registry.py` and
`tests/test_core_spec_plan.py` exercises `ToolExposure` variants, `is_direct`,
runtime exposure defaults, overrides, direct/deferred/hidden planning, and
parallel-call gating. Focused validation is deferred by the current crate
automation rule until `codex-tools` functional module code is complete.
