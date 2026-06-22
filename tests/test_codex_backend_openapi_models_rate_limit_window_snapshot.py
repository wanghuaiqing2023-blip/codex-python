from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import RateLimitWindowSnapshot


def test_new_matches_rust_constructor() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/rate_limit_window_snapshot.rs
    # Contract: RateLimitWindowSnapshot::new assigns all four i32 fields.
    snapshot = RateLimitWindowSnapshot.new(42, 300, 120, 123456)

    assert snapshot.used_percent == 42
    assert snapshot.limit_window_seconds == 300
    assert snapshot.reset_after_seconds == 120
    assert snapshot.reset_at == 123456


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default zeroes all i32 fields.
    assert RateLimitWindowSnapshot() == RateLimitWindowSnapshot(0, 0, 0, 0)


def test_json_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde rename preserves snake_case field names.
    snapshot = RateLimitWindowSnapshot.from_mapping(
        {
            "used_percent": 84,
            "limit_window_seconds": 3600,
            "reset_after_seconds": 600,
            "reset_at": 999,
        }
    )

    assert snapshot.to_json_dict() == {
        "used_percent": 84,
        "limit_window_seconds": 3600,
        "reset_after_seconds": 600,
        "reset_at": 999,
    }


def test_from_mapping_rejects_non_integer_fields() -> None:
    # Rust serde contract: numeric fields must deserialize as integers.
    with pytest.raises(TypeError, match="expected integer"):
        RateLimitWindowSnapshot.from_mapping({"used_percent": "42"})
