# pycodex.utils.json_to_toml

Python alignment target for Rust crate `codex-utils-json-to-toml`.

Rust coordinate:

- `codex/codex-rs/utils/json-to-toml/src/lib.rs`

Python mapping:

- `pycodex/utils/json_to_toml/__init__.py`

The module preserves Rust's JSON value to TOML value conversion contract:

- JSON null maps to an empty string
- booleans, integers, floats, and strings map directly
- arrays and objects recurse
- unsupported values fall back to string representation

