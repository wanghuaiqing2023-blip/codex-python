# 2026-06-05 canonical crate migration batch 7: core-skills

## Scope

Move already-implemented Python helper behavior for Rust crate `codex-core-skills` into the canonical package `pycodex/core_skills`.

## Rust source coordinate

- `codex/codex-rs/core-skills/src/config_rules.rs`
- `codex/codex-rs/core-skills/src/injection.rs`
- `codex/codex-rs/core-skills/src/invocation_utils.rs`
- `codex/codex-rs/core-skills/src/mention_counts.rs`
- `codex/codex-rs/core-skills/src/render.rs`

## Python target coordinate

- `pycodex/core_skills/config_rules.py`
- `pycodex/core_skills/injections.py`
- `pycodex/core_skills/invocation_utils.py`
- `pycodex/core_skills/mentions.py`
- `pycodex/core_skills/rendering.py`

## Migration policy

This is a canonical-coordinate migration for existing helper behavior, not a deep implementation of deferred extension runtime features. The old `pycodex/core/skill_*` files remain only until focused validation passes and are expected to be deleted immediately afterward.

## Validation before deleting old coordinates

- `python -m pytest tests/test_core_skills.py tests/test_core_skill_config_rules.py tests/test_core_skill_injections.py tests/test_core_skill_invocation_utils.py tests/test_core_skill_mentions.py tests/test_core_skill_rendering.py -q`: 62 passed.
- Import smoke for `pycodex.core_skills.*`, `pycodex.core.skills`, and `pycodex.core.turn_runtime`: passed.

## Old coordinate deletion

Deleted the former `pycodex/core/skill_*` module files after validation.

## Validation after deleting old coordinates

- Focused tests: 62 passed.
- Import smoke after deletion: passed.
- Residual old-coordinate check: no matches for `pycodex.core.skill_*` imports.
