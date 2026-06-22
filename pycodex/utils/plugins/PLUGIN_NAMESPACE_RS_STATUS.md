# codex-utils-plugins src/plugin_namespace.rs status

Rust coordinate: `codex/codex-rs/utils/plugins/src/plugin_namespace.rs`

Python coordinate: `pycodex/utils/plugins/plugin_namespace.py`

Status: `complete`

Behavior contract:

- discover `.codex-plugin/plugin.json` before `.claude-plugin/plugin.json`.
- return the manifest path only when the candidate is a file.
- walk the skill path and ancestors to find the nearest plugin manifest.
- read the manifest `name` field and fall back to the plugin root directory name when it is blank.
- return no namespace for missing, unreadable, invalid, or non-object manifests.

Evidence:

- `tests/test_utils_plugins_plugin_namespace.py` mirrors Rust tests `uses_manifest_name` and `uses_name_from_alternate_discoverable_manifest_path`.
- Additional source-contract cases cover blank-name fallback and invalid/missing manifests.
- Actual test execution is deferred until the remaining crate module is certified.
