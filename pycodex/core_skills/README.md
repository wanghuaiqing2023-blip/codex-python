# pycodex.core_skills

Canonical Python package for helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/core-skills`
- Python package: `pycodex/core_skills`

## Module correspondence

| Rust behavior area | Python module |
| --- | --- |
| `config_rules.rs` | `pycodex/core_skills/config_rules.py` |
| `injection.rs` | `pycodex/core_skills/injections.py` |
| `invocation_utils.rs` | `pycodex/core_skills/invocation_utils.py` |
| `mention_counts.rs` / explicit mention helpers | `pycodex/core_skills/mentions.py` |
| `render.rs` | `pycodex/core_skills/rendering.py` |

This package is intentionally scoped to already-ported helper behavior. Deep MCP/plugin/marketplace runtime behavior remains outside the active core target unless the common CLI/runtime path needs a compatibility surface.
