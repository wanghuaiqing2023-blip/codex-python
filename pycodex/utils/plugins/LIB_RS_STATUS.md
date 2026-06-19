# codex-utils-plugins src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/plugins/src/lib.rs`

Python coordinate: `pycodex/utils/plugins/__init__.py`

Status: `complete`

Behavior contract:

- crate root exposes the `mcp_connector`, `mention_syntax`, and `plugin_namespace` module surfaces.
- crate root re-exports `find_plugin_manifest_path` and `plugin_namespace_for_skill_path`.
- `PluginSkillRoot` carries `path`, `plugin_id`, and `plugin_root` fields with equality/hash semantics.

Evidence:

- `tests/test_utils_plugins_lib.py` covers the crate-root public surface and `PluginSkillRoot` shape.
- `tests/test_utils_plugins_mcp_connector.py`, `tests/test_utils_plugins_plugin_namespace.py`, and `tests/test_core_mention_syntax.py` cover child module behavior.
