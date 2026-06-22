# codex-hooks src/engine/output_parser.rs Status

Rust crate: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/output_parser.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Anchors

- `UniversalOutput`, `SessionStartOutput`, `PreToolUseOutput`,
  `PermissionRequestOutput`, `PostToolUseOutput`,
  `UserPromptSubmitOutput`, `StopOutput`, `PreCompactOutput`, and
  `StatelessHookOutput`.
- Parser entry points `parse_session_start`, `parse_subagent_start`,
  `parse_pre_tool_use`, `parse_permission_request`, `parse_post_tool_use`,
  `parse_pre_compact`, `parse_post_compact`, `parse_user_prompt_submit`,
  `parse_stop`, `parse_subagent_stop`, and `looks_like_json`.
- Unsupported/invalid decision helpers for PreToolUse, PermissionRequest, and
  PostToolUse stdout JSON output.

## Python Coverage

- `tests/test_hooks_engine_output_parser_rs.py` mirrors the Rust
  PermissionRequest reserved-field tests and source contracts for serde-like
  object/enum rejection, universal output projection, PreToolUse
  hook-specific versus legacy decisions, PermissionRequest default deny
  messages, PostToolUse invalid block reasons, and start/stop/user-prompt
  output structures.

## Validation

- `python -m pytest tests/test_hooks_engine_output_parser_rs.py -q --tb=short`
  passed on 2026-06-21 with `6 passed`.
- Hooks module validation including this file passed on 2026-06-21 with
  `122 passed`.
- Hooks plus core hooks regression validation including this file passed on
  2026-06-21 with `145 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_output_parser_rs.py`
  passed on 2026-06-21.

## Remaining Debt

- None for this module-scoped behavior contract. Sibling `src/engine/*`
  dispatcher/discovery/runner modules remain separate `codex-hooks`
  crate-level gaps.
