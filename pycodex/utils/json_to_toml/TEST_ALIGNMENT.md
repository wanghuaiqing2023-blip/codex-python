# codex-utils-json-to-toml Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/json-to-toml/src/lib.rs`

Python module:

- `pycodex/utils/json_to_toml/__init__.py`

Parity evidence:

- `tests/test_utils_json_to_toml.py`

Rust-derived coverage:

- `json_number_to_toml`
- `json_array_to_toml`
- `json_bool_to_toml`
- `json_float_to_toml`
- `json_null_to_toml`
- `json_object_nested`

Additional Python boundary coverage:

- non-JSON-like values fall back to string representation.

Validation:

- `python -m pytest tests\test_utils_json_to_toml.py -q` -> `7 passed`
- `python -m py_compile pycodex\utils\json_to_toml\__init__.py tests\test_utils_json_to_toml.py` -> passed

Known adaptations:

- Rust returns typed `toml::Value` variants. Python returns the equivalent plain Python values accepted by the local TOML/config helpers.

