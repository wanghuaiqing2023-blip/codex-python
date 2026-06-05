# 2026-06-06 - canonical migration batch 31: http transport adapter package

## Purpose

Give the Python-specific HTTP/SSE transport adapter a dedicated package coordinate and README instead of forcing it into a misleading one-to-one Rust file mapping.

## Functional Rust source anchors

- `codex/codex-rs/core/src/client.rs`
- `codex/codex-rs/core/src/client_common.rs`
- `codex/codex-rs/core/src/responses_retry.rs`
- `codex/codex-rs/core/src/session/turn.rs`
- `codex/codex-rs/protocol/src/protocol.rs`

## Python canonical target

- `pycodex/core/http_transport/__init__.py`
- `pycodex/core/http_transport/README.md`

## Moved from old path

- `pycodex/core/http_transport.py`

## Result

The public import path remains `pycodex.core.http_transport`, but it is now backed by a dedicated package. The package README documents that this is not an unported root-level leftover. It is a Python stdlib compatibility adapter whose behavior corresponds to multiple Rust modules.

## Validation

- Package import smoke: passed.
- Old file absent, new package initializer and README present.
- Focused adjacent test command:
  - `python -m pytest tests/test_core_http_transport.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_exec_local_runtime.py`
- Result: `454 passed`.

## Scope note

No behavior split was performed. The package can be split later only if doing so improves maintainability without obscuring the adapter boundary.
