# codex-utils-plugins src/mention_syntax.rs status

Rust coordinate: `codex/codex-rs/utils/plugins/src/mention_syntax.rs`

Python coordinate: `pycodex/utils/plugins/mention_syntax.py`

Status: `complete`

Behavior contract:

- `TOOL_MENTION_SIGIL` is the plaintext tool mention sigil `$`.
- `PLUGIN_TEXT_MENTION_SIGIL` is the plugin linked-plaintext sigil `@`.

Evidence:

- `tests/test_utils_plugins_mention_syntax.py` covers both exported constants.
- Actual test execution is deferred until the remaining crate modules are certified.
