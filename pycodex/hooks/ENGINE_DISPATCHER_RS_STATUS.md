# codex-hooks src/engine/dispatcher.rs Status

Rust crate: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/dispatcher.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Anchors

- `ParsedHandler`
- `select_handlers(...)`
- `select_handlers_for_matcher_inputs(...)`
- `running_summary(...)`
- `completed_summary(...)`
- `scope_for_event(...)`
- `execute_handlers(...)`

## Python Coverage

- `tests/test_hooks_engine_dispatcher_rs.py` mirrors the Rust dispatcher
  selection tests for duplicate stop handlers, overlapping SessionStart
  matchers, compact trigger matching, tool-name matching, `*` matching,
  regex alternation, alias matching once per handler, UserPromptSubmit matcher
  ignoring, and declaration-order preservation.
- The same test file covers source contracts for scope mapping, running and
  completed summary projection, and `execute_handlers(...)` completion-order
  assignment with declaration-order return ordering.

## Validation

- `python -m pytest tests/test_hooks_engine_dispatcher_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- Hooks module validation including this file passed on 2026-06-21 with
  `133 passed`.
- Hooks plus core hooks regression validation including this file passed on
  2026-06-21 with `156 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_dispatcher_rs.py`
  passed on 2026-06-21.

## Remaining Debt

- None for this module-scoped behavior contract. Sibling `src/engine/*`
  command runner, discovery, and engine facade modules remain separate
  `codex-hooks` crate-level gaps.
