# codex-utils-json-to-toml src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/json-to-toml/src/lib.rs`

Python target:

- `pycodex/utils/json_to_toml/__init__.py`

Behavior contract covered:

- null to empty string
- bool/int/float/string passthrough
- recursive array conversion
- recursive object/table conversion
- unsupported values fall back to string representation

Tests:

- `tests/test_utils_json_to_toml.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_json_to_toml.py -q` -> `7 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\json_to_toml\__init__.py tests\test_utils_json_to_toml.py` -> passed

