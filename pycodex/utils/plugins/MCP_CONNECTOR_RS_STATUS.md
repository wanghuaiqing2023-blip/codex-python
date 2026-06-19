# codex-utils-plugins src/mcp_connector.rs status

Rust coordinate: `codex/codex-rs/utils/plugins/src/mcp_connector.rs`

Python coordinate: `pycodex/utils/plugins/mcp_connector.py`

Status: `complete`

Behavior contract:

- default originators reject ids in `DISALLOWED_CONNECTOR_IDS`.
- first-party chat originators reject ids in `FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS` instead.
- `sanitize_name` lowercases ASCII alphanumeric characters, converts other characters to separators, trims surrounding separators, defaults an empty slug to `app`, and returns the underscore form.

Evidence:

- `tests/test_utils_plugins_mcp_connector.py` covers connector id filtering and name sanitization source contracts.
- Actual test execution is deferred until the remaining crate modules are certified.
