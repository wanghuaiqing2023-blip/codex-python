# 2026-06-06 - canonical migration batch 26: agent/config/context/state core subpackages

## Purpose

Move clear root-level Python modules into Rust-aligned core subpackages, preserving previous implementation work while reducing duplicate or ambiguous coordinates.

## Rust source anchors

- `codex/codex-rs/core/src/agent/agent_resolver.rs`
- `codex/codex-rs/core/src/agent/control.rs`
- `codex/codex-rs/core/src/agent/registry.rs`
- `codex/codex-rs/core/src/agent/status.rs`
- `codex/codex-rs/core/src/config/agent_roles.rs`
- `codex/codex-rs/core/src/config/edit.rs`
- `codex/codex-rs/core/src/context/mod.rs`
- `codex/codex-rs/core/src/context/permissions_instructions.rs`
- `codex/codex-rs/core/src/state/auto_compact_window.rs`

## Python canonical targets

- `pycodex/core/agent/agent_resolver.py`
- `pycodex/core/agent/control.py`
- `pycodex/core/agent/registry.py`
- `pycodex/core/agent/status.py`
- `pycodex/core/config/agent_roles.py`
- `pycodex/core/config/edit.py`
- `pycodex/core/context/__init__.py`
- `pycodex/core/context/permissions_instructions.py`
- `pycodex/core/state/auto_compact_window.py`

## Moved from old paths

- `pycodex/core/agent_resolver.py`
- `pycodex/core/agent_control.py`
- `pycodex/core/agent_registry.py`
- `pycodex/core/agent_status.py`
- `pycodex/core/agent_roles.py`
- `pycodex/core/config_edit.py`
- `pycodex/core/context.py`
- `pycodex/core/permissions_instructions.py`
- `pycodex/core/auto_compact_window.py`

## Context package conversion

`permissions_instructions.py` maps to Rust `core/src/context/permissions_instructions.rs`. Python could not safely place it under `pycodex/core/context/` while `pycodex/core/context.py` existed as a sibling module. Therefore this batch converts the old `context.py` file into `pycodex/core/context/__init__.py`, keeping `pycodex.core.context` imports stable while allowing submodules below that package.

## Validation

- Canonical module import smoke: passed.
- Old selected file path check: old files absent, new files present.
- Residual old import search: no old module-path leakage; one harmless top-level re-export import false positive (`agent_status_from_event`).
- Focused adjacent test command:
  - `python -m pytest tests/test_core_agent_control.py tests/test_core_agent_registry.py tests/test_core_agent_resolver.py tests/test_core_agent_roles.py tests/test_core_agent_status.py tests/test_core_auto_compact_window.py tests/test_core_config_edit.py tests/test_core_context.py tests/test_core_context_updates.py tests/test_core_permissions_instructions.py tests/test_core_realtime_context.py tests/test_core_request_permissions_handler.py tests/test_core_request_plugin_install_handler.py tests/test_core_session_runtime.py`
- Result: `266 passed, 1 skipped`.

## Scope note

This is a coordinate consolidation batch. It preserves existing behavior and imports while placing modules under Rust-aligned package coordinates.
