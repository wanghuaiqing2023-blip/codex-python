# 2026-06-05 canonical migration batch 9: utils/plugins mention syntax

## Scope

Move plaintext tool/plugin mention sigils from the old `pycodex.core` coordinate to the canonical utility package.

## Rust source coordinate

- `codex/codex-rs/utils/plugins/src/mention_syntax.rs`

## Python target coordinate

- `pycodex/utils/plugins/mention_syntax.py`

## Old Python coordinate

- `pycodex/core/mention_syntax.py`

## Migration policy

Keep the old file only until focused validation passes, then delete it to avoid dual coordinates.

## Validation before deleting old coordinate

- `python -m pytest tests/test_core_mention_syntax.py tests/test_core_plugin_mentions.py tests/test_core_skill_mentions.py -q`: 40 passed.
- Import smoke for `pycodex.utils.plugins.mention_syntax`, `pycodex.core.plugin_mentions`, and `pycodex.core_skills.mentions`: passed.

## Old coordinate deletion

Deleted `pycodex/core/mention_syntax.py` after focused validation.

## Validation after deleting old coordinate

- Focused tests: 40 passed.
- Import smoke after deletion: passed.
- Strict residual old-coordinate check: no matches for `pycodex.core.mention_syntax`.
