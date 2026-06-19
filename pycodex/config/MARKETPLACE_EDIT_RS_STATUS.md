# codex-config `src/marketplace_edit.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/marketplace_edit.rs`

Python module: `pycodex/config/marketplace_edit.py`

Python tests: `tests/test_config_marketplace_edit.py`

## Behavior Contract

`src/marketplace_edit.rs` owns user marketplace config edits in
`$CODEX_HOME/config.toml`.

The Python port mirrors the module-scoped contract:

- `MarketplaceConfigUpdate` carries required update fields plus optional
  `last_revision`, `ref`, and `sparse_paths`.
- `record_user_marketplace()` creates or replaces a named marketplace entry and
  creates `CODEX_HOME` before writing.
- Existing non-table `marketplaces` values are replaced with a table on write.
- `remove_user_marketplace()` returns `true` only when removal happened.
- Missing config files and missing marketplace entries report not found.
- Name case mismatches are reported with the configured name.
- Table and inline-table marketplace entries can be removed.
- Removing the final marketplace removes the empty `marketplaces` table.

## Notes

The Python implementation uses the local dependency-light TOML compatibility
layer and a small serializer instead of `toml_edit::DocumentMut`. A narrow
fallback parser handles the multi-line inline table fixture used by the Rust
module test. Exact decoration preservation for arbitrary existing documents is
an intentional adaptation.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
