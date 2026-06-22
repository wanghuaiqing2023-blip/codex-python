# codex-memories-write src/extensions

Rust crate: `codex-memories-write`
Rust modules: `src/extensions/mod.rs`, `src/extensions/ad_hoc.rs`, `src/extensions/prune.rs`
Python package: `pycodex.memories.write`

## Status

`complete_slice`

## Rust Anchors

- `seed_extension_instructions`
- `ad_hoc::seed_instructions`
- `prune_old_extension_resources`
- `prune_old_extension_resources_with_now`
- `resource_timestamp`

## Covered Contract

- Seeds the `extensions/ad_hoc/instructions.md` file from the Rust template.
- Preserves existing customized ad-hoc instructions by using create-new
  semantics.
- Prunes only timestamped markdown files under `<extension>/resources`.
- Prunes only extensions that have an `instructions.md` file.
- Uses the Rust timestamp prefix format `%Y-%m-%dT%H-%M-%S` and seven-day
  retention cutoff.

## Python Tests

- `tests/test_memories_write_extensions_rs.py::test_seeds_instructions_without_overwriting_existing_file`
- `tests/test_memories_write_extensions_rs.py::test_prunes_only_old_resources_from_extensions_with_instructions`
- `tests/test_memories_write_extensions_rs.py::test_parses_timestamp_prefix_from_resource_file_name`

## Validation

2026-06-22:

- `python -m pytest tests\test_memories_write_extensions_rs.py tests\test_memories_write_workspace_rs.py tests\test_memories_write_control_rs.py tests\test_memories_write_guard_rs.py tests\test_memories_write_prompts_rs.py tests\test_memories_write_storage_rs.py -q --tb=short`
  - `18 passed, 1 skipped`

## Remaining Outside This Module

- Startup orchestration in `src/start.rs`.
- Phase 1 and phase 2 live model/runtime flows.
- State DB integration and live backend rate-limit fetch.
