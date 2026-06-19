# codex-config `src/skills_config.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/skills_config.rs`

Python module: `pycodex/config/skills_config.py`

Python tests: `tests/test_config_skills_config.py`

## Behavior Contract

`src/skills_config.rs` owns the serializable skill-related config shapes that
are re-exported through `codex-config`: `SkillConfig`, `SkillsConfig`, and
`BundledSkillsConfig`.

The Python port mirrors the module-scoped contract:

- `BundledSkillsConfig` defaults `enabled` to `true`.
- `SkillsConfig` defaults `bundled` and `include_instructions` to absent and
  `config` to an empty list.
- `SkillConfig` accepts path-based or name-based selectors.
- `SkillConfig.enabled` is required during deserialization, matching the Rust
  field with no `serde(default)`.
- All three shapes reject unknown fields like the Rust `deny_unknown_fields`
  schema/serde contract.
- Invalid field shapes are rejected before constructing effective config
  values.

## Notes

This module only owns config data shapes and deserialization behavior. Skill
discovery, rendering, invocation, plugin-provided skills, and marketplace or
remote skill behavior belong to sibling crates/modules and remain outside this
module boundary.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
