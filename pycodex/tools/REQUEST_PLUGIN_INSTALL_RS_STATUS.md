# codex-tools src/request_plugin_install.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/request_plugin_install.rs`
Rust tests: `codex/codex-rs/tools/src/request_plugin_install_tests.rs`
Python module: `pycodex/tools/request_plugin_install.py`
Python tests: `tests/test_core_request_plugin_install.py`

## Behavior contract

`src/request_plugin_install.rs` owns the request-plugin-install helper contract:

- `RequestPluginInstallArgs`, `RequestPluginInstallResult`, and approval metadata constants.
- Elicitation request construction with the expected `threadId`, `turnId`,
  `serverName`, `mode`, `_meta`, `message`, and empty object schema.
- Approval metadata construction with connector `install_url` preserved and absent
  plugin install URLs omitted.
- Connector completion helpers that require matching connector IDs and
  `is_accessible == true`.
- Multi-connector completion only succeeds when every expected connector is
  accessible.

## Python alignment

`pycodex.tools.request_plugin_install` mirrors the Rust constants, data records,
elicitation request/meta builders, and connector completion helpers. Python keeps
the Rust serialized field names while accepting enum-like objects and mappings
where the surrounding Python integration needs them.

## Evidence

`tests/test_core_request_plugin_install.py` covers the Rust module tests:

- `build_request_plugin_install_elicitation_request_uses_expected_shape`
- `build_request_plugin_install_elicitation_request_for_plugin_omits_install_url`
- `build_request_plugin_install_meta_uses_expected_shape`
- `verified_connector_install_completed_requires_accessible_connector`
- `all_requested_connectors_picked_up_requires_every_expected_connector`

Additional Python checks cover local type validation for non-Rust-shaped inputs.

Focused validation is deferred by the current crate automation rule until
`codex-tools` functional module code is complete.
