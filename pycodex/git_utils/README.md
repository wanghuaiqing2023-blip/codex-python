# pycodex.git_utils

Python counterpart for Rust crate `codex-git-utils`.

## Rust Counterpart

```text
Rust crate: codex-git-utils
Rust path: codex/codex-rs/git-utils
```

## Module Mapping

| Rust module/file | Python module/file | Status |
|---|---|---|
| `src/info.rs` | `pycodex/git_utils/__init__.py` | `complete_slice` for remote URL canonicalization |
| `src/branch.rs` | `pycodex/git_utils/__init__.py` | `complete_slice` for merge-base behavior |
| `src/apply.rs` | `pycodex/git_utils/__init__.py` | `complete` for patch path extraction, git-apply output parsing, and repository apply/revert scenarios |

The current Python implementation is consolidated in `__init__.py`; keep this
mapping documented until or unless the package is split to mirror Rust files.

`codex-git-utils` is strict complete as of 2026-06-15. Focused validation
passed with `17 passed, 7 subtests passed` in `tests/test_core_git_info.py`.
