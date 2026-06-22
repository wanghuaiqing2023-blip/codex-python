# pycodex.collaboration_mode_templates

Canonical Python package for the Rust template crate:

- Rust crate path: `codex/codex-rs/collaboration-mode-templates`
- Python package path: `pycodex/collaboration_mode_templates`

## Module Correspondence

| Rust module | Python module |
| --- | --- |
| `src/lib.rs` | `pycodex/collaboration_mode_templates/__init__.py` |

## Status

Status: complete.

The Rust crate exposes four `include_str!` constants backed by Markdown files:
`PLAN`, `DEFAULT`, `EXECUTE`, and `PAIR_PROGRAMMING`. Python keeps the same
public constant names and loads package-local template files that are byte-for-
byte copies of the Rust template files.

## Test Sources

Rust source:

```text
codex/codex-rs/collaboration-mode-templates/src/lib.rs
codex/codex-rs/collaboration-mode-templates/templates/*.md
```

Python parity tests:

```text
tests/test_collaboration_mode_templates_lib_rs.py
```
