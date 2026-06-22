# codex-collaboration-mode-templates src/lib.rs status

Rust coordinate: `codex/codex-rs/collaboration-mode-templates/src/lib.rs`

Python coordinate: `pycodex/collaboration_mode_templates/__init__.py`

Status: `complete`

Behavior contract:

- expose `PLAN`, `DEFAULT`, `EXECUTE`, and `PAIR_PROGRAMMING` constants.
- each constant preserves the exact Markdown template text included by Rust's `include_str!`.
- no extra runtime behavior is owned by this crate.

Evidence:

- `tests/test_collaboration_mode_templates_lib_rs.py` compares each Python constant against the corresponding Rust template file and checks the public constant surface.
