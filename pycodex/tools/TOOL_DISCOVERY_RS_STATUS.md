# codex-tools src/tool_discovery.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/tool_discovery.rs`
Rust tests: `codex/codex-rs/tools/src/tool_discovery_tests.rs`
Python module: `pycodex/tools/tool_discovery.py`
Python tests: `tests/test_core_tool_discovery.py`

## Behavior contract

`src/tool_discovery.rs` owns the dependency-light discoverable tool data contract:

- tool-name constants for `tool_search`, `list_available_plugins_to_install`,
  and `request_plugin_install`;
- `DiscoverableToolType` and `DiscoverableToolAction` snake_case wire names;
- connector/plugin `DiscoverableTool` wrappers and accessors for type, id, name,
  and connector-only install URL;
- `filter_request_plugin_install_discoverable_tools_for_client`, where the
  `codex-tui` client omits plugin suggestions and other clients preserve all
  tools;
- `DiscoverablePluginInfo`, `RequestPluginInstallEntry`, and
  `ListAvailablePluginsToInstallResult`;
- `collect_request_plugin_install_entries`, including empty connector skill/MCP
  fields and preserved plugin metadata.

## Python alignment

`pycodex.tools.tool_discovery` mirrors the Rust constants, enum wire values,
typed connector/plugin wrappers, TUI filtering behavior, and request plugin
install entry collection. Python also provides explicit mapping round-trips and
type validation for integration boundaries.

## Evidence

`tests/test_core_tool_discovery.py` covers the Rust module tests:

- `discoverable_tool_enums_use_expected_wire_names`
- `filter_request_plugin_install_discoverable_tools_for_codex_tui_omits_plugins`

Additional Python coverage exercises accessor delegation, non-TUI preservation,
entry collection, result serialization, mapping round-trips, and malformed input
guards.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
