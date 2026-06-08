# pycodex.core.tasks

Rust counterpart:

```text
Rust crate: codex-core
Rust module path: codex/codex-rs/core/src/tasks
```

This package carries module-scoped task helpers. It does not represent full
task scheduling parity for `tasks/mod.rs`; large task orchestration remains a
separate runtime boundary.

Current mappings:

- `compact.py` -> `codex/codex-rs/core/src/tasks/compact.rs`
- `lifecycle.py` -> `codex/codex-rs/core/src/tasks/lifecycle.rs`
- `regular.py` -> `codex/codex-rs/core/src/tasks/regular.rs`
- `review.py` -> `codex/codex-rs/core/src/tasks/review.rs`
