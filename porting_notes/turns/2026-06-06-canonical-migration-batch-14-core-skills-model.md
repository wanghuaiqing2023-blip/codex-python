# Canonical migration batch 14: core-skills model split

## Summary

Moved skill model definitions out of the MCP dependency helper module and into the canonical `core_skills` model coordinate.

## Rust anchors and Python coordinates

| Rust anchor | Python coordinate |
|---|---|
| `codex/codex-rs/core-skills/src/model.rs` | `pycodex/core_skills/model.py` |
| `codex/codex-rs/core/src/mcp_skill_dependencies.rs` | `pycodex/core/mcp_skill_dependencies.py` |
| `codex/codex-rs/core/src/skills.rs` | `pycodex/core/skills.py` |

## Moved model definitions

- `SkillMetadata`
- `SkillDependencies`
- `SkillToolDependency`

## Import policy

- Canonical definition import: `pycodex.core_skills.model`
- Core MCP dependency module import: `pycodex.core.mcp_skill_dependencies` only for MCP dependency behavior.
- Core skills facade import: `pycodex.core.skills` may re-export `SkillMetadata`, matching Rust `core/src/skills.rs`.
- Root `pycodex.core` no longer exports these model definitions.

## Validation

- Focused validation: `72 passed`
- Import smoke: passed
- Residual check: model classes are defined only in `pycodex/core_skills/model.py`

## Notes

This batch is a definition-coordinate split, not a behavior rewrite. The goal is to make the Python tree mirror Rust's distinction between `core-skills` model data and `core` MCP dependency behavior.
