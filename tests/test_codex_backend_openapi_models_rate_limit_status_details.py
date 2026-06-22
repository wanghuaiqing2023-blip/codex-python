from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    RateLimitStatusDetails,
    RateLimitWindowSnapshot,
    UNSET,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/rate_limit_status_details.rs
    # Contract: RateLimitStatusDetails::new sets bools and omits both window fields.
    details = RateLimitStatusDetails.new(True, False)

    assert details.allowed is True
    assert details.limit_reached is False
    assert details.primary_window is UNSET
    assert details.secondary_window is UNSET
    assert details.to_json_dict() == {"allowed": True, "limit_reached": False}


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default false-initializes bools and omits double-option windows.
    details = RateLimitStatusDetails()

    assert details.allowed is False
    assert details.limit_reached is False
    assert details.primary_window is UNSET
    assert details.secondary_window is UNSET


def test_double_option_window_serialization_states() -> None:
    # Rust contract: serde_with double_option distinguishes omitted, null, and object windows.
    omitted = RateLimitStatusDetails.from_mapping({"allowed": True, "limit_reached": True})
    explicit_null = RateLimitStatusDetails.from_mapping(
        {"allowed": True, "limit_reached": True, "primary_window": None}
    )
    present = RateLimitStatusDetails(
        allowed=True,
        limit_reached=False,
        primary_window=RateLimitWindowSnapshot.new(42, 300, 120, 123),
    )

    assert omitted.primary_window is UNSET
    assert "primary_window" not in omitted.to_json_dict()
    assert explicit_null.primary_window is None
    assert explicit_null.to_json_dict()["primary_window"] is None
    assert present.to_json_dict()["primary_window"] == {
        "used_percent": 42,
        "limit_window_seconds": 300,
        "reset_after_seconds": 120,
        "reset_at": 123,
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: bool fields and nested windows must have matching JSON types.
    with pytest.raises(TypeError, match="expected bool"):
        RateLimitStatusDetails.from_mapping({"allowed": "true", "limit_reached": False})
    with pytest.raises(TypeError, match="expected rate limit window object or null"):
        RateLimitStatusDetails.from_mapping({"primary_window": "window"})
