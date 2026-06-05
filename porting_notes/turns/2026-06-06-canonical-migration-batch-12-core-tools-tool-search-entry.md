# Canonical migration batch 12: core/tools/tool_search_entry

## Summary

Moved the remaining core tool-search entry conversion behavior from the old top-level core coordinate into the canonical Python package that mirrors Rust `codex-rs/core/src/tools`.

## Rust anchor

- `codex/codex-rs/core/src/tools/tool_search_entry.rs`

## Python canonical coordinate

- `pycodex/core/tools/tool_search_entry.py`
- `pycodex/core/tools/__init__.py`

## Deleted old coordinate

- `pycodex/core/tool_search_entry.py`

## Updated import policy

- Production imports now use `pycodex.core.tools.tool_search_entry`.
- Focused tests now import tool-search entry conversion helpers from `pycodex.core.tools.tool_search_entry`.
- `ToolSearchSourceInfo` remains in `pycodex.tools.tool_discovery`, matching the earlier tools/tool_discovery split.
- `pycodex.core` no longer re-exports `ToolSearchEntry`, `ToolSearchInfo`, `coalesce_loadable_tool_specs`, `default_namespace_description`, or `loadable_tool_spec_from_spec`.

## Validation

- Before deleting the old coordinate: `87 passed`
- Import smoke: passed
- After deleting the old coordinate: `87 passed`
- Old import residual check: no matches for `pycodex.core.tool_search_entry`

## Notes

This is a tree-coordinate migration, not a behavior rewrite. The purpose is to preserve the existing implementation while moving it into the same conceptual module position as the upstream Rust source.
