from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    AdditionalRateLimitDetails,
    CreditStatusDetails,
    PlanType,
    RateLimitReachedKind,
    RateLimitReachedType,
    RateLimitStatusDetails,
    RateLimitStatusPayload,
    RateLimitWindowSnapshot,
    UNSET,
)


def test_plan_type_and_reached_kind_unknown_fallbacks() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/rate_limit_status_payload.rs
    # Contract: serde(other) maps unknown enum strings to Unknown variants.
    assert PlanType.from_raw_value("enterprise_cbp_usage_based") is PlanType.ENTERPRISE_CBP_USAGE_BASED
    assert PlanType.from_raw_value("future-plan") is PlanType.UNKNOWN
    assert RateLimitReachedKind.from_raw_value("workspace_member_credits_depleted") is RateLimitReachedKind.WORKSPACE_MEMBER_CREDITS_DEPLETED
    assert RateLimitReachedKind.from_raw_value("future-kind") is RateLimitReachedKind.UNKNOWN


def test_reached_type_uses_type_field_name() -> None:
    # Rust contract: RateLimitReachedType serializes field `kind` as JSON key `type`.
    reached = RateLimitReachedType.from_mapping({"type": "rate_limit_reached"})

    assert reached.kind is RateLimitReachedKind.RATE_LIMIT_REACHED
    assert reached.to_json_dict() == {"type": "rate_limit_reached"}


def test_new_matches_rust_constructor_defaults() -> None:
    # Rust contract: RateLimitStatusPayload::new sets plan_type and omits double-option fields.
    payload = RateLimitStatusPayload.new(PlanType.PRO)

    assert payload.plan_type is PlanType.PRO
    assert payload.rate_limit is UNSET
    assert payload.credits is UNSET
    assert payload.additional_rate_limits is UNSET
    assert payload.rate_limit_reached_type is UNSET
    assert payload.to_json_dict() == {"plan_type": "pro"}


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default uses PlanType::Guest and omitted optional fields.
    payload = RateLimitStatusPayload()

    assert payload.plan_type is PlanType.GUEST
    assert payload.rate_limit is UNSET
    assert payload.credits is UNSET


def test_double_option_payload_fields_decode_and_serialize() -> None:
    # Rust contract: all optional payload fields use serde_with double_option.
    payload = RateLimitStatusPayload.from_mapping(
        {
            "plan_type": "plus",
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {
                    "used_percent": 42,
                    "limit_window_seconds": 300,
                    "reset_after_seconds": 120,
                    "reset_at": 123,
                },
            },
            "credits": {"has_credits": True},
            "additional_rate_limits": [{"limit_name": "other", "metered_feature": "other"}],
            "rate_limit_reached_type": {"type": "workspace_owner_usage_limit_reached"},
        }
    )

    assert payload.plan_type is PlanType.PLUS
    assert isinstance(payload.rate_limit, RateLimitStatusDetails)
    assert isinstance(payload.rate_limit.primary_window, RateLimitWindowSnapshot)
    assert payload.credits == CreditStatusDetails(has_credits=True, unlimited=False)
    assert payload.additional_rate_limits == (AdditionalRateLimitDetails.new("other", "other"),)
    assert payload.rate_limit_reached_type == RateLimitReachedType(RateLimitReachedKind.WORKSPACE_OWNER_USAGE_LIMIT_REACHED)
    assert payload.to_json_dict()["additional_rate_limits"] == [{"limit_name": "other", "metered_feature": "other"}]

    explicit_null = RateLimitStatusPayload.from_mapping({"plan_type": "free", "rate_limit": None})
    assert explicit_null.rate_limit is None
    assert explicit_null.to_json_dict()["rate_limit"] is None


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: enums and nested objects must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected string"):
        RateLimitStatusPayload.from_mapping({"plan_type": 123})
    with pytest.raises(TypeError, match="expected additional rate limits array or null"):
        RateLimitStatusPayload.from_mapping({"additional_rate_limits": "nope"})
