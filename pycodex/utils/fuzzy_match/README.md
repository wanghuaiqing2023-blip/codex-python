# pycodex.utils.fuzzy_match

Python counterpart for the Rust `codex-utils-fuzzy-match` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-fuzzy-match
Rust path: codex/codex-rs/utils/fuzzy-match
Cargo role: simple case-insensitive subsequence matcher for fuzzy filtering
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/fuzzy_match/__init__.py` | crate public function and inline tests |

## Alignment Unit

The acceptance unit is a pure function behavior contract:

```text
utils.fuzzy_match.case_insensitive_subsequence
utils.fuzzy_match.original_character_indices
utils.fuzzy_match.lowercase_expansion_mapping
utils.fuzzy_match.score_window_and_prefix_bonus
utils.fuzzy_match.empty_needle_max_score
```

## Current Status

Status: module_completed_with_focused_validation.

The Python implementation mirrors Rust's public `fuzzy_match` helper: it matches
the lowercased needle as a subsequence of a lowercased haystack, maps matches
back to original haystack character indices for highlighting, deduplicates
indices when lowercase expansion maps multiple chars to one original character,
and computes the same lower-is-better score with the prefix bonus.

## Test Sources

Primary Python parity tests:

```text
tests/test_utils_fuzzy_match.py
```

Rust source/test anchors:

```text
codex/codex-rs/utils/fuzzy-match/src/lib.rs
```

## Stop Rule

This module contract is complete once `tests/test_utils_fuzzy_match.py` passes.
Do not expand into app-server fuzzy file search or TUI filtering unless a future
core slice explicitly targets those runtime paths.
