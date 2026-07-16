# pycodex.ext.goal

Rust crate: `codex-goal-extension`

Rust anchor: `codex/codex-rs/ext/goal`

`extension.py` owns contributor installation and lifecycle routing. Existing
validated Goal persistence helpers and tool handlers are exposed through the
Rust-coordinate modules while `pycodex.core.goals` and
`pycodex.core.tools.handlers.goal` remain documented compatibility import
paths. Product runtime registration is owned by `GoalExtension`.
