# 2026-06-02 Core Exec Path Coverage Check

## Graph-selected slice

- `codex-rs/exec/src/lib.rs`
  - `run_main`
  - `run_exec_session`
  - `resolve_resume_thread_id`
- `pycodex/exec/local_runtime.py`
  - `core_exec_enabled`
  - `local_http_exec_enabled`
- `pycodex/exec/core_runtime.py`
  - `build_default_core_exec_runtime`
  - `resolve_core_exec_resume_target`
  - `run_core_exec_command`
- `pycodex/cli/parser.py`
  - `_run_noninteractive_exec`

## Graph-informed check

- Traced the `exec` high-impact slice from graph nodes to Python call sites and confirmed the non-interactive selection flow is present:
  - core path is preferred when key env + auth conditions indicate it;
  - local HTTP path remains available as fallback;
  - both paths emit summaries and persist rollouts with different target handlers.
- Confirmed core resume logic maps to upstream intent for missing target cases:
  - if resume lookup fails, we now use a new-turn fallback path instead of immediate hard failure.
- Confirmed auth error shaping for core/local HTTP remains differentiated by error text at runtime boundary.

## Rust source checked

- `codex/.understand-anything/knowledge-graph.json` (targeted slices and call edges around `run_exec_session`)
- `codex/codex-rs/exec/src/lib.rs` (graph-indexed target functions)

## Python changes

- No behavior-affecting code changes in this turn.
- Recorded current verification state for the core slice and retained existing implementations as-is.

## Follow-up debt

- Add a small end-to-end smoke run for `codex exec` core path that exercises:
  - non-interactive `exec` with prompt-only input,
  - resume with missing or stale target,
  - `review` with API key defaulting path,
  - and error surfaces from both core and local-HTTP runtime builders.
