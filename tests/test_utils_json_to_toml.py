from __future__ import annotations

from pycodex.utils.json_to_toml import json_to_toml


def test_json_number_to_toml() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_number_to_toml
    assert json_to_toml(123) == 123


def test_json_array_to_toml() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_array_to_toml
    assert json_to_toml([True, 1]) == [True, 1]


def test_json_bool_to_toml() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_bool_to_toml
    assert json_to_toml(False) is False


def test_json_float_to_toml() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_float_to_toml
    assert json_to_toml(1.25) == 1.25


def test_json_null_to_toml() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_null_to_toml
    assert json_to_toml(None) == ""


def test_json_object_nested() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Rust test: tests::json_object_nested
    assert json_to_toml({"outer": {"inner": 2}}) == {"outer": {"inner": 2}}


def test_non_json_value_falls_back_to_string() -> None:
    # Source: codex/codex-rs/utils/json-to-toml/src/lib.rs
    # Contract: unsupported numeric representation falls back to String; Python
    # mirrors that catch-all for non-JSON-like values.
    assert json_to_toml(object()).startswith("<object object at ")
