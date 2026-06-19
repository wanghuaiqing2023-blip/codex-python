# codex-collaboration-mode-templates test alignment

Rust crate: `codex-collaboration-mode-templates`

Python package: `pycodex/collaboration_mode_templates`

Status: `complete`

Certified modules:

- `codex/codex-rs/collaboration-mode-templates/src/lib.rs` -> `pycodex/collaboration_mode_templates/__init__.py`

Source-contract coverage:

- `PLAN` equals `include_str!("../templates/plan.md")`.
- `DEFAULT` equals `include_str!("../templates/default.md")`.
- `EXECUTE` equals `include_str!("../templates/execute.md")`.
- `PAIR_PROGRAMMING` equals `include_str!("../templates/pair_programming.md")`.
- the Python public surface exposes exactly those four constants.

Validation:

- `python -m pytest tests/test_collaboration_mode_templates_lib_rs.py -q`
- `python -m py_compile pycodex/collaboration_mode_templates/__init__.py tests/test_collaboration_mode_templates_lib_rs.py`
