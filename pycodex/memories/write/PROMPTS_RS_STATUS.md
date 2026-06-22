# codex-memories-write src/prompts.rs Status

Rust crate: `codex-memories-write`
Rust module: `src/prompts.rs`
Python module: `pycodex.memories.write`

## Status

`complete_slice`

## Evidence

- Rust source: `codex/codex-rs/memories/write/src/prompts.rs`
- Rust tests: `codex/codex-rs/memories/write/src/prompts_tests.rs`
- Rust templates: `codex/codex-rs/memories/write/templates/memories/stage_one_input.md`, `codex/codex-rs/memories/write/templates/memories/consolidation.md`
- Python tests: `tests/test_memories_write_prompts_rs.py`

## Covered Contracts

- `build_stage_one_input_message` renders rollout path, cwd, and truncated rollout contents through the embedded stage-one template.
- Stage-one rollout truncation uses resolved context window, `effective_context_window_percent`, and `stage_one::CONTEXT_WINDOW_PERCENT`.
- Missing model context window falls back to `stage_one::DEFAULT_ROLLOUT_TOKEN_LIMIT`.
- `build_consolidation_prompt` points to `phase2_workspace_diff.md`.
- Consolidation prompt includes memory extension folder/input guidance only when the extensions directory exists.

## Open Outside This Module Slice

- Runtime phase-one request execution.
- Runtime phase-two consolidation agent orchestration.
- Workspace diff generation.
- Extension resource pruning/seeding behavior.
