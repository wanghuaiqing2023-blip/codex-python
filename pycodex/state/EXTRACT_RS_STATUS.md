# codex-state `src/extract.rs`

Status: `complete`

Python module: `pycodex/state/extract.py`

## Scope

This pass mirrors the Rust rollout-to-thread-metadata mutation helpers:

- `apply_rollout_item`
- `rollout_item_affects_thread_metadata`
- `enum_to_string`
- user message title/preview extraction helpers
- image-only user message placeholder

## Rust Evidence

- Rust module: `codex/codex-rs/state/src/extract.rs`
- Rust tests cover:
  - response-item user messages do not set title or first user message
  - event user messages set title and first user message
  - image-only user messages use `[Image]`
  - blank user messages without images do not mutate preview/title
  - thread goals set preview only
  - session CWD wins over turn-context CWD
  - turn-context fills missing CWD, model, reasoning effort, sandbox, approval
  - session metadata does not set model or reasoning effort

## Python Evidence

- `pycodex.state.extract` mutates `ThreadMetadata` in place and ignores
  response/compacted rollout items.
- User-message prefix stripping, preview/title behavior, image-only placeholder,
  thread-goal preview, token count clamping, session metadata, Git metadata, and
  turn-context updates mirror the Rust module contract.
- The helpers accept both existing protocol dataclasses and mapping-shaped
  rollout/event payloads to stay compatible with parsed rollout surfaces.

## Deferred

- Reading rollout files and writing SQLite state remain owned by runtime/store
  modules.
- Response item extraction is intentionally a no-op, matching Rust.

## Validation

Formal parity validation:

```text
python -m pytest tests\test_state_extract_rs.py -q
# 11 passed

python -m py_compile pycodex\state\extract.py pycodex\state\__init__.py tests\test_state_extract_rs.py
```

Coverage ports the Rust module tests for response-item no-op behavior,
event-user-message title/preview/first-message extraction, image-only
placeholder handling, blank-message no-op behavior, thread-goal preview
precedence, session/turn CWD precedence, turn-context runtime fields, and
session metadata not setting model/reasoning effort. Additional coverage checks
token-count clamping/default-provider fill, `rollout_item_affects_thread_metadata`,
and user-message helper behavior.
