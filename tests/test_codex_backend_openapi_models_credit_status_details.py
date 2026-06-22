from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import CreditStatusDetails, UNSET


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/credit_status_details.rs
    # Contract: CreditStatusDetails::new sets bools and omits all double-option fields.
    details = CreditStatusDetails.new(True, False)

    assert details.has_credits is True
    assert details.unlimited is False
    assert details.balance is UNSET
    assert details.approx_local_messages is UNSET
    assert details.approx_cloud_messages is UNSET
    assert details.to_json_dict() == {"has_credits": True, "unlimited": False}


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default false-initializes bools and omits optional fields.
    details = CreditStatusDetails()

    assert details.has_credits is False
    assert details.unlimited is False
    assert details.balance is UNSET


def test_double_option_fields_decode_and_serialize() -> None:
    # Rust contract: balance and approximate message fields use serde_with double_option.
    details = CreditStatusDetails.from_mapping(
        {
            "has_credits": True,
            "unlimited": False,
            "balance": "9.99",
            "approx_local_messages": [{"message": "local"}],
            "approx_cloud_messages": None,
        }
    )

    assert details.balance == "9.99"
    assert details.approx_local_messages == ({"message": "local"},)
    assert details.approx_cloud_messages is None
    assert details.to_json_dict()["approx_local_messages"] == [{"message": "local"}]
    assert details.to_json_dict()["approx_cloud_messages"] is None

    explicit_null = CreditStatusDetails.from_mapping({"has_credits": False, "unlimited": False, "balance": None})
    assert explicit_null.balance is None
    assert explicit_null.to_json_dict()["balance"] is None


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: bool/string/array fields must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected bool"):
        CreditStatusDetails.from_mapping({"has_credits": "true"})
    with pytest.raises(TypeError, match="expected string or null"):
        CreditStatusDetails.from_mapping({"balance": 99})
    with pytest.raises(TypeError, match="expected array or null"):
        CreditStatusDetails.from_mapping({"approx_local_messages": {"message": "local"}})
