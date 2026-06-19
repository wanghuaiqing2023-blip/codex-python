# codex-utils-plugins test alignment

Rust crate: `codex-utils-plugins`

Python package: `pycodex/utils/plugins`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/plugins/src/mention_syntax.rs` -> `pycodex/utils/plugins/mention_syntax.py`
- `codex/codex-rs/utils/plugins/src/mcp_connector.rs` -> `pycodex/utils/plugins/mcp_connector.py`
- `codex/codex-rs/utils/plugins/src/plugin_namespace.rs` -> `pycodex/utils/plugins/plugin_namespace.py`
- `codex/codex-rs/utils/plugins/src/lib.rs`

Source-contract coverage added for `src/mention_syntax.rs`:

- `TOOL_MENTION_SIGIL` is `$`.
- `PLUGIN_TEXT_MENTION_SIGIL` is `@`.

Source-contract coverage added for `src/mcp_connector.rs`:

- default originator connector id deny-list.
- first-party chat connector id deny-list.
- connector name sanitization and empty-name fallback.

Rust-test/source-contract coverage added for `src/plugin_namespace.rs`:

- `uses_manifest_name`.
- `uses_name_from_alternate_discoverable_manifest_path`.
- blank manifest name fallback to the plugin root directory name.
- missing or invalid manifests return no namespace.

Source-contract coverage added for `src/lib.rs`:

- crate-root child module utility surface.
- `find_plugin_manifest_path` and `plugin_namespace_for_skill_path` re-export surface.
- `PluginSkillRoot` field shape, equality, hashing, and `plugin_id` typing.

Validation:

- `python -m pytest tests/test_core_mention_syntax.py tests/test_utils_plugins_mcp_connector.py tests/test_utils_plugins_plugin_namespace.py tests/test_utils_plugins_lib.py -q`
- `python -m py_compile pycodex/utils/plugins/__init__.py pycodex/utils/plugins/mcp_connector.py pycodex/utils/plugins/mention_syntax.py pycodex/utils/plugins/plugin_namespace.py tests/test_core_mention_syntax.py tests/test_utils_plugins_mcp_connector.py tests/test_utils_plugins_plugin_namespace.py tests/test_utils_plugins_lib.py`
