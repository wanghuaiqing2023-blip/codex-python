# 2026-06-06 - canonical migration batch 30: plugin rendering and context manager updates

## Purpose

Move the last two clear root-level Python modules into Rust-aligned core subpackage coordinates.

## Rust source anchors

- `codex/codex-rs/core/src/plugins/render.rs`
- `codex/codex-rs/core/src/context_manager/updates.rs`

## Python canonical targets

- `pycodex/core/plugins/render.py`
- `pycodex/core/context_manager/updates.py`

## Moved from old paths

- `pycodex/core/app_plugin_rendering.py`
- `pycodex/core/context_updates.py`

## Result

Plugin/app instruction rendering now lives under `pycodex/core/plugins/`, matching the upstream plugin render module. Context update construction now lives under `pycodex/core/context_manager/`, matching the upstream context manager updates module.

## Validation

- Residual old import search across `pycodex/` and `tests/`: clean.
- Canonical module import smoke: passed.
- Focused adjacent test command:
  - `python -m pytest tests/test_core_context_updates.py tests/test_core_context.py tests/test_core_plugin_mentions.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_http_transport.py`
- Result: `286 passed`.

## Scope note

This batch only moves coordinates and rewrites imports. `pycodex/core/http_transport.py` remains in place because it is a Python-specific stdlib HTTP transport adapter without a direct Rust file coordinate.
