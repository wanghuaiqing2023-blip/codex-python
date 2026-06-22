# codex-config `src/plugin_edit.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/plugin_edit.rs`

Python module: `pycodex/config/plugin_edit.py`

Python tests: `tests/test_config_plugin_edit.py`

## Behavior Contract

`src/plugin_edit.rs` owns user plugin enablement edits in
`$CODEX_HOME/config.toml`.

The Python port mirrors the module-scoped contract:

- `PluginConfigEdit` represents `SetEnabled` and `Clear` edit operations.
- `set_user_plugin_enabled()` writes `[plugins."<plugin_key>"].enabled`.
- Existing plugin fields are preserved when toggling `enabled`.
- `clear_user_plugin()` removes the selected plugin entry.
- Removing the final plugin entry removes the empty `plugins` table.
- Clearing a missing plugin does not create a config file.
- Empty edit lists are no-ops.
- Ordered edit batches apply in order.

## Notes

Rust uses `toml_edit::DocumentMut`, symlink-aware write paths, and atomic
writes. The Python port keeps a dependency-light TOML mapping/serializer and
ordinary file writes. Existing-file symlink following is handled by the host
filesystem, while exact decoration preservation and atomic write-path
resolution remain documented adaptations for this module.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
