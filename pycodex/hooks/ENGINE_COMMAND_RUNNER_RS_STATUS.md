# codex-hooks src/engine/command_runner.rs Status

Rust crate: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/command_runner.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Anchors

- `CommandRunResult`
- `run_command(...)`
- `build_command(...)`
- `default_shell_command(...)`

## Python Coverage

- `tests/test_hooks_engine_command_runner_rs.py` covers default shell argv
  construction, custom shell args plus handler command ordering, cwd/stdin
  piping, stdout/stderr capture, handler environment overlay, exit-code
  capture, spawn-error projection, timeout killing/error text, and
  timestamp/duration fields.

## Validation

- `python -m pytest tests/test_hooks_engine_command_runner_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- Hooks module validation including command runner passed on 2026-06-21 with
  `138 passed`.
- Hooks plus core-hooks regression validation including command runner passed
  on 2026-06-21 with `161 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_command_runner_rs.py`
  passed.

## Remaining Debt

- None for this module-scoped behavior contract. Sibling `src/engine/*`
  discovery and engine facade modules remain separate `codex-hooks`
  crate-level gaps.
