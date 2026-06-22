from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import AdditionalRateLimitDetails, UNSET


class _RateLimitStub:
    def to_json_dict(self) -> dict[str, int]:
        return {"used_percent": 42}


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/additional_rate_limit_details.rs
    # Contract: AdditionalRateLimitDetails::new sets required strings and omits rate_limit.
    details = AdditionalRateLimitDetails.new("codex_other", "codex_other")

    assert details.limit_name == "codex_other"
    assert details.metered_feature == "codex_other"
    assert details.rate_limit is UNSET
    assert details.to_json_dict() == {
        "limit_name": "codex_other",
        "metered_feature": "codex_other",
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default uses empty strings and no outer rate_limit option.
    details = AdditionalRateLimitDetails()

    assert details.limit_name == ""
    assert details.metered_feature == ""
    assert details.rate_limit is UNSET


def test_double_option_rate_limit_serialization_states() -> None:
    # Rust contract: serde_with double_option distinguishes omitted, null, and object.
    omitted = AdditionalRateLimitDetails.from_mapping({"limit_name": "a", "metered_feature": "b"})
    explicit_null = AdditionalRateLimitDetails.from_mapping(
        {"limit_name": "a", "metered_feature": "b", "rate_limit": None}
    )
    present = AdditionalRateLimitDetails("a", "b", _RateLimitStub())

    assert omitted.rate_limit is UNSET
    assert "rate_limit" not in omitted.to_json_dict()
    assert explicit_null.rate_limit is None
    assert explicit_null.to_json_dict()["rate_limit"] is None
    assert present.to_json_dict()["rate_limit"] == {"used_percent": 42}


def test_from_mapping_rejects_non_string_required_fields() -> None:
    # Rust serde contract: required string fields must deserialize as strings.
    with pytest.raises(TypeError, match="expected string"):
        AdditionalRateLimitDetails.from_mapping({"limit_name": 123, "metered_feature": "b"})
